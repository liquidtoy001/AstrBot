"""Own all built-in sessions; Core never owns their runners or history writes."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot import logger
from astrbot.core.agent.config import StoredAgentConfig
from astrbot.core.agent.runtime import AgentInput, AgentRuntime, AgentSession, AgentTurn
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent

from .delegated_session import DelegatedAgentInput, DelegatedAgentSession
from .main_session import MainAgentSession

if TYPE_CHECKING:
    from astrbot.core.agent.config_store import AgentConfigStore
    from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
    from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
    from astrbot.core.star.context import Context


# Description shown on agent configs created by spawn_agent(provider_id=...).
AUTO_AGENT_CONFIG_DESCRIPTION = (
    "Created automatically when the main agent was asked to use this model."
)


class AstrAgentRuntime(AgentRuntime):
    """AstrBot host services around native main and delegated execution."""

    def __init__(
        self,
        context: Context,
        *,
        agent_configs: AgentConfigStore,
        subagents: SubAgentService,
    ) -> None:
        """Bind native execution to explicit configuration and delegation services.

        Args:
            context: Host provider, plugin, platform and conversation services.
            agent_configs: Shared storage for reusable agent configurations.
            subagents: Delegation scheduler sharing the application's runtime registry.
        """
        self.context = context
        self.agent_configs = agent_configs
        self.subagents = subagents
        self._sessions: dict[tuple[str, str], AgentSession] = {}
        self._opening = asyncio.Lock()
        self._active_main: dict[str, AgentTurn] = {}
        self._closed = False

    def normalize_config(self, config: dict, *, delegated: bool = False) -> dict:
        """Validate native options and apply role-appropriate defaults.

        Args:
            config: Native model, persona, execution and delegation options.
            delegated: Whether to retain only reusable persona/model overrides.

        Returns:
            Validated native configuration.
        """
        from astrbot.core.config.agent import normalize_agent

        return normalize_agent(
            {"runtime": "astrbot", "config": config}, delegated=delegated
        )["config"]

    def referenced_config_ids(self, config: dict) -> list[str]:
        """Return configured delegation targets, including disabled selections.

        Args:
            config: Native runtime configuration.

        Returns:
            Stable agent_config IDs referenced by this configuration.
        """
        return list(config.get("subagents", {}).get("config_ids", []))

    async def spawn_agent(
        self,
        context: SubAgentContext,
        messages: list[dict],
        *,
        config_id: str | None = None,
        name: str | None = None,
        provider_id: str | None = None,
    ) -> dict:
        """Resolve this runtime's delegation policy before opening another agent.

        Args:
            context: Bound native parent execution and authorized capabilities.
            messages: Explicit structured task input.
            config_id: Optional reusable agent selected by the parent.
            name: Optional session display name.
            provider_id: Optional chat provider; its agent config in the
                profile is reused or created and selected.

        Returns:
            Public session identity and initial execution state, plus
            ``agent_config`` when provider_id chose the configuration.

        Raises:
            ValueError: If delegation, the agent_config, or its runtime is unavailable.
        """
        config = (
            self.context.get_config(umo=context.event.unified_msg_origin)
            .get("agent", {})
            .get("config", {})
        )
        policy = config.get("subagents", {})
        if not policy.get("enabled", False):
            raise ValueError("Subagents are disabled for this configuration profile")
        selected_runtime = "astrbot"
        selected_config = self.normalize_config({}, delegated=True)
        # Models that fill every optional field send blanks for unused ones,
        # and some put a provider ID into config_id.
        config_id = (config_id or "").strip() or None
        provider_id = (provider_id or "").strip() or None
        name = (name or "").strip() or None
        if config_id is not None and config_id not in policy.get("config_ids", []):
            if provider_id is not None:
                config_id = None
            elif config_id in {
                provider.provider_config["id"]
                for provider in self.context.get_all_providers()
            }:
                config_id, provider_id = None, config_id
        if config_id is not None and provider_id is not None:
            agent_config = await self.agent_configs.get(config_id)
            configured = agent_config.config.get("model", {}).get("provider_id")
            if configured != provider_id:
                raise ValueError(
                    f"Agent configuration {config_id} does not run on {provider_id}. "
                    f"Send only config_id={config_id} to use that agent, or only "
                    f"provider_id={provider_id} (config_id empty) to run on that provider."
                )
            provider_id = None
        chosen = None
        if provider_id is not None:
            chosen = await self._agent_config_for_provider(
                context.event.unified_msg_origin, provider_id
            )
            config_id = chosen[0].config_id
        if config_id is not None:
            # A config chosen by provider_id was just selected in the stored
            # profile; this message still reads the earlier snapshot.
            if chosen is None and config_id not in policy.get("config_ids", []):
                raise ValueError(
                    f"Agent configuration is not selected by this profile: {config_id}"
                )
            agent_config = await self.agent_configs.get(config_id)
            if not agent_config.enabled:
                raise ValueError(f"Agent configuration is disabled: {config_id}")
            selected_runtime, selected_config = (
                agent_config.runtime,
                agent_config.config,
            )
            name = name or agent_config.name
        runtime = self.subagents.runtimes.get(selected_runtime)
        if runtime is None:
            raise ValueError(f"Agent runtime unavailable: {selected_runtime}")
        selected_config = runtime.normalize_config(selected_config, delegated=True)
        result = await self.subagents.spawn(
            context,
            messages,
            runtime=selected_runtime,
            config=selected_config,
            config_id=config_id,
            name=name,
        )
        if chosen is not None:
            # Tell the main agent, so it can tell the user, what was set up.
            result["agent_config"] = {
                "config_id": chosen[0].config_id,
                "name": chosen[0].name,
                "created": chosen[1],
            }
        return result

    async def _agent_config_for_provider(
        self, umo: str, provider_id: str
    ) -> tuple[StoredAgentConfig, bool]:
        """Find or create the agent config that runs on a chat provider.

        Reuses an enabled AstrBot config without its own persona that uses this
        provider, preferring one the profile already selects; otherwise creates
        one. The result is selected in the session's
        stored profile. The store lock keeps concurrent spawns to one config.

        Args:
            umo: Session whose routed profile receives the selection.
            provider_id: Loaded chat provider the agent should run on.

        Returns:
            The configuration and whether it was created now.

        Raises:
            ValueError: If the provider is not a loaded chat provider.
        """
        providers = {
            provider.provider_config["id"]: provider
            for provider in self.context.get_all_providers()
        }
        if provider_id not in providers:
            raise ValueError(
                f"Unknown or unavailable chat provider: {provider_id}. Available chat provider IDs: {list(providers)}"
            )
        manager = self.context.astrbot_config_mgr
        profile = (
            manager.confs.get(manager.get_conf_info(umo)["id"]) or manager.default_conf
        )
        async with self.agent_configs.lock:
            selected = (
                profile.setdefault("agent", {})
                .setdefault("config", {})
                .setdefault("subagents", {})
                .setdefault("config_ids", [])
            )
            matching = [
                item
                for item in await self.agent_configs.list()
                if item.enabled
                and item.runtime == "astrbot"
                and item.config.get("model", {}).get("provider_id") == provider_id
                and not item.config.get("persona", {}).get("persona_id")
            ]
            # Any plain config on this provider will do; prefer one the profile
            # already selects, so no duplicate is created.
            agent_config = next(
                (item for item in matching if item.config_id in selected),
                matching[0] if matching else None,
            )
            created = agent_config is None
            if agent_config is None:
                model = providers[provider_id].get_model() or provider_id
                agent_config = await self.agent_configs.save(
                    StoredAgentConfig(
                        config_id=str(uuid4()),
                        name=f"{model.rsplit('/', 1)[-1]} worker"[:128],
                        description=AUTO_AGENT_CONFIG_DESCRIPTION,
                        runtime="astrbot",
                        config=self.normalize_config(
                            {"model": {"provider_id": provider_id}}, delegated=True
                        ),
                    )
                )
            if agent_config.config_id not in selected:
                selected.append(agent_config.config_id)
                await profile.save_config_async()
        return agent_config, created

    async def initialize(self) -> None:
        """Initialize native execution environments before plugins can use them."""
        if sys.platform == "win32" and any(
            config.get("provider_settings", {}).get("computer_use_runtime") == "local"
            for config in self.context.astrbot_config_mgr.confs.values()
        ):
            try:
                from .computer.process_sandbox.windows_setup import (
                    initialize_windows_sandbox,
                )

                await asyncio.to_thread(initialize_windows_sandbox)
            except Exception as exc:
                logger.warning(f"Windows Local sandbox is unavailable: {exc}")

    async def open_session(
        self,
        umo: str,
        *,
        session_id: str | None = None,
        options: dict | None = None,
        input: AgentInput | None = None,
    ) -> AgentSession:
        """Bind the current main conversation or restore an exact identity.

        Args:
            umo: Source selected by Core.
            session_id: Exact conversation to restore, or None for current main.
            options: Runtime-specific session options.
            input: Event for creating a main conversation or opening a delegated one.

        Returns:
            The sole live owner of the requested native conversation.

        Raises:
            ValueError: If the runtime is closed, the session is missing, or ownership differs.
        """
        if self._closed:
            raise ValueError("AstrBot agent runtime is closed")
        profile = (options or {}).get("profile", "main")
        if (
            profile == "main"
            and input is not None
            and isinstance(input.event, AgentWakeupEvent)
        ):
            target = input.event.agent_session
            if target is not None:
                if session_id is not None and session_id != target.session_id:
                    raise ValueError("Wakeup and runtime session targets differ")
                session_id = target.session_id
        manager = self.context.conversation_manager
        if profile == "subagent":
            async with self._opening:
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = (
                    self._sessions.get((profile, session_id))
                    if session_id is not None
                    else None
                )
                if session is not None and session.umo != umo:
                    raise ValueError("Agent session belongs to another UMO")
                if session is None or session.closed:
                    if not isinstance(input, DelegatedAgentInput):
                        raise ValueError(
                            "Opening a child requires delegated caller input"
                        )
                    if session is not None:
                        await session.close()
                    session = await DelegatedAgentSession.open(
                        self, umo, input, options or {}, session_id=session_id
                    )
                if self._closed:
                    await session.close()
                    raise ValueError(
                        "AstrBot agent runtime closed during session creation"
                    )
                if session.umo != umo:
                    raise ValueError("Agent session belongs to another UMO")
                self._sessions[(profile, session.id)] = session
                return session
        if profile != "main":
            raise ValueError(f"Unknown built-in agent session profile: {profile}")
        conversation = None
        select_current = session_id is None
        if select_current and input is not None:
            request = input.event.get_extra("provider_request")
            if request is not None and request.conversation is not None:
                session_id = request.conversation.cid
                select_current = False
        if select_current:
            session_id = await manager.get_curr_conversation_id(umo)
        if conversation is None and session_id is not None:
            conversation = await manager.db.conversation_store.get_metadata(session_id)
        if conversation is None and select_current:
            # Only first creation needs serialization; recheck after acquiring the
            # lock so concurrent first messages cannot create competing sessions.
            async with self._opening:
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session_id = await manager.get_curr_conversation_id(umo)
                conversation = (
                    await manager.db.conversation_store.get_metadata(session_id)
                    if session_id is not None
                    else None
                )
                if conversation is None:
                    session_id = await manager.new_conversation(
                        umo,
                        platform_id=input.event.get_platform_id() if input else None,
                    )
                    conversation = await manager.db.conversation_store.get_metadata(
                        session_id
                    )
        if (
            session_id is None
            or conversation is None
            or conversation.umo != umo
            or self.subagents.store.find_native_conversation(umo, session_id)
            is not None
        ):
            raise ValueError("Agent conversation is missing or belongs to another UMO")
        # Existing conversations perform all database reads outside this registry
        # lock. Their execution lock controls when fresh history is loaded.
        async with self._opening:
            if self._closed:
                raise ValueError("AstrBot agent runtime closed during session creation")
            session = self._sessions.get((profile, session_id))
            if session is None or session.closed:
                if session is not None:
                    await session.close()
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = MainAgentSession(self, session_id, umo)
                self._sessions[(profile, session_id)] = session
            elif session.umo != umo:
                raise ValueError("Agent session belongs to another UMO")
            return session

    def active_turn(self, umo: str) -> AgentTurn | None:
        """Find main's active execution without exposing its native runner.

        Args:
            umo: Source of an arriving message or wakeup.

        Returns:
            The current turn handle, or None while no main turn can accept steering.
        """
        return self._active_main.get(umo)

    async def close(self) -> None:
        """Stop all sessions before releasing the runtime's host services."""
        from .computer.computer_client import shutdown_local_booter

        self._closed = True
        async with self._opening:
            sessions = list(self._sessions.values())
        try:
            await asyncio.gather(*(session.close() for session in sessions))
        finally:
            self._sessions.clear()
            await shutdown_local_booter()
