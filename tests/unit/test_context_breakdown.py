from astrbot.core.agent.context.token_counter import estimate_context_breakdown
from astrbot.core.agent.message import Message, TextPart, ThinkPart
from astrbot.core.agent.tool import FunctionTool, ToolSet


def test_estimate_context_breakdown_splits_components():
    tools = ToolSet(
        [
            FunctionTool(
                name="lookup",
                description="Look something up",
                parameters={"type": "object", "properties": {}},
            )
        ]
    )
    messages = [
        Message(role="system", content="You are a helpful assistant."),
        Message(role="user", content="hello there"),
        Message(
            role="assistant",
            content=[ThinkPart(think="let me think"), TextPart(text="hi")],
        ),
        Message(role="tool", content="result text", tool_call_id="1"),
    ]
    result = estimate_context_breakdown(messages, tools)
    assert result.pop("tool_count") == 1
    assert set(result) == {
        "system",
        "tools",
        "messages",
        "tool_results",
        "reasoning",
    }
    assert all(result[k] > 0 for k in result)


def test_estimate_context_breakdown_without_tools():
    result = estimate_context_breakdown([Message(role="user", content="hi there")])
    assert result["tools"] == 0
    assert result["system"] == 0
