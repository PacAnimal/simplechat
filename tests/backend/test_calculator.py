import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.tools.calculator import calculate


# ---- calculator tool unit tests ----

def test_addition():
    r = calculate("2 + 2")
    assert r["result"] == 4
    assert "4" in r["text"]
    assert "2 + 2" in r["text"]


def test_subtraction():
    assert calculate("10 - 3")["result"] == 7


def test_multiplication():
    assert calculate("6 * 7")["result"] == 42


def test_division():
    assert calculate("15 / 4")["result"] == 3.75


def test_floor_division():
    assert calculate("15 // 4")["result"] == 3


def test_modulo():
    assert calculate("17 % 5")["result"] == 2


def test_power():
    assert calculate("2 ** 10")["result"] == 1024


def test_negative_unary():
    assert calculate("-5 + 3")["result"] == -2


def test_compound_expression():
    assert calculate("(3 + 4) * 2 - 1")["result"] == 13


def test_sqrt():
    assert calculate("sqrt(144)")["result"] == 12.0


def test_cbrt():
    r = calculate("cbrt(27)")
    assert abs(r["result"] - 3.0) < 1e-10


def test_sin():
    r = calculate("sin(pi / 2)")
    assert abs(r["result"] - 1.0) < 1e-10


def test_cos():
    r = calculate("cos(0)")
    assert abs(r["result"] - 1.0) < 1e-10


def test_tan():
    r = calculate("tan(0)")
    assert abs(r["result"] - 0.0) < 1e-10


def test_log_natural():
    r = calculate("log(e)")
    assert abs(r["result"] - 1.0) < 1e-10


def test_log10():
    r = calculate("log10(1000)")
    assert abs(r["result"] - 3.0) < 1e-10


def test_log2():
    r = calculate("log2(8)")
    assert abs(r["result"] - 3.0) < 1e-10


def test_exp():
    r = calculate("exp(0)")
    assert abs(r["result"] - 1.0) < 1e-10


def test_factorial():
    assert calculate("factorial(5)")["result"] == 120


def test_factorial_zero():
    assert calculate("factorial(0)")["result"] == 1


def test_abs_negative():
    assert calculate("abs(-42)")["result"] == 42


def test_ceil():
    assert calculate("ceil(3.2)")["result"] == 4


def test_floor():
    assert calculate("floor(3.8)")["result"] == 3


def test_round_half():
    assert calculate("round(2.5)")["result"] in (2, 3)  # banker's rounding


def test_degrees():
    r = calculate("degrees(pi)")
    assert abs(r["result"] - 180.0) < 1e-10


def test_radians():
    r = calculate("radians(180)")
    assert abs(r["result"] - math.pi) < 1e-10


def test_hypot():
    r = calculate("hypot(3, 4)")
    assert abs(r["result"] - 5.0) < 1e-10


def test_constant_pi():
    r = calculate("pi")
    assert abs(r["result"] - math.pi) < 1e-10


def test_constant_e():
    r = calculate("e")
    assert abs(r["result"] - math.e) < 1e-10


def test_constant_tau():
    r = calculate("tau")
    assert abs(r["result"] - math.tau) < 1e-10


def test_division_by_zero():
    r = calculate("1 / 0")
    assert "error" in r
    assert "zero" in r["error"].lower()
    assert "text" in r


def test_invalid_syntax():
    r = calculate("2 +* 3")
    assert "error" in r


def test_unknown_function_blocked():
    r = calculate("__import__('os')")
    assert "error" in r


def test_attribute_access_blocked():
    r = calculate("math.sqrt(4)")
    assert "error" in r


def test_unknown_name_blocked():
    r = calculate("evil_var + 1")
    assert "error" in r


def test_string_literal_blocked():
    r = calculate("'hello'")
    assert "error" in r


def test_empty_expression():
    r = calculate("")
    assert "error" in r


def test_integer_result_drops_dot_zero():
    # sqrt(4) = 2.0 but should format as "2", not "2.0"
    r = calculate("sqrt(4)")
    assert r["text"].endswith("= 2")


def test_float_result_preserved():
    r = calculate("1 / 3")
    assert r["result"] == pytest.approx(0.3333, abs=1e-4)


# ---- OpenAI provider: calculator tool call ----

@pytest.mark.asyncio
async def test_openai_calculator_tool_call():
    """OpenAI provider routes calculate tool call through execute_tool and returns result."""
    from backend.providers.openai_provider import OpenAIProvider

    tc_chunk = MagicMock()
    tc_chunk.choices = [MagicMock()]
    tc_chunk.choices[0].delta.content = None
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "call_calc_1"
    tc_delta.function.name = "calculate"
    tc_delta.function.arguments = '{"expression": "sqrt(144)"}'
    tc_chunk.choices[0].delta.tool_calls = [tc_delta]

    text_chunk = MagicMock()
    text_chunk.choices = [MagicMock()]
    text_chunk.choices[0].delta.content = "The square root of 144 is 12."
    text_chunk.choices[0].delta.tool_calls = None

    call_count = 0

    async def fake_create(**kwargs):
        nonlocal call_count
        call_count += 1

        async def gen1():
            yield tc_chunk

        async def gen2():
            yield text_chunk

        return gen1() if call_count == 1 else gen2()

    fake_result = {"result": 12.0, "expression": "sqrt(144)", "text": "sqrt(144) = 12"}

    provider = OpenAIProvider()
    with (
        patch.object(provider.client.chat.completions, "create", new=fake_create),
        patch("backend.providers.openai_provider._execute_tool", new=AsyncMock(return_value=fake_result)),
    ):
        events = []
        async for event in provider._stream([{"role": "user", "content": "What is sqrt(144)?"}], "gpt-4o", False):
            events.append(event)

    assert any(e["type"] == "tool_start" and e["name"] == "calculate" for e in events)
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert any("12" in e.get("content", "") for e in tool_results)
    assert any(e["type"] == "text_delta" for e in events)


@pytest.mark.asyncio
async def test_openai_calculator_tool_definition_included():
    """OpenAI provider must include CALCULATOR_TOOL in every request's tools list."""
    from backend.providers.openai_provider import OpenAIProvider

    text_chunk = MagicMock()
    text_chunk.choices = [MagicMock()]
    text_chunk.choices[0].delta.content = "ok"
    text_chunk.choices[0].delta.tool_calls = None

    captured_kwargs: list[dict] = []

    async def fake_create(**kwargs):
        captured_kwargs.append(kwargs)

        async def gen():
            yield text_chunk

        return gen()

    provider = OpenAIProvider()
    with patch.object(provider.client.chat.completions, "create", new=fake_create):
        async for _ in provider._stream([{"role": "user", "content": "hi"}], "gpt-4o", False):
            pass

    assert captured_kwargs
    tool_names = [t["function"]["name"] for t in captured_kwargs[0]["tools"] if t.get("type") == "function"]
    assert "calculate" in tool_names


# ---- Anthropic provider: calculator tool call ----

@pytest.mark.asyncio
async def test_anthropic_calculator_tool_call():
    """Anthropic provider routes calculate tool call through execute_tool and returns result."""
    from backend.providers.anthropic_provider import AnthropicProvider

    def make_tool_events():
        # note: MagicMock(name=...) sets the mock's repr name, not a .name attribute
        # so we set .name explicitly after construction
        blk = MagicMock()
        blk.type = "tool_use"
        blk.id = "tc_calc_1"
        blk.name = "calculate"
        return [
            MagicMock(type="content_block_start", content_block=blk),
            MagicMock(type="content_block_delta", delta=MagicMock(
                type="input_json_delta", partial_json='{"expression": "factorial(5)"}',
            )),
            MagicMock(type="content_block_stop"),
        ]

    def make_text_events():
        return [
            MagicMock(type="content_block_start", content_block=MagicMock(type="text", id="blk_1")),
            MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="5! is 120.")),
            MagicMock(type="content_block_stop"),
        ]

    async def async_iter(items):
        for item in items:
            yield item

    def make_mock_stream(events_fn):
        ms = AsyncMock()
        ms.__aenter__ = AsyncMock(return_value=ms)
        ms.__aexit__ = AsyncMock(return_value=False)
        ms.__aiter__ = lambda self: async_iter(events_fn())
        return ms

    fake_result = {"result": 120, "expression": "factorial(5)", "text": "factorial(5) = 120"}

    event_fns = [make_tool_events, make_text_events]
    fn_iter = iter(event_fns)

    provider = AnthropicProvider()
    with (
        patch.object(provider.client.messages, "stream", side_effect=lambda **kw: make_mock_stream(next(fn_iter))),
        patch("backend.providers.anthropic_provider._execute_tool", new=AsyncMock(return_value=fake_result)),
    ):
        events = []
        async for event in provider._stream([{"role": "user", "content": "What is 5!?"}], "claude-sonnet-4-6", False):
            events.append(event)

    assert any(e["type"] == "tool_start" and e["name"] == "calculate" for e in events)
    tool_results = [e for e in events if e["type"] == "tool_result"]
    assert any("120" in e.get("content", "") for e in tool_results)
    assert any(e["type"] == "text_delta" for e in events)


@pytest.mark.asyncio
async def test_anthropic_calculator_tool_definition_included():
    """Anthropic provider must pass calculator tool in every request."""
    from backend.providers.anthropic_provider import AnthropicProvider

    def make_text_events():
        return [
            MagicMock(type="content_block_start", content_block=MagicMock(type="text", id="blk_0")),
            MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="ok")),
            MagicMock(type="content_block_stop"),
        ]

    async def async_iter(items):
        for item in items:
            yield item

    captured_kwargs: list[dict] = []

    def make_mock_stream(**kwargs):
        captured_kwargs.append(kwargs)
        ms = AsyncMock()
        ms.__aenter__ = AsyncMock(return_value=ms)
        ms.__aexit__ = AsyncMock(return_value=False)
        ms.__aiter__ = lambda self: async_iter(make_text_events())
        return ms

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", side_effect=make_mock_stream):
        async for _ in provider._stream([{"role": "user", "content": "hi"}], "claude-sonnet-4-6", False):
            pass

    assert captured_kwargs
    tool_names = [t["name"] for t in captured_kwargs[0]["tools"] if "name" in t]
    assert "calculate" in tool_names


# ---- execute_tool dispatcher ----

@pytest.mark.asyncio
async def test_execute_tool_calculate():
    """execute_tool correctly dispatches to the calculator."""
    from backend.providers.base import execute_tool

    result = await execute_tool("calculate", {"expression": "2 ** 8"})
    assert result["result"] == 256
    assert "256" in result["text"]


@pytest.mark.asyncio
async def test_execute_tool_calculate_error_returned_not_raised():
    """execute_tool returns error dict for bad expressions instead of raising."""
    from backend.providers.base import execute_tool

    result = await execute_tool("calculate", {"expression": "1 / 0"})
    assert "error" in result
    assert "text" in result
