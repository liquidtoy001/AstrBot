from types import SimpleNamespace

import pytest

from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.provider.entities import LLMResponse
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError


def _history(rounds):
    messages = []
    for i in range(rounds):
        messages.append({"role": "user", "content": f"question {i} " * 30})
        messages.append({"role": "assistant", "content": f"answer {i} " * 30})
    return messages


class _Store:
    def __init__(self, messages, conflict=False):
        self.snapshot = SimpleNamespace(
            messages=messages,
            revision=SimpleNamespace(head_seq=7, leaf_event_id="leaf"),
        )
        self.conflict = conflict
        self.appended = None

    async def read(self, cid):
        return self.snapshot

    async def append(self, cid, drafts, **kwargs):
        if self.conflict:
            raise ConversationConflictError("changed")
        self.appended = (cid, drafts, kwargs)


class _Provider:
    def __init__(self, text="short summary"):
        self.text = text
        self.provider_config = {"id": "p1", "modalities": ["text"]}

    def get_model(self):
        return "m1"

    async def text_chat(self, **kwargs):
        return LLMResponse(role="assistant", completion_text=self.text)


def _service(store, provider=None, running=False):
    service = object.__new__(ChatService)
    service.db = SimpleNamespace(
        conversation_store=store,
        get_platform_session_by_id=_session,
    )
    task = SimpleNamespace(done=lambda: not running)
    service.chat_runs = {"r1": SimpleNamespace(task=task)}
    service.chat_runs_by_session = {"s1": {"r1"}}

    async def using(provider_type, umo):
        return provider or _Provider()

    service.core_lifecycle = SimpleNamespace(
        conversation_manager=SimpleNamespace(get_curr_conversation_id=_cid),
        astrbot_config_mgr=SimpleNamespace(
            get_conf=lambda umo: {"agent": {"config": {"compression": {}}}}
        ),
        provider_manager=SimpleNamespace(inst_map={}, get_using_provider_async=using),
    )
    return service


async def _session(session_id):
    return SimpleNamespace(
        creator="alice", is_group=False, platform_id="webchat", session_id="s1"
    )


async def _cid(umo):
    return "c1"


@pytest.mark.asyncio
async def test_compact_keeps_latest_round_and_writes_with_revision_check():
    store = _Store(_history(4))
    result = await _service(store).compact_session("alice", "s1")
    assert result["after"] < result["before"]
    cid, drafts, kwargs = store.appended
    assert cid == "c1"
    assert kwargs["reason"] == "compaction"
    assert kwargs["expected_head"] == 7
    assert kwargs["expected_leaf"] == "leaf"
    assert drafts[0]["payload"]["token_usage"] == 0
    history = kwargs["history"]
    assert "short summary" in history[0]["content"]
    # The latest complete round is kept word for word.
    assert history[-2:] == _history(4)[-2:]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("store", "provider", "running"),
    [
        (_Store(_history(1)), None, False),  # too short
        (_Store(_history(4)), None, True),  # reply running
        (_Store(_history(4)), _Provider(text=""), False),  # empty summary
        (_Store(_history(4)), _Provider(text="x " * 5000), False),  # not smaller
        (_Store(_history(4), conflict=True), None, False),  # changed meanwhile
    ],
)
async def test_compact_refuses_without_changing_history(store, provider, running):
    with pytest.raises(ChatServiceError):
        await _service(store, provider, running).compact_session("alice", "s1")
    assert store.appended is None


@pytest.mark.asyncio
async def test_compact_uses_configured_summary_provider():
    from unittest.mock import AsyncMock

    store = _Store(_history(4))
    service = _service(store)
    summary = _Provider("configured summary")
    summary.text_chat = AsyncMock(wraps=summary.text_chat)
    service.core_lifecycle.astrbot_config_mgr.get_conf = lambda umo: {
        "agent": {"config": {"compression": {"provider_id": "summary"}}}
    }
    service.core_lifecycle.provider_manager.inst_map["summary"] = summary
    fallback = AsyncMock(side_effect=AssertionError("must use configured compressor"))
    service.core_lifecycle.provider_manager.get_using_provider_async = fallback
    await service.compact_session("alice", "s1")
    summary.text_chat.assert_awaited_once()
    fallback.assert_not_awaited()
    assert "configured summary" in store.appended[2]["history"][0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("registration", ["event", "agent_callback"])
async def test_compact_refuses_active_non_sse_execution(registration):
    from astrbot.core.utils.active_event_registry import active_event_registry

    store = _Store(_history(4))
    service = _service(store)
    scope = await service._owned_scope("alice", "s1")

    class Event:
        unified_msg_origin = scope.umo

        def get_extra(self, key):
            return None

        def set_extra(self, key, value):
            pass

    event = Event()

    def callback():
        return None

    if registration == "event":
        active_event_registry.register(event)
    else:
        active_event_registry.register_agent_stop_callback(event, callback)
    try:
        with pytest.raises(ChatServiceError, match="still running"):
            await service.compact_session("alice", "s1")
        assert store.appended is None
    finally:
        if registration == "event":
            active_event_registry.unregister(event)
        else:
            active_event_registry.unregister_agent_stop_callback(event, callback)


@pytest.mark.asyncio
async def test_compact_refuses_when_a_run_starts_during_the_summary():
    """A run that starts while the summary is generated keeps the old history."""
    from astrbot.core.utils.active_event_registry import active_event_registry

    store = _Store(_history(4))
    scope_umo = []

    class Event:
        def __init__(self, umo):
            self.unified_msg_origin = umo

        def get_extra(self, key):
            return None

        def set_extra(self, key, value):
            pass

    events = []

    class StartsARun(_Provider):
        async def text_chat(self, **kwargs):
            # A message arrives while the summary is being generated.
            event = Event(scope_umo[0])
            active_event_registry.register(event)
            events.append(event)
            return await super().text_chat(**kwargs)

    service = _service(store, StartsARun())
    scope_umo.append((await service._owned_scope("alice", "s1")).umo)
    try:
        with pytest.raises(ChatServiceError, match="still running"):
            await service.compact_session("alice", "s1")
        assert store.appended is None
    finally:
        for event in events:
            active_event_registry.unregister(event)
