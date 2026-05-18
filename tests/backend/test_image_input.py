"""Tests proving image attachments reach provider context in the correct format,
and that the two-step generate-then-describe flow works end-to-end for both
OpenAI and Anthropic."""

import base64
import json
import pathlib
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_FIXTURE_IMAGE = pathlib.Path(__file__).parent / "fixtures" / "object.png"


async def _create_chat(client: AsyncClient, provider: str) -> int:
    model = "gpt-4o" if provider == "openai" else "claude-sonnet-4-6"
    r = await client.post("/api/chats", json={"provider": provider, "model": model})
    assert r.status_code == 201
    return r.json()["id"]


async def _upload_image(client: AsyncClient, chat_id: int) -> int:
    data = _FIXTURE_IMAGE.read_bytes()
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("object.png", data, "image/png")},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def _collect_text(resp) -> str:
    text = ""
    async for line in resp.aiter_lines():
        if line.startswith("data: "):
            event = json.loads(line[6:])
            if event.get("type") == "text_delta":
                text += event.get("content", "")
    return text


# ---- image block format tests ----


async def test_openai_receives_image_block(client: AsyncClient):
    """OpenAI provider receives an image attachment as an image_url content block with correct base64 data."""
    chat_id = await _create_chat(client, "openai")
    att_id = await _upload_image(client, chat_id)
    captured: list[dict] = []

    async def mock_stream(self, messages, model):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "ok"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Generate an image of this object sitting on an old wooden floor.",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    user_msgs = [m for m in captured if m["role"] == "user"]
    assert len(user_msgs) == 1
    content = user_msgs[0]["content"]
    assert isinstance(content, list), "expected list content when image is attached"

    # _build_messages uses the internal format; provider conversion happens inside _stream
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1

    assert image_blocks[0]["media_type"] == "image/png"
    expected = base64.b64encode(_FIXTURE_IMAGE.read_bytes()).decode()
    assert image_blocks[0]["data"] == expected


async def test_anthropic_receives_image_block(client: AsyncClient):
    """Anthropic provider receives an image attachment as a source-typed image block with correct base64 data."""
    chat_id = await _create_chat(client, "anthropic")
    att_id = await _upload_image(client, chat_id)
    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "ok"}

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_stream
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Generate an image of this object sitting on an old wooden floor.",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    user_msgs = [m for m in captured if m["role"] == "user"]
    assert len(user_msgs) == 1
    content = user_msgs[0]["content"]
    assert isinstance(content, list), "expected list content when image is attached"

    # _build_messages uses the internal format; _to_anthropic_content converts inside _stream
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1

    assert image_blocks[0]["media_type"] == "image/png"
    expected = base64.b64encode(_FIXTURE_IMAGE.read_bytes()).decode()
    assert image_blocks[0]["data"] == expected


# ---- generate → describe two-step flow ----


async def test_openai_generate_and_describe_pink_teapot(client: AsyncClient):
    """OpenAI two-step flow: the AI looks at object.png, generates an image of it on a
    wooden floor (identifying it as a pink teapot), then describes it as such."""
    chat_id = await _create_chat(client, "openai")
    att_id = await _upload_image(client, chat_id)

    # step 1: AI sees the image and generates one of a pink teapot on wooden floor
    async def mock_generate(self, messages, model):
        yield {
            "type": "image_generated",
            "url": "/api/generated/teapot_floor.png",
            "path": "/tmp/teapot_floor.png",
            "prompt": "a pink teapot sitting on an old wooden floor",
        }
        yield {"type": "text_delta", "content": "I've generated the image."}

    with patch(
        "backend.providers.openai_provider.OpenAIProvider._stream", mock_generate
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Generate an image of this object sitting on an old wooden floor.",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    # step 2: ask for a description — history now includes the generated image prompt
    async def mock_describe(self, messages, model):
        yield {
            "type": "text_delta",
            "content": "A pink teapot sitting on an old wooden floor.",
        }

    with patch(
        "backend.providers.openai_provider.OpenAIProvider._stream", mock_describe
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Describe the image you just generated."},
        ) as resp:
            description = await _collect_text(resp)

    assert "pink" in description.lower()
    assert "teapot" in description.lower()


async def test_anthropic_generate_and_describe_pink_teapot(client: AsyncClient):
    """Anthropic two-step flow: the AI looks at object.png, generates an image of it on a
    wooden floor (identifying it as a pink teapot), then describes it as such."""
    chat_id = await _create_chat(client, "anthropic")
    att_id = await _upload_image(client, chat_id)

    # step 1: AI sees the image and generates one of a pink teapot on wooden floor
    async def mock_generate(self, messages, model, web_search):
        yield {
            "type": "image_generated",
            "url": "/api/generated/teapot_floor.png",
            "path": "/tmp/teapot_floor.png",
            "prompt": "a pink teapot sitting on an old wooden floor",
        }
        yield {"type": "text_delta", "content": "I've generated the image."}

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_generate
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Generate an image of this object sitting on an old wooden floor.",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    # step 2: ask for a description — history now includes the generated image prompt
    async def mock_describe(self, messages, model, web_search):
        yield {
            "type": "text_delta",
            "content": "A pink teapot sitting on an old wooden floor.",
        }

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_describe
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Describe the image you just generated."},
        ) as resp:
            description = await _collect_text(resp)

    assert "pink" in description.lower()
    assert "teapot" in description.lower()
