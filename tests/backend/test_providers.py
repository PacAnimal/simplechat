import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
        async for event in provider._stream([{"role": "user", "content": "Hi"}], "gpt-4o", False):
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
        async for event in provider._stream([{"role": "user", "content": "Hi"}], "gpt-4o", False):
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
        "url": "/generated/test.png",
        "prompt": "a cat",
        "text": "Image generated.",
    }

    provider = OpenAIProvider()
    with (
        patch.object(provider.client.chat.completions, "create", new=fake_create),
        patch("backend.providers.openai_provider._execute_tool", new=AsyncMock(return_value=fake_image_result)),
    ):
        events = []
        async for event in provider._stream([{"role": "user", "content": "Draw a cat"}], "gpt-4o", False):
            events.append(event)

    assert any(e["type"] == "tool_start" for e in events)
    assert any(e["type"] == "image_generated" for e in events)
    assert any(e["type"] == "text_delta" for e in events)


# ---- Anthropic provider ----

async def test_anthropic_stream_text():
    from backend.providers.anthropic_provider import AnthropicProvider

    # build mock streaming context
    events_sequence = [
        MagicMock(type="content_block_start", content_block=MagicMock(type="text", id="blk_0")),
        MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="Hello")),
        MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text=" world")),
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
    mock_stream.get_final_message = AsyncMock(return_value=MagicMock(stop_reason="end_turn", content=[]))

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", return_value=mock_stream):
        events = []
        async for event in provider._stream([{"role": "user", "content": "Hi"}], "claude-sonnet-4-6", False):
            events.append(event)

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert text == "Hello world"


async def test_anthropic_stream_web_search_event():
    from backend.providers.anthropic_provider import AnthropicProvider

    events_sequence = [
        MagicMock(type="content_block_start", content_block=MagicMock(type="server_tool_use", id="srv_0", name="web_search")),
        MagicMock(type="content_block_stop"),
        MagicMock(type="content_block_start", content_block=MagicMock(type="text", id="blk_1")),
        MagicMock(type="content_block_delta", delta=MagicMock(type="text_delta", text="Result!")),
        MagicMock(type="content_block_stop"),
    ]

    async def async_iter(items):
        for item in items:
            yield item

    mock_stream = AsyncMock()
    mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
    mock_stream.__aexit__ = AsyncMock(return_value=False)
    mock_stream.__aiter__ = lambda self: async_iter(events_sequence)
    mock_stream.get_final_message = AsyncMock(return_value=MagicMock(stop_reason="end_turn", content=[]))

    provider = AnthropicProvider()
    with patch.object(provider.client.messages, "stream", return_value=mock_stream):
        events = []
        async for event in provider._stream([{"role": "user", "content": "Search for X"}], "claude-sonnet-4-6", True):
            events.append(event)

    assert any(e["type"] == "searching" for e in events)
    assert any(e["type"] == "text_delta" for e in events)
