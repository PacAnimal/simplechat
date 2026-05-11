import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _collect_sse(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


async def test_stream_openai_message(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "Hello "}
        yield {"type": "text_delta", "content": "world!"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Say hello"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            events = await _collect_sse(response)

    text_events = [e for e in events if e["type"] == "text_delta"]
    assert any("Hello" in e["content"] for e in text_events)
    done_events = [e for e in events if e["type"] == "done"]
    assert len(done_events) == 1


async def test_stream_anthropic_message(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model, web_search):
        yield {"type": "text_delta", "content": "Hi there"}

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_stream
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Hello"},
        ) as response:
            assert response.status_code == 200
            events = await _collect_sse(response)

    assert any(e["type"] == "text_delta" for e in events)
    assert any(e["type"] == "done" for e in events)


async def test_stream_saves_messages(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "The answer is 42."}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "What is the answer?"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    msgs = (await client.get(f"/api/chats/{chat_id}/messages")).json()
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "What is the answer?"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "The answer is 42."


async def test_stream_auto_titles_chat(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    assert create.json()["title"] == "New Chat"

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "Sure!"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Tell me about the Eiffel Tower"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["title"] != "New Chat"
    assert "Eiffel" in chat["title"]


async def test_stream_missing_chat(client: AsyncClient):
    async with client.stream(
        "POST",
        "/api/chats/99999/messages",
        json={"content": "Hello"},
    ) as response:
        assert response.status_code == 404


async def test_stream_image_generation(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        yield {"type": "tool_start", "name": "generate_image"}
        yield {
            "type": "image_generated",
            "url": "/api/generated/test.png",
            "prompt": "a cat",
            "path": "/tmp/test.png",
        }
        yield {"type": "tool_result", "name": "generate_image", "content": "Done."}
        yield {"type": "text_delta", "content": "Here is your image!"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Draw a cat"},
        ) as response:
            events = await _collect_sse(response)

    image_events = [e for e in events if e["type"] == "image_generated"]
    assert len(image_events) == 1
    assert image_events[0]["url"] == "/api/generated/test.png"


async def test_stream_updates_chat_updated_at(client: AsyncClient):
    """updated_at must be bumped after every exchange, even when title is already set."""
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o", "title": "fixed"}
    )
    chat_id = create.json()["id"]
    before = create.json()["updated_at"]

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "ok"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "hello"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["updated_at"] != before


async def test_auto_title_does_not_fire_when_explicit_title_given(client: AsyncClient):
    """A chat created with an explicit title must keep it after the first exchange."""
    create = await client.post(
        "/api/chats",
        json={"provider": "openai", "model": "gpt-4o", "title": "My Project"},
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "ok"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Tell me something"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["title"] == "My Project"


async def test_auto_title_does_not_fire_after_patch_title(client: AsyncClient):
    """Setting the title via PATCH, then sending a message, must not auto-retitle."""
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    await client.patch(f"/api/chats/{chat_id}", json={"title": "Custom Title"})

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "ok"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Some question"},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["title"] == "Custom Title"


async def test_auto_title_fires_only_once(client: AsyncClient):
    """Auto-title must not fire on the second message."""
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "ok"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        for content in (
            "First message sets the title",
            "Second message must not change it",
        ):
            async with client.stream(
                "POST",
                f"/api/chats/{chat_id}/messages",
                json={"content": content},
            ) as response:
                async for _ in response.aiter_lines():
                    pass

    chat = (await client.get(f"/api/chats/{chat_id}")).json()
    assert chat["title"] == "First message sets the title"


async def test_stream_error_event_on_provider_failure(client: AsyncClient):
    """A provider exception must produce an SSE error event, not a 500."""
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]

    async def mock_stream(self, messages, model):
        raise RuntimeError("provider exploded")
        yield  # make it a generator

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "hello"},
        ) as response:
            assert response.status_code == 200
            events = await _collect_sse(response)

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "provider exploded" in error_events[0]["message"]
