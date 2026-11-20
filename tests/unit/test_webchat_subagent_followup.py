"""A WebChat reply to delivered sub-agent results records those agents."""

from types import SimpleNamespace

import pytest

from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    streaming_response_event,
)
from astrbot.core.platform.sources.webchat import webchat_adapter
from astrbot.core.platform.sources.webchat.webchat_adapter import WebChatAdapter


def _event(cls, wakeup: bool):
    event = object.__new__(cls)
    event._extras = (
        {
            "_subagent_wakeup": ["webchat:FriendMessage:s", "c"],
            "_subagent_result_agents": ["aa11", "bb22"],
        }
        if wakeup
        else {"_subagent_result_agents": ["aa11"]}
    )
    event.message_str = "Review these delegated task results."
    return event


@pytest.fixture
def saved(monkeypatch, tmp_path):
    rows = []

    async def insert(**kwargs):
        rows.append(kwargs["content"])

    monkeypatch.setattr(
        webchat_adapter,
        "db_helper",
        SimpleNamespace(insert_platform_message_history=insert, insert_attachment=None),
    )
    adapter = object.__new__(WebChatAdapter)
    adapter.attachments_dir = tmp_path
    return adapter, rows


@pytest.mark.asyncio
async def test_subagent_wakeup_reply_records_the_delivered_agents(saved):
    adapter, rows = saved
    token = streaming_response_event.set(_event(AgentWakeupEvent, True))
    try:
        await adapter._save_proactive_message("s", MessageChain().message("done"))
    finally:
        streaming_response_event.reset(token)
    assert rows[0]["subagent_results"] == ["aa11", "bb22"]
    assert rows[0]["message"][0]["text"] == "done"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cls", "wakeup"),
    [
        (AgentWakeupEvent, False),  # scheduled task or plugin wake-up
        (AstrMessageEvent, True),  # not a wake-up event at all
        (None, False),  # plugin push outside any event
    ],
)
async def test_other_proactive_messages_stay_unmarked(saved, cls, wakeup):
    adapter, rows = saved
    token = streaming_response_event.set(_event(cls, wakeup) if cls else None)
    try:
        await adapter._save_proactive_message("s", MessageChain().message("hi"))
    finally:
        streaming_response_event.reset(token)
    assert "subagent_results" not in rows[0]
