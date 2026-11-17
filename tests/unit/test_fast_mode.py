"""ChatUI fast mode: request option, provider support and request fields."""

from types import SimpleNamespace

import pytest

from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
from astrbot.core.platform.sources.webchat.request_flags import (
    resolve_webchat_chat_options,
)
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.provider.sources.anthropic_source import ProviderAnthropic
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from tests.unit.test_reasoning_effort_override import (
    CHAT_CONFIG,
    _chunk,
    _completion,
)


@pytest.mark.parametrize(
    ("value", "expected"), [(True, True), (False, None), ("true", None), (1, None)]
)
def test_fast_mode_option_accepts_only_true(value, expected):
    assert resolve_webchat_chat_options({"fast_mode": value})["fast_mode"] is expected


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("api_base", "fast", "tier"),
    [
        ("https://api.openai.com/v1", True, "priority"),
        ("https://api.openai.com/v1", False, None),
        ("https://api.x.ai/v1", True, "priority"),
        ("https://openrouter.ai/api/v1", True, "priority"),
        ("https://api.openai.com.example/v1", True, None),
        ("https://proxy.example/api.openai.com", True, None),
        ("https://api.openai.com@proxy.example/v1", True, None),
        ("https://proxy.example.com/v1", True, None),  # gateways may reject it
    ],
)
async def test_chat_completions_fast_mode_uses_priority_tier_on_official_hosts(
    monkeypatch, stream, api_base, fast, tier
):
    provider = ProviderOpenAIOfficial({**CHAT_CONFIG, "api_base": api_base}, {})
    captured: dict = {}

    async def chunks():
        yield _chunk()

    async def create(**kwargs):
        captured.update(kwargs)
        return chunks() if stream else _completion()

    monkeypatch.setattr(provider.client.chat.completions, "create", create)
    try:
        assert provider.supports_fast_mode() is (tier is not None or not fast)
        if stream:
            async for _ in provider.text_chat_stream(prompt="hi", fast_mode=fast):
                pass
        else:
            await provider.text_chat(prompt="hi", fast_mode=fast)
        extra_body = captured.get("extra_body") or {}
        assert (captured.get("service_tier") or extra_body.get("service_tier")) == tier
        assert "fast_mode" not in captured and "fast_mode" not in extra_body
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    ("model", "api_base", "speed"),
    [
        ("claude-opus-5-5", "https://api.anthropic.com", "fast"),
        ("claude-fable-5-2", "https://api.anthropic.com", "fast"),
        # No fast mode on these models: the API would reject the field.
        ("claude-sonnet-5-5", "https://api.anthropic.com", None),
        ("claude-opus-5-50", "https://api.anthropic.com", None),
        ("claude-opus-5-5", "https://api.anthropic.com.example/v1", None),
        ("claude-opus-5-5", "https://proxy.example/api.anthropic.com", None),
    ],
)
async def test_anthropic_fast_mode_only_for_offered_models_on_the_official_api(
    stream, model, api_base, speed
):
    provider = ProviderAnthropic(
        {
            "id": "anthropic-test",
            "type": "anthropic_chat_completion",
            "model": model,
            "key": ["test-key"],
            "api_base": api_base,
        },
        {},
    )
    captured: dict = {}

    async def query(payloads, tools, **kwargs):
        captured.update(payloads)
        return SimpleNamespace(role="assistant")

    async def query_stream(payloads, tools, **kwargs):
        captured.update(payloads)
        yield SimpleNamespace(role="assistant")

    provider._query = query
    provider._query_stream = query_stream
    try:
        assert provider.supports_fast_mode() is (speed is not None)
        if stream:
            async for _ in provider.text_chat_stream(prompt="hi", fast_mode=True):
                pass
        else:
            await provider.text_chat(prompt="hi", fast_mode=True)
        assert captured.get("speed") == speed
    finally:
        await provider.terminate()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("include_model", "supported", "expected"),
    [(True, True, True), (False, True, None), (True, False, None)],
)
async def test_runner_sends_fast_mode_only_to_a_supporting_primary_provider(
    include_model, supported, expected
):
    received: dict = {}

    async def recorded_responses(payload, **_kwargs):
        received.update(payload)
        yield SimpleNamespace(role="assistant")

    runner = object.__new__(ToolLoopAgentRunner)
    runner.req = ProviderRequest(model="m", fast_mode=True)
    runner.provider = SimpleNamespace(supports_fast_mode=lambda model: supported)
    runner.run_context = SimpleNamespace(messages=[])
    runner.streaming = False
    runner._abort_signal = None
    runner.request_max_retries = None
    runner._sanitize_contexts_for_provider = lambda messages: messages
    runner._func_tool_for_provider = lambda: None
    runner._recorded_responses = recorded_responses

    async for _ in runner._iter_llm_responses(include_model=include_model):
        pass

    assert received.get("fast_mode") is expected


def test_provider_list_marks_providers_that_support_fast_mode():
    from astrbot.dashboard.services.config_service import ProviderConfigService

    openai = ProviderOpenAIOfficial(CHAT_CONFIG, {})
    proxy = ProviderOpenAIOfficial(
        {**CHAT_CONFIG, "id": "proxy", "api_base": "https://proxy.example/v1"}, {}
    )
    service = object.__new__(ProviderConfigService)
    service.provider_manager = SimpleNamespace(
        provider_sources_config=[],
        providers_config=[
            {**CHAT_CONFIG, "provider_type": "chat_completion", "enable": True},
            {
                **CHAT_CONFIG,
                "id": "proxy",
                "provider_type": "chat_completion",
                "enable": True,
            },
        ],
        inst_map={"test-openai": openai, "proxy": proxy},
    )
    providers = service.list_providers(capability="chat_completion")["providers"]
    assert {p["id"]: p.get("supports_fast_mode") for p in providers} == {
        "test-openai": True,
        "proxy": None,
    }
