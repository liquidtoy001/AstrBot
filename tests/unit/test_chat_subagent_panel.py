from types import SimpleNamespace

import pytest

from astrbot.core.agent.runtime import AgentSessionRef
from astrbot.core.astr_agent_runtime.subagents.store import (
    AgentRecord,
    AgentScope,
    AgentState,
    TaskRecord,
)
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError

UMO = "webchat:FriendMessage:webchat!alice!s1"


class _Db:
    def __init__(self, native):
        self.native = native

    async def get_platform_session_by_id(self, session_id):
        if session_id != "s1":
            return None
        return SimpleNamespace(
            creator="alice", is_group=False, platform_id="webchat", session_id="s1"
        )

    async def get_preference(self, scope, scope_id, key):
        value = self.native.get(key)
        return SimpleNamespace(value=value) if value else None


class _Subagents:
    def __init__(self, agents):
        self.store = SimpleNamespace(
            list=lambda scope: [a for a in agents if a.scope == scope]
        )
        self.cancelled = None

    async def cancel_owned(self, scope, agent_id):
        if agent_id != "a1":
            raise ValueError(f"Unknown subagent: {agent_id}")
        self.cancelled = (scope, agent_id)
        return {"agent_id": agent_id, "state": "cancelled"}


def _agent(agent_id, scope, state):
    return AgentRecord(
        agent_id=agent_id,
        scope=scope,
        runtime="astrbot",
        name="reviewer",
        conversation_id=f"native-{agent_id}",
        options={
            "config": {"persona": {"persona_id": "critic"}, "model": {}},
            "config_id": "cfg1",
        },
        owner={"sender_id": "alice"},
        parent=AgentSessionRef(runtime="astrbot", session_id=scope.conversation_id),
        turns=[
            TaskRecord(
                1,
                [{"type": "plain", "text": "Review the report"}],
                state=state,
                result="Looks fine",
                completed_steps=3,
            )
        ],
    )


def _service(agents, native, provider_config=None):
    service = object.__new__(ChatService)
    service.db = _Db(native)
    provider = SimpleNamespace(
        get_model=lambda: "gpt-test",
        provider_config=provider_config
        or {"anth_thinking_config": {"type": "adaptive", "effort": "low"}},
    )
    service.core_lifecycle = SimpleNamespace(
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=lambda umo: _async("c1")
        ),
        astrbot_config_mgr=SimpleNamespace(
            get_conf=lambda umo: {"agent": {"config": {"subagents": {"enabled": True}}}}
        ),
        subagents=_Subagents(agents),
        provider_manager=SimpleNamespace(inst_map={"p1": provider}),
        agent_configs=SimpleNamespace(list=_configs),
    )
    return service


async def _configs():
    return [SimpleNamespace(config_id="cfg1", name="haiku-worker")]


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_list_subagents_merges_record_and_native_conversation():
    scope = AgentScope(UMO, "c1")
    other = AgentScope(UMO, "c-old")
    native = {
        "native-a1": {
            "umo": UMO,
            "provider_id": "p1",
            "tools": ["web_search"],
            "instructions": "Be critical",
            "token_usage": 1234,
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [{"function": {"name": "web_search"}}],
                },
                {"role": "tool", "content": "..."},
            ],
        }
    }
    service = _service(
        [
            _agent("a1", scope, AgentState.COMPLETED),
            _agent("a2", other, AgentState.RUNNING),
        ],
        native,
    )
    data = await service.list_subagents("alice", "s1")
    assert data["enabled"] is True
    assert [a["agent_id"] for a in data["agents"]] == ["a1"]
    agent = data["agents"][0]
    assert agent["state"] == "completed"
    assert agent["persona_id"] == "critic"
    assert agent["provider_id"] == "p1"
    assert agent["model"] == "gpt-test"
    assert agent["thinking"] == "low"
    assert agent["config_name"] == "haiku-worker"
    assert agent["tools"] == ["web_search"]
    assert agent["context_tokens"] == 1234
    assert agent["completed_steps"] == 3
    assert agent["result"] == "Looks fine"


@pytest.mark.asyncio
async def test_subagent_access_requires_session_owner_and_known_agent():
    service = _service([], {})
    with pytest.raises(ChatServiceError):
        await service.list_subagents("mallory", "s1")
    with pytest.raises(ChatServiceError):
        await service.cancel_subagent("alice", "s1", "missing")
    result = await service.cancel_subagent("alice", "s1", "a1")
    assert result["state"] == "cancelled"
    assert service.core_lifecycle.subagents.cancelled == (AgentScope(UMO, "c1"), "a1")


@pytest.mark.asyncio
async def test_subagent_panel_does_not_read_foreign_private_conversation():
    scope = AgentScope(UMO, "c1")
    service = _service(
        [_agent("a1", scope, AgentState.RUNNING)],
        {
            "native-a1": {
                "umo": "webchat:FriendMessage:webchat!bob!private",
                "provider_id": "secret",
                "instructions": "private",
                "token_usage": 12345,
                "tools": ["secret_tool"],
                "messages": [],
            }
        },
    )
    agents = (await service.list_subagents("alice", "s1"))["agents"]
    assert len(agents) == 1
    assert agents[0].get("context_tokens", 0) == 0
    assert "secret" not in str(agents)


@pytest.mark.asyncio
async def test_deleted_agent_configuration_keeps_existing_agent_visible():
    service = _service([_agent("a1", AgentScope(UMO, "c1"), AgentState.RUNNING)], {})

    async def none_left():
        return []

    service.core_lifecycle.agent_configs.list = none_left
    agents = (await service.list_subagents("alice", "s1"))["agents"]
    assert [agent["agent_id"] for agent in agents] == ["a1"]
    assert agents[0]["config_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_config", "expected"),
    [
        ({"custom_extra_body": {"reasoning_effort": "high"}}, "high"),
        ({"custom_extra_body": {"reasoning": {"effort": "medium"}}}, "medium"),
        # Only the three ChatUI levels are shown; other values are not guessed.
        ({"custom_extra_body": {"reasoning_effort": "xhigh"}}, None),
        ({"custom_extra_body": {"reasoning_effort": "minimal"}}, None),
        ({"anth_thinking_config": {"type": "enabled", "budget": 4096}}, None),
        ({"anth_thinking_config": {"type": "adaptive", "effort": "max"}}, None),
    ],
)
async def test_subagent_thinking_level_comes_only_from_known_provider_levels(
    provider_config, expected
):
    scope = AgentScope(UMO, "c1")
    native = {"native-a1": {"umo": UMO, "provider_id": "p1", "messages": []}}
    service = _service(
        [_agent("a1", scope, AgentState.RUNNING)], native, provider_config
    )
    data = await service.list_subagents("alice", "s1")
    assert data["agents"][0]["thinking"] == expected
