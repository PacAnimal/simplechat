from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---- OpenAI provider ----


async def test_openai_stream_text():
    from backend.providers.openai_provider import OpenAIProvider

    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta.content = "Hello "
    chunk1.choices[0].delta.tool_calls = None

    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta.content = "world"
    chunk2.choices[0].delta.tool_calls = None

    async def fake_create(**kwargs):
        async def gen():
            yield chunk1
            yield chunk2

        return gen()

    provider = OpenAIProvider()
    with patch.object(provider.client.chat.completions, "create", new=fake_create):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Hi"}], "gpt-4o", False
        ):
            events.append(event)

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert text == "Hello world"


async def test_openai_stream_no_choices():
    from backend.providers.openai_provider import OpenAIProvider

    empty_chunk = MagicMock()
    empty_chunk.choices = []

    async def fake_create(**kwargs):
        async def gen():
            yield empty_chunk

        return gen()

    provider = OpenAIProvider()
    with patch.object(provider.client.chat.completions, "create", new=fake_create):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Hi"}], "gpt-4o", False
        ):
            events.append(event)

    assert events == []


async def test_openai_stream_image_tool():
    from backend.providers.openai_provider import OpenAIProvider

    # first chunk: tool call starts
    tc_chunk = MagicMock()
    tc_chunk.choices = [MagicMock()]
    tc_chunk.choices[0].delta.content = None
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "call_abc"
    tc_delta.function.name = "generate_image"
    tc_delta.function.arguments = '{"prompt":"a cat"}'
    tc_chunk.choices[0].delta.tool_calls = [tc_delta]

    # second chunk: continuation after tool
    text_chunk = MagicMock()
    text_chunk.choices = [MagicMock()]
    text_chunk.choices[0].delta.content = "Here you go!"
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

    fake_image_result = {
        "path": "/tmp/test.png",
        "url": "/api/generated/test.png",
        "prompt": "a cat",
        "text": "Image generated.",
    }

    provider = OpenAIProvider()
    with (
        patch.object(provider.client.chat.completions, "create", new=fake_create),
        patch(
            "backend.providers.openai_provider._execute_tool",
            new=AsyncMock(return_value=fake_image_result),
        ),
    ):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Draw a cat"}], "gpt-4o", False
        ):
            events.append(event)

    assert any(e["type"] == "tool_start" for e in events)
    assert any(e["type"] == "image_generated" for e in events)
    assert any(e["type"] == "text_delta" for e in events)


# ---- Anthropic provider ----


async def test_anthropic_stream_text():
    from backend.providers.anthropic_provider import AnthropicProvider

    # build mock streaming context
    events_sequence = [
        MagicMock(
            type="content_block_start", content_block=MagicMock(type="text", id="blk_0")
        ),
        MagicMock(
            type="content_block_delta", delta=MagicMock(type="text_delta", text="Hello")
        ),
        MagicMock(
            type="content_block_delta",
            delta=MagicMock(type="text_delta", text=" world"),
        ),
        MagicMock(type="content_block_stop"),
        MagicMock(type="message_stop"),
    ]

    async def async_iter(items):
        for item in items:
            yield item

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.__aiter__ = lambda self: async_iter(events_sequence)
    mock_stream.get_final_message = AsyncMock(
        return_value=MagicMock(stop_reason="end_turn", content=[])
    )

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", return_value=mock_stream):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Hi"}], "claude-sonnet-4-6", False
        ):
            events.append(event)

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert text == "Hello world"


async def test_anthropic_stream_web_search_event():
    from backend.providers.anthropic_provider import AnthropicProvider

    events_sequence = [
        MagicMock(
            type="content_block_start",
            content_block=MagicMock(
                type="server_tool_use", id="srv_0", name="web_search"
            ),
        ),
        MagicMock(type="content_block_stop"),
        MagicMock(
            type="content_block_start", content_block=MagicMock(type="text", id="blk_1")
        ),
        MagicMock(
            type="content_block_delta",
            delta=MagicMock(type="text_delta", text="Result!"),
        ),
        MagicMock(type="content_block_stop"),
    ]

    async def async_iter(items):
        for item in items:
            yield item

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.__aiter__ = lambda self: async_iter(events_sequence)
    mock_stream.get_final_message = AsyncMock(
        return_value=MagicMock(stop_reason="end_turn", content=[])
    )

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", return_value=mock_stream):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Search for X"}], "claude-sonnet-4-6", True
        ):
            events.append(event)

    assert any(e["type"] == "searching" for e in events)
    assert any(e["type"] == "text_delta" for e in events)


# ---- Optional API key guard ----


async def test_openai_provider_raises_without_key():
    import backend.providers.openai_provider as m

    original = m.settings.openai_api_key
    m.settings.openai_api_key = None
    try:
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            m.OpenAIProvider()
    finally:
        m.settings.openai_api_key = original


async def test_anthropic_provider_raises_without_key():
    import backend.providers.anthropic_provider as m

    original = m.settings.anthropic_api_key
    m.settings.anthropic_api_key = None
    try:
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            m.AnthropicProvider()
    finally:
        m.settings.anthropic_api_key = original


async def test_anthropic_unknown_block_type_does_not_corrupt_output():
    """Unknown content_block_start type must be silently ignored, not re-append the previous block."""
    from backend.providers.anthropic_provider import AnthropicProvider

    events_sequence = [
        MagicMock(
            type="content_block_start", content_block=MagicMock(type="text", id="blk_0")
        ),
        MagicMock(
            type="content_block_delta", delta=MagicMock(type="text_delta", text="Hello")
        ),
        MagicMock(type="content_block_stop"),
        # unknown block type — must reset current_block to None
        MagicMock(
            type="content_block_start",
            content_block=MagicMock(type="future_block_type", id="blk_1"),
        ),
        MagicMock(
            type="content_block_delta",
            delta=MagicMock(type="text_delta", text="IGNORED"),
        ),
        MagicMock(type="content_block_stop"),
    ]

    async def async_iter(items):
        for item in items:
            yield item

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.__aiter__ = lambda self: async_iter(events_sequence)

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", return_value=mock_stream):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Hi"}], "claude-sonnet-4-6", False
        ):
            events.append(event)

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    # should only see "Hello", not "IGNORED" (unknown delta type) or a duplicated "Hello"
    assert text == "Hello"


# ---- Max tool iterations ----


async def test_openai_stream_max_iterations_guard():
    """Provider must stop after MAX_TOOL_ITERATIONS and yield an error event."""
    from backend.providers.openai_provider import MAX_TOOL_ITERATIONS, OpenAIProvider

    tc_chunk = MagicMock()
    tc_chunk.choices = [MagicMock()]
    tc_chunk.choices[0].delta.content = None
    tc_delta = MagicMock()
    tc_delta.index = 0
    tc_delta.id = "call_loop"
    tc_delta.function.name = "generate_image"
    tc_delta.function.arguments = '{"prompt":"loop"}'
    tc_chunk.choices[0].delta.tool_calls = [tc_delta]

    async def fake_create(**kwargs):
        async def gen():
            yield tc_chunk

        return gen()

    fake_result = {
        "path": "/tmp/x.png",
        "url": "/api/generated/x.png",
        "prompt": "loop",
        "text": "Done.",
    }

    provider = OpenAIProvider()
    with (
        patch.object(provider.client.chat.completions, "create", new=fake_create),
        patch(
            "backend.providers.openai_provider._execute_tool",
            new=AsyncMock(return_value=fake_result),
        ),
    ):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Loop"}], "gpt-4o", False
        ):
            events.append(event)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "maximum iterations" in error_events[0]["message"]
    # should have called the tool exactly MAX_TOOL_ITERATIONS times
    tool_starts = [e for e in events if e["type"] == "tool_start"]
    assert len(tool_starts) == MAX_TOOL_ITERATIONS


# ---- Ollama provider ----


def _make_ollama_chunk(content: str | None):
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    return chunk


async def _ollama_events(chunks: list, provider=None):
    import backend.providers.ollama_provider as m

    if provider is None:
        original = m.settings.ollama_api_url
        m.settings.ollama_api_url = "http://localhost:11434"
        try:
            provider = m.OllamaProvider()
        finally:
            m.settings.ollama_api_url = original

    async def fake_create(**kwargs):
        async def gen():
            for c in chunks:
                yield c

        return gen()

    with patch.object(provider.client.chat.completions, "create", new=fake_create):
        events = []
        async for event in provider._stream([{"role": "user", "content": "Hi"}], "llama3"):
            events.append(event)
    return events


async def test_ollama_stream_plain_text():
    events = await _ollama_events(
        [_make_ollama_chunk("Hello "), _make_ollama_chunk("world")]
    )
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking_delta")
    assert text == "Hello world"
    assert thinking == ""


async def test_ollama_stream_think_block_single_chunk():
    events = await _ollama_events(
        [_make_ollama_chunk("<think>No violation.</think>Safe reply")]
    )
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking_delta")
    assert thinking == "No violation."
    assert text == "Safe reply"


async def test_ollama_stream_think_block_cross_chunk():
    # tags split across chunk boundaries
    events = await _ollama_events(
        [
            _make_ollama_chunk("<thi"),
            _make_ollama_chunk("nk>No violation.</th"),
            _make_ollama_chunk("ink>Reply"),
        ]
    )
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking_delta")
    assert thinking == "No violation."
    assert text == "Reply"


async def test_ollama_stream_think_then_text():
    events = await _ollama_events(
        [
            _make_ollama_chunk("<think>internal</think>"),
            _make_ollama_chunk("visible"),
        ]
    )
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    thinking = "".join(e["content"] for e in events if e["type"] == "thinking_delta")
    assert thinking == "internal"
    assert text == "visible"


async def test_ollama_stream_no_think_tags():
    events = await _ollama_events([_make_ollama_chunk("just text")])
    assert all(e["type"] == "text_delta" for e in events)


async def test_ollama_stream_no_choices():
    empty = MagicMock()
    empty.choices = []
    events = await _ollama_events([empty])
    assert events == []


async def test_anthropic_stream_max_iterations_guard():
    """Anthropic provider must also stop after MAX_TOOL_ITERATIONS."""
    from backend.providers.anthropic_provider import (
        MAX_TOOL_ITERATIONS,
        AnthropicProvider,
    )

    # build a stream that always returns a tool_use block
    def make_tool_events():
        return [
            MagicMock(
                type="content_block_start",
                content_block=MagicMock(
                    type="tool_use",
                    id="tc_0",
                    name="generate_image",
                ),
            ),
            MagicMock(
                type="content_block_delta",
                delta=MagicMock(
                    type="input_json_delta",
                    partial_json='{"prompt":"loop"}',
                ),
            ),
            MagicMock(type="content_block_stop"),
        ]

    async def async_iter(items):
        for item in items:
            yield item

    def make_mock_stream():
        ms = AsyncMock()
        ms.__aenter__ = AsyncMock(return_value=ms)
        ms.__aexit__ = AsyncMock(return_value=False)
        ms.__aiter__ = lambda self: async_iter(make_tool_events())
        return ms

    fake_result = {
        "path": "/tmp/x.png",
        "url": "/api/generated/x.png",
        "prompt": "loop",
        "text": "Done.",
    }

    provider = AnthropicProvider()
    with (
        patch.object(
            provider.client.messages,
            "stream",
            side_effect=lambda **kw: make_mock_stream(),
        ),
        patch(
            "backend.providers.anthropic_provider._execute_tool",
            new=AsyncMock(return_value=fake_result),
        ),
    ):
        events = []
        async for event in provider._stream(
            [{"role": "user", "content": "Loop"}], "claude-sonnet-4-6", False
        ):
            events.append(event)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "maximum iterations" in error_events[0]["message"]
    tool_starts = [e for e in events if e["type"] == "tool_start"]
    assert len(tool_starts) == MAX_TOOL_ITERATIONS
