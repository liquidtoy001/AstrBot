"""Per-conversation ChatUI options: one path from the request to the event."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml
from jsonschema import Draft7Validator
from pydantic import ValidationError

from astrbot.core.astr_agent_runtime.main_agent.request import collect_initial_request
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.request_flags import (
    resolve_webchat_chat_options,
)
from astrbot.core.platform.sources.webchat.webchat_adapter import WebChatAdapter
from astrbot.dashboard.schemas import ChatThreadMessageRequest
from astrbot.dashboard.services.chat_service import ChatService

INVALID = ["xhigh", "", 1, True, [], {}, None]


def _event(payload):
    adapter = object.__new__(WebChatAdapter)
    adapter.metadata = PlatformMetadata(name="webchat", description="t", id="webchat")
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "webchat"
    message.session_id = "webchat!alice!options"
    message.message_id = "m1"
    message.sender = MessageMember("alice", "alice")
    message.message = []
    message.message_str = "hello"
    message.raw_message = ("alice", "options", payload)
    return adapter.create_event(message)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (400_000, 400_000),
        (True, None),
        (False, None),
        (0, None),
        (-5, None),
        ("400000", None),
        (1.5, None),
        (None, None),
    ],
)
def test_compact_threshold_accepts_only_positive_integers(value, expected):
    resolved = resolve_webchat_chat_options({"compact_threshold": value})
    assert resolved.pop("compact_threshold") == expected
    # The other options stay unset.
    assert set(resolved.values()) == {None}
    assert _event({"compact_threshold": value}).get_extra("compact_threshold") == (
        expected
    )


def test_adapter_puts_options_on_the_event():
    from astrbot.core.astr_agent_runtime.permission_mode import _conversation_modes

    try:
        assert _event({"permission_mode": "root"}).get_extra("permission_mode") is None
        event = _event({"permission_mode": "workspace"})
        assert event.get_extra("permission_mode") == "workspace"
    finally:
        _conversation_modes.clear()


@pytest.mark.asyncio
async def test_adapter_puts_options_on_the_event_and_the_request():
    assert _event({"reasoning_effort": "xhigh"}).get_extra("reasoning_effort") is None
    event = _event({"reasoning_effort": "medium"})
    assert event.get_extra("reasoning_effort") == "medium"
    req, _ = await collect_initial_request(
        event,
        SimpleNamespace(),
        SimpleNamespace(provider_wake_prefix="", provider_settings={}),
    )
    assert req.reasoning_effort == "medium"
    assert req.fast_mode is False

    # Fast mode reaches the request only for a strict true.
    for value, expected in ((True, True), ("true", False), (1, False)):
        req, _ = await collect_initial_request(
            _event({"fast_mode": value}),
            SimpleNamespace(),
            SimpleNamespace(provider_wake_prefix="", provider_settings={}),
        )
        assert req.fast_mode is expected


def test_request_models_reject_unknown_options():
    with pytest.raises(ValidationError):
        ChatThreadMessageRequest(message="hi", permission_mode="root")
    with pytest.raises(ValidationError):
        ChatThreadMessageRequest(message="hi", compact_threshold=0)


@pytest.mark.parametrize(
    "schema_name",
    ["ChatRequest", "ChatMessageRegenerateRequest", "ChatThreadMessageRequest"],
)
def test_openapi_contract_accepts_the_options(schema_name):
    spec = yaml.safe_load(
        (Path(__file__).resolve().parents[2] / "openspec/openapi-v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft7Validator(
        {
            "$ref": f"#/components/schemas/{schema_name}",
            "components": spec["components"],
        }
    )
    payload = {
        "permission_mode": "workspace",
        "fast_mode": True,
        "compact_threshold": 400_000,
    }
    if schema_name != "ChatMessageRegenerateRequest":
        payload["message"] = "hello"
    validator.validate(payload)
    validator.validate({**payload, "permission_mode": "workspace_no_ask"})
    validator.validate({**payload, "reasoning_effort": "high"})
    assert list(validator.iter_errors({**payload, "reasoning_effort": "xhigh"}))
    assert list(validator.iter_errors({**payload, "permission_mode": "root"}))
    assert list(validator.iter_errors({**payload, "fast_mode": "yes"}))
    for invalid in (0, -1, True, "32000", 1.5):
        assert list(validator.iter_errors({**payload, "compact_threshold": invalid})), (
            invalid
        )


@pytest.mark.asyncio
async def test_thread_forwards_chat_options():
    service = object.__new__(ChatService)
    service.db = SimpleNamespace(
        get_webchat_thread_by_id=AsyncMock(
            return_value=SimpleNamespace(
                creator="alice", thread_id="t1", selected_text="excerpt"
            )
        )
    )
    options = {
        "permission_mode": "workspace",
        "fast_mode": True,
        "compact_threshold": 400_000,
    }
    result = await service.prepare_thread_chat_payload(
        "alice", {"thread_id": "t1", "message": [], **options}
    )
    assert {key: result.get(key) for key in options} == options


@pytest.mark.asyncio
async def test_websocket_send_forwards_chat_options():
    """WebSocket text chat shares the SSE run, so it must pass the options on."""
    from astrbot.dashboard.services.live_chat_service import (
        LiveChatService,
        LiveChatSession,
    )

    received = []

    async def build_chat_stream(username, post_data):
        received.append(post_data)

        async def stream():
            return
            yield

        return stream()

    service = object.__new__(LiveChatService)
    service.chat_service = SimpleNamespace(build_chat_stream=build_chat_stream)
    service.ensure_chat_subscription = AsyncMock()
    service.send_chat_payload = AsyncMock()
    await service.handle_chat_message(
        LiveChatSession("live", "alice"),
        {
            "t": "send",
            "session_id": "s1",
            "message": [{"type": "plain", "text": "hi"}],
            "permission_mode": "workspace",
        },
        AsyncMock(),
    )
    assert received[0]["permission_mode"] == "workspace"


@pytest.mark.asyncio
async def test_regenerate_forwards_chat_options():
    service = object.__new__(ChatService)
    service.running_convs = {}
    service.conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="c1")
    )
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(
            return_value=SimpleNamespace(
                creator="alice", platform_id="webchat", is_group=False, session_id="s1"
            )
        ),
        get_platform_message_history_by_id=AsyncMock(
            return_value=SimpleNamespace(
                platform_id="webchat", user_id="s1", content={"type": "bot"}
            )
        ),
        conversation_store=SimpleNamespace(
            read=AsyncMock(
                return_value=SimpleNamespace(
                    revision=SimpleNamespace(head_seq=2, leaf_event_id="e2")
                )
            ),
            rewind_webchat=AsyncMock(
                return_value=SimpleNamespace(
                    content={"message": ["original"]}, turn_id="turn"
                )
            ),
        ),
    )
    options = {
        "permission_mode": "workspace",
        "fast_mode": True,
        "compact_threshold": 400_000,
    }
    payload = await service.prepare_regenerate_message_payload(
        "alice", {"session_id": "s1", "message_id": 2, **options}
    )
    assert {key: payload[key] for key in options} == options
    assert payload["message"] == ["original"]
    service.db.conversation_store.rewind_webchat.assert_awaited_once_with(
        "c1", 2, expected_head=2, expected_leaf="e2"
    )


# Permission mode on the options path.


@pytest.mark.parametrize("invalid", INVALID + ["root"])
def test_resolver_keeps_only_known_permission_modes(invalid):
    for mode in ("workspace", "workspace_no_ask", "ask", "full"):
        assert (
            resolve_webchat_chat_options({"permission_mode": mode})["permission_mode"]
            == mode
        )
    assert (
        resolve_webchat_chat_options({"permission_mode": invalid})["permission_mode"]
        is None
    )


def test_each_message_sets_the_live_mode_and_one_without_it_clears_it():
    from astrbot.core.astr_agent_runtime.permission_mode import _conversation_modes

    try:
        event = _event({"permission_mode": "full"})
        assert _conversation_modes[event.session_id] == "full"
        assert _event({}).get_extra("permission_mode") is None
        assert event.session_id not in _conversation_modes
    finally:
        _conversation_modes.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("thread", [False, True])
async def test_deleting_a_conversation_forgets_its_live_mode(thread):
    from astrbot.core.astr_agent_runtime.permission_mode import (
        _conversation_modes,
        set_conversation_permission_mode,
    )

    service = object.__new__(ChatService)
    service.chat_runs_by_session = {}
    service.running_convs = {}
    service.conv_mgr = SimpleNamespace(delete_conversations_by_user_id=AsyncMock())
    service.platform_history_mgr = SimpleNamespace(
        get=AsyncMock(return_value=[]), delete=AsyncMock()
    )
    service.umop_config_router = SimpleNamespace(delete_route=AsyncMock())
    service.db = SimpleNamespace(
        delete_webchat_threads_by_parent_session=AsyncMock(return_value=[]),
        delete_platform_session=AsyncMock(),
    )
    set_conversation_permission_mode("webchat!alice!gone", "full")
    set_conversation_permission_mode("webchat!alice!keep", "full")
    try:
        if thread:
            await service.delete_threads_by_ids(["gone"], "alice")
        else:
            await service.delete_session_internal(
                SimpleNamespace(
                    session_id="gone", platform_id="webchat", is_group=False
                ),
                "alice",
            )
        assert "webchat!alice!gone" not in _conversation_modes
        assert _conversation_modes["webchat!alice!keep"] == "full"
    finally:
        _conversation_modes.clear()


# Thinking level on the options path.


@pytest.mark.parametrize("invalid", INVALID)
def test_resolver_keeps_only_valid_thinking_levels(invalid):
    assert (
        resolve_webchat_chat_options({"reasoning_effort": "low"})["reasoning_effort"]
        == "low"
    )
    assert (
        resolve_webchat_chat_options({"reasoning_effort": invalid})["reasoning_effort"]
        is None
    )


@pytest.mark.asyncio
async def test_thinking_level_reaches_the_provider_request():
    assert _event({"reasoning_effort": "xhigh"}).get_extra("reasoning_effort") is None
    event = _event({"reasoning_effort": "medium"})
    assert event.get_extra("reasoning_effort") == "medium"
    req, _ = await collect_initial_request(
        event,
        SimpleNamespace(),
        SimpleNamespace(provider_wake_prefix="", provider_settings={}),
    )
    assert req.reasoning_effort == "medium"


def test_request_models_reject_unknown_levels():
    with pytest.raises(ValidationError):
        ChatThreadMessageRequest(message="hi", reasoning_effort="xhigh")
