"""
Stub provider for E2E testing. Activated with STUB_PROVIDERS=true.
Returns canned responses without calling any real AI API.
"""

import asyncio
import base64
import os
from collections.abc import AsyncIterator

from .. import sse_events
from ..config import settings
from .base import ChatMessage, StreamEvent

# 1x1 placeholder PNG
_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_PLACEHOLDER_FILENAME = "stub_placeholder.png"


def _ensure_placeholder():
    path = os.path.join(settings.generated_dir, _PLACEHOLDER_FILENAME)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(_PLACEHOLDER_PNG)
    return path


class StubProvider:
    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def stream_chat(
        self, messages: list[ChatMessage], model: str, web_search: bool = False
    ) -> AsyncIterator[StreamEvent]:
        return self._gen(messages, model, web_search)

    def _stream(
        self, messages: list[ChatMessage], model: str, web_search: bool
    ) -> AsyncIterator[StreamEvent]:
        return self._gen(messages, model, web_search)

    async def _gen(self, messages, model, web_search) -> AsyncIterator[StreamEvent]:
        def _text(c: str | list) -> str:
            if isinstance(c, str):
                return c
            return next((b["text"] for b in c if b.get("type") == "text"), "")

        last_user = next(
            (_text(m["content"]) for m in reversed(messages) if m["role"] == "user"), ""
        )
        is_image_request = any(
            kw in last_user.lower()
            for kw in ["image", "picture", "draw", "generate", "paint", "photo"]
        )

        if is_image_request:
            yield {"type": sse_events.TOOL_START, "name": "generate_image"}
            await asyncio.sleep(0.05)
            path = _ensure_placeholder()
            yield {
                "type": sse_events.IMAGE_GENERATED,
                "url": f"/api/generated/{_PLACEHOLDER_FILENAME}",
                "prompt": last_user,
                "path": path,
            }
            yield {
                "type": sse_events.TOOL_RESULT,
                "name": "generate_image",
                "content": "Image generated.",
            }
            for word in f"Here is your generated image! (stub · {self.provider_name} · {model})".split():
                yield {"type": sse_events.TEXT_DELTA, "content": word + " "}
        elif web_search:
            yield {"type": sse_events.SEARCHING, "name": "web_search"}
            await asyncio.sleep(0.05)
            for word in f"[Web search enabled] Stub response from {self.provider_name} ({model}).".split():
                yield {"type": sse_events.TEXT_DELTA, "content": word + " "}
        else:
            response = f"Hello! I am a stub response from **{self.provider_name}** using `{model}`. Your message was: _{last_user}_"
            for word in response.split():
                yield {"type": sse_events.TEXT_DELTA, "content": word + " "}
