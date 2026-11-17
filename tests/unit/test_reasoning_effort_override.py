"""Per-request reasoning effort override (ChatUI thinking level)."""

from types import SimpleNamespace

import pytest
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_chunk import ChatCompletionChunk
from openai.types.responses import Response

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.sources.openai_responses_source import (
    ProviderOpenAIResponses,
)
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial

CHAT_CONFIG = {
    "id": "test-openai",
    "type": "openai_chat_completion",
    "model": "gpt-test",
    "key": ["test-key"],
    "api_base": "https://api.openai.com/v1",
    "custom_extra_body": {"reasoning_effort": "high", "temperature": 0.1},
}


def _completion() -> ChatCompletion:
    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
    )


def _chunk() -> ChatCompletionChunk:
    return ChatCompletionChunk.model_validate(
        {
            "id": "chatcmpl-stream",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": "gpt-test",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("override", "expected"), [("low", "low"), (None, "high")])
async def test_chat_completions_text_chat_override(monkeypatch, override, expected):
    provider = ProviderOpenAIOfficial(dict(CHAT_CONFIG), {})
    try:
        captured: dict = {}

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return _completion()

        monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
        kwargs = {"reasoning_effort": override} if override else {}
        await provider.text_chat(prompt="hi", **kwargs)

        assert captured["extra_body"]["reasoning_effort"] == expected
        assert captured["extra_body"]["temperature"] == 0.1
        assert "reasoning_effort" not in captured
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_chat_completions_stream_override_wins_over_config(monkeypatch):
    provider = ProviderOpenAIOfficial(dict(CHAT_CONFIG), {})
    try:
        captured: dict = {}

        async def fake_stream():
            yield _chunk()

        async def fake_create(**kwargs):
            captured.update(kwargs)
            return fake_stream()

        monkeypatch.setattr(provider.client.chat.completions, "create", fake_create)
        async for _ in provider.text_chat_stream(prompt="hi", reasoning_effort="low"):
            pass

        assert captured["extra_body"]["reasoning_effort"] == "low"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_override_keeps_other_reasoning_options(monkeypatch):
    provider = ProviderOpenAIResponses(
        {
            "id": "test-responses",
            "provider": "openai",
            "type": "openai_responses",
            "model": "gpt-test",
            "key": ["test-key"],
            "api_base": "https://api.openai.com/v1",
            "custom_extra_body": {"reasoning": {"effort": "high", "summary": "auto"}},
        },
        {},
    )
    captured: dict = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return Response.model_validate(
            {
                "id": "resp_1",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-test",
                "output": [
                    {
                        "id": "m1",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "ok", "annotations": []}
                        ],
                    }
                ],
                "parallel_tool_calls": True,
                "tool_choice": "auto",
                "tools": [],
            }
        )

    monkeypatch.setattr(provider.client.responses, "create", fake_create)
    payloads = {"model": "gpt-test", "input": "hi", "store": False}
    try:
        result = await provider._query(dict(payloads), None, reasoning_effort="low")
        assert result.completion_text == "ok"
        assert captured["extra_body"]["reasoning"] == {
            "effort": "low",
            "summary": "auto",
        }
        captured.clear()
        result = await provider._query(dict(payloads), None)
        assert result.completion_text == "ok"
        assert captured["extra_body"]["reasoning"] == {
            "effort": "high",
            "summary": "auto",
        }
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("include_model", [True, False])
async def test_runner_sends_effort_only_to_primary_provider(include_model):
    received: dict = {}

    async def recorded_responses(payload, **_kwargs):
        received.update(payload)
        yield SimpleNamespace(role="assistant")

    runner = object.__new__(ToolLoopAgentRunner)
    runner.req = ProviderRequest(model="m", reasoning_effort="medium")
    runner.run_context = SimpleNamespace(messages=[])
    runner.streaming = False
    runner._abort_signal = None
    runner.request_max_retries = None
    runner._sanitize_contexts_for_provider = lambda messages: messages
    runner._func_tool_for_provider = lambda: None
    runner._recorded_responses = recorded_responses

    async for _ in runner._iter_llm_responses(include_model=include_model):
        pass

    if include_model:
        assert received["reasoning_effort"] == "medium"
    else:
        assert "reasoning_effort" not in received


@pytest.mark.parametrize(
    ("thinking_config", "expected_thinking", "expected_output"),
    [
        ({}, {"type": "enabled", "budget_tokens": 2048}, None),
        ({"budget": 30000}, {"type": "enabled", "budget_tokens": 2048}, None),
        ({"type": "adaptive", "effort": "high"}, {"type": "adaptive"}, "low"),
    ],
)
def test_anthropic_maps_effort_by_thinking_mode(
    thinking_config, expected_thinking, expected_output
):
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic.__new__(ProviderAnthropic)
    provider.thinking_config = thinking_config
    payloads = {"max_tokens": 65536}

    payloads["_reasoning_effort"] = "low"
    provider._apply_thinking_config(payloads)

    assert payloads["thinking"] == expected_thinking
    assert payloads.get("output_config", {}).get("effort") == expected_output
    assert "_reasoning_effort" not in payloads


def test_anthropic_budget_stays_below_max_tokens():
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic.__new__(ProviderAnthropic)
    provider.thinking_config = {}
    payloads = {"max_tokens": 4096}

    payloads["_reasoning_effort"] = "high"
    provider._apply_thinking_config(payloads)

    assert payloads["thinking"]["budget_tokens"] == 2048


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("gemini-3.7-flash", {"thinking_level": "LOW"}),
        ("gemini-4-neon", {"thinking_level": "LOW"}),
        ("gemini-2.5-flash", {"thinking_budget": 1024}),
    ],
)
async def test_gemini_maps_effort_to_level_or_budget(model, expected):
    from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI

    provider = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    provider.provider_config = {"gm_thinking_config": {"level": "HIGH", "budget": 0}}
    provider.provider_settings = {}
    provider.model_name = model
    provider.safety_settings = []

    config = await provider._prepare_query_config(
        {"model": model}, reasoning_effort="low"
    )

    dumped = config.thinking_config.model_dump(exclude_none=True, mode="json")
    assert dumped == expected


@pytest.mark.asyncio
async def test_unexpected_plugin_effort_does_not_fail_the_request():
    """on_llm_request may set any value; budget models fall back to high."""
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
    from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI

    anthropic = ProviderAnthropic.__new__(ProviderAnthropic)
    anthropic.thinking_config = {}
    payloads = {"model": "kimi-for-coding", "max_tokens": 65536}
    payloads["_reasoning_effort"] = "xhigh"
    anthropic._apply_thinking_config(payloads)
    assert payloads["thinking"] == {"type": "enabled", "budget_tokens": 16384}

    gemini = ProviderGoogleGenAI.__new__(ProviderGoogleGenAI)
    gemini.provider_config = {"gm_thinking_config": {"budget": 0}}
    gemini.provider_settings = {}
    gemini.model_name = "gemini-2.5-flash"
    gemini.safety_settings = []
    config = await gemini._prepare_query_config(
        {"model": "gemini-2.5-flash"}, reasoning_effort="xhigh"
    )
    assert config.thinking_config.thinking_budget == 24576


@pytest.mark.parametrize(
    ("model", "adaptive"),
    [
        ("claude-haiku-5-5", True),
        ("claude-opus-5-5", True),
        ("claude-sonnet-4-6", True),
        ("anthropic/claude-fable-5-2", True),
        ("claude-haiku-4-5", False),
        ("anthropic/claude-sonnet-4.5", False),
        ("claude-sonnet-4-5-latest", False),
        ("claude-opus-4.1", False),
        ("claude-sonnet-4.6", True),
        ("claude-opus-4-1-20250805", False),
        ("claude-sonnet-4-20250514", False),
        ("claude-3-7-sonnet-latest", False),
        ("kimi-for-coding", False),
    ],
)
def test_anthropic_effort_uses_adaptive_on_new_claude_models(model, adaptive):
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic.__new__(ProviderAnthropic)
    provider.thinking_config = {"budget": 4096}
    payloads = {"model": model, "max_tokens": 65536}

    payloads["_reasoning_effort"] = "medium"
    provider._apply_thinking_config(payloads)

    if adaptive:
        assert payloads["thinking"] == {"type": "adaptive"}
        assert payloads["output_config"]["effort"] == "medium"
    else:
        assert payloads["thinking"] == {"type": "enabled", "budget_tokens": 8192}
        assert "output_config" not in payloads


@pytest.mark.parametrize("max_tokens", [1024, 1025])
def test_anthropic_small_output_budget_is_valid(max_tokens):
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic

    provider = ProviderAnthropic.__new__(ProviderAnthropic)
    provider.thinking_config = {}
    payloads = {"model": "kimi-for-coding", "max_tokens": max_tokens}
    payloads["_reasoning_effort"] = "high"
    provider._apply_thinking_config(payloads)

    assert payloads["max_tokens"] == max_tokens
    if max_tokens <= 1024:
        assert "thinking" not in payloads
    else:
        assert 1024 <= payloads["thinking"]["budget_tokens"] < max_tokens


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_kind", ["anthropic", "gemini"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_provider_entrypoints_forward_reasoning_effort(
    monkeypatch, provider_kind, streaming
):
    from astrbot.core.provider.entities import LLMResponse
    from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
    from astrbot.core.provider.sources.gemini_source import ProviderGoogleGenAI

    cls = ProviderAnthropic if provider_kind == "anthropic" else ProviderGoogleGenAI
    provider = cls(
        {
            "id": "test",
            "api_base": "https://api.anthropic.com"
            if provider_kind == "anthropic"
            else "https://generativelanguage.googleapis.com",
            "model": "claude-opus-5-5"
            if provider_kind == "anthropic"
            else "gemini-2.5-flash",
            "key": ["test-key"],
        },
        {},
    )
    seen = []

    async def query(payload, tools, **kwargs):
        seen.append((payload, kwargs))
        return LLMResponse(role="assistant", completion_text="done")

    async def stream(payload, tools, **kwargs):
        yield await query(payload, tools, **kwargs)

    monkeypatch.setattr(provider, "_query", query)
    monkeypatch.setattr(provider, "_query_stream", stream)
    try:
        if streaming:
            results = [
                item
                async for item in provider.text_chat_stream(
                    prompt="hello", reasoning_effort="medium"
                )
            ]
        else:
            results = [
                await provider.text_chat(prompt="hello", reasoning_effort="medium")
            ]
        assert results[-1].completion_text == "done"
        assert len(seen) == 1 and seen[0][1]["reasoning_effort"] == "medium"
    finally:
        await provider.terminate()


@pytest.mark.asyncio
async def test_responses_stream_preserves_reasoning_configuration(monkeypatch):
    provider = ProviderOpenAIResponses(
        {
            **CHAT_CONFIG,
            "type": "openai_responses",
            "custom_extra_body": {"reasoning": {"effort": "high", "summary": "auto"}},
        },
        {},
    )
    captured = []

    async def stream():
        yield {
            "type": "response.completed",
            "response": {
                "id": "r1",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
            },
        }

    async def create(**kwargs):
        captured.append(kwargs)
        return stream()

    monkeypatch.setattr(provider.client.responses, "create", create)
    try:
        for effort in ("low", None):
            results = [
                item
                async for item in provider._query_stream(
                    {"model": "test", "input": "hello"}, None, reasoning_effort=effort
                )
            ]
            assert results[-1].completion_text == "ok"
        assert [call["extra_body"]["reasoning"] for call in captured] == [
            {"effort": "low", "summary": "auto"},
            {"effort": "high", "summary": "auto"},
        ]
        assert (
            provider.provider_config["custom_extra_body"]["reasoning"]["effort"]
            == "high"
        )
    finally:
        await provider.terminate()
