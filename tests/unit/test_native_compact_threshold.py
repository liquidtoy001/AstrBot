from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.astr_agent_runtime import execution
from astrbot.core.astr_agent_runtime.main_agent import providers
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import llm_metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("threshold", "is_subagent", "expected"),
    [
        (None, False, 0),
        (400_000, False, 400_000),
        (5_000_000, False, 1_000_000),
        (400_000, True, 0),
        (True, False, 0),
        (4_000, False, 200_000),
    ],
)
async def test_chatui_compact_threshold(monkeypatch, threshold, is_subagent, expected):
    monkeypatch.setitem(
        llm_metadata.LLM_METADATAS, "big-model", {"limit": {"context": 1_000_000}}
    )
    monkeypatch.setattr(
        providers, "resolve_compression_provider", AsyncMock(return_value=None)
    )
    reset = AsyncMock()
    monkeypatch.setattr(ToolLoopAgentRunner, "reset", reset)
    provider = SimpleNamespace(
        provider_config={"id": "p1"}, get_model=lambda: "big-model"
    )
    config = SimpleNamespace(
        fallback_max_context_tokens=128_000,
        context_limit_reached_strategy="truncate_by_turns",
        tool_call_timeout=60,
        streaming_response=False,
        llm_compress_instruction="",
        llm_compress_keep_recent_ratio=0.15,
        dequeue_context_length=1,
        max_context_length=-1,
        tool_schema_mode="full",
        request_max_retries=1,
    )
    event = SimpleNamespace(
        get_extra=lambda key: threshold if key == "compact_threshold" else None
    )
    await execution.create_native_runner(
        SimpleNamespace(),
        provider,
        ProviderRequest(prompt="hi"),
        config,
        SimpleNamespace(event=event, is_subagent=is_subagent),
        fallback_providers=[],
    )
    assert reset.call_args.kwargs["compress_trigger_tokens"] == expected
