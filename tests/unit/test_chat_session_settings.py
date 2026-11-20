from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.core import session_overrides
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config import AstrBotConfig
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError

UMO = "webchat:FriendMessage:webchat!alice!s1"


@pytest_asyncio.fixture
async def persona_service(temp_db, tmp_path, monkeypatch):
    await temp_db.initialize()
    prefs = SharedPreferences(temp_db)
    await prefs.initialize()
    monkeypatch.setattr(session_overrides, "sp", prefs)
    monkeypatch.setattr("astrbot.core.conversation_mgr.sp", prefs)
    monkeypatch.setattr("astrbot.dashboard.services.chat_service.sp", prefs)
    config = AstrBotConfig(str(tmp_path / "profile.json"), deepcopy(DEFAULT_CONFIG))
    acm = AstrBotConfigManager(config, UmopConfigRouter(prefs), prefs)
    acm.abconf_data = {}
    acm.default_conf["agent"]["config"]["persona"]["persona_id"] = "helper"
    personas = PersonaManager(temp_db, acm)
    personas.personas_v3 = [
        {"name": "helper", "prompt": "Help"},
        {"name": "critic", "prompt": "Review"},
    ]
    service = object.__new__(ChatService)
    service.db = temp_db
    service.core_lifecycle = SimpleNamespace(
        conversation_manager=ConversationManager(temp_db, acm),
        astrbot_config_mgr=acm,
        provider_manager=SimpleNamespace(
            get_using_provider_async=AsyncMock(return_value=None)
        ),
        persona_mgr=personas,
    )
    await temp_db.create_platform_session(creator="alice", session_id="s1")
    try:
        yield service, prefs
    finally:
        await prefs.close()


@pytest.mark.asyncio
async def test_session_settings_ignore_removed_legacy_persona_rule(persona_service):
    service, prefs = persona_service
    await prefs.session_put(UMO, "session_service_config", {"persona_id": "critic"})
    data = await service.get_session_settings("alice", "s1")
    # Removing B3's fix exposes a stale lock that the runtime does not use.
    assert data["persona"] == {
        "conversation": None,
        "default": "helper",
        "options": ["helper", "critic"],
    }
    selected, _, _ = await service.core_lifecycle.persona_mgr.resolve_selected_persona(
        umo=UMO, platform_name="webchat"
    )
    assert selected == data["persona"]["default"]


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime", ["astrbot", "dify"])
async def test_session_settings_reflect_effective_overrides(persona_service, runtime):
    service, _ = persona_service
    core = service.core_lifecycle
    core.astrbot_config_mgr.default_conf["agent"]["runtime"] = runtime
    core.astrbot_config_mgr.default_conf["agent"]["config"]["persona_id"] = "helper"
    path = (
        "agent.config.persona.persona_id"
        if runtime == "astrbot"
        else "agent.config.persona_id"
    )
    await core.conversation_manager.new_conversation(UMO, persona_id="stale")
    await session_overrides.update_overrides(UMO, {path: "critic"})
    data = await service.get_session_settings("alice", "s1")
    assert data["persona"]["conversation"] == "critic"
    assert data["persona"]["default"] == "helper"
    assert "forced" not in data["persona"]
    selected, _, _ = await core.persona_mgr.resolve_selected_persona(
        umo=UMO, platform_name="webchat"
    )
    assert selected == data["persona"]["conversation"]


@pytest.mark.asyncio
async def test_persona_switch_existing_conversation_and_rejects_bad_input(
    persona_service,
):
    service, _ = persona_service
    await service.core_lifecycle.conversation_manager.new_conversation(UMO)
    data = await service.set_session_persona("alice", "s1", "[%None]")
    assert data["persona"]["conversation"] == "[%None]"
    with pytest.raises(ChatServiceError):
        await service.set_session_persona("alice", "s1", "unknown")
    with pytest.raises(ChatServiceError):
        await service.get_session_settings("mallory", "s1")


@pytest.mark.asyncio
@pytest.mark.parametrize("persona_id", ["critic", "[%None]"])
async def test_new_conversation_persona_is_used_by_runtime(persona_service, persona_id):
    service, _ = persona_service
    core = service.core_lifecycle
    assert await core.conversation_manager.get_curr_conversation_id(UMO) is None
    await service.set_session_persona("alice", "s1", persona_id)
    # Removing B4's update leaves the runtime using the profile default.
    selected, _, _ = await core.persona_mgr.resolve_selected_persona(
        umo=UMO, platform_name="webchat"
    )
    assert selected == persona_id
    assert (await service.get_session_settings("alice", "s1"))["persona"][
        "conversation"
    ] == persona_id
