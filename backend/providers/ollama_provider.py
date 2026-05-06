import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from .. import sse_events
from ..config import settings
from .base import ChatMessage, StreamEvent

logger = logging.getLogger(__name__)


def _partial_tag_suffix(text: str, tag: str) -> int:
    """Length of the longest suffix of text that is a prefix of tag."""
    for n in range(min(len(tag) - 1, len(text)), 0, -1):
        if text.endswith(tag[:n]):
            return n
    return 0


class OllamaProvider:
    def __init__(self):
        if not settings.ollama_api_url:
            raise ValueError("OLLAMA_API_URL is not configured")
        base_url = settings.ollama_api_url.rstrip("/") + "/v1"
        self.client = AsyncOpenAI(api_key="ollama", base_url=base_url)

    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        return self._stream(messages, model)

    async def _stream(
        self,
        messages: list[ChatMessage],
        model: str,
    ) -> AsyncIterator[StreamEvent]:
        if settings.ollama_system_prompt:
            messages = [
                {"role": "system", "content": settings.ollama_system_prompt},
                *messages,
            ]

        stream = await self.client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore
            stream=True,
        )

        in_think = False
        buf = ""

        async for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if not content:
                continue

            buf += content

            # parse out <think>...</think> blocks as thinking events
            while buf:
                if in_think:
                    end = buf.find("</think>")
                    if end == -1:
                        partial = _partial_tag_suffix(buf, "</think>")
                        emit = buf[: len(buf) - partial]
                        if emit:
                            yield {"type": sse_events.THINKING_DELTA, "content": emit}
                        buf = buf[len(buf) - partial :]
                        break
                    if end > 0:
                        yield {"type": sse_events.THINKING_DELTA, "content": buf[:end]}
                    buf = buf[end + len("</think>") :]
                    in_think = False
                else:
                    start = buf.find("<think>")
                    if start == -1:
                        partial = _partial_tag_suffix(buf, "<think>")
                        emit = buf[: len(buf) - partial]
                        if emit:
                            yield {"type": sse_events.TEXT_DELTA, "content": emit}
                        buf = buf[len(buf) - partial :]
                        break
                    if start > 0:
                        yield {"type": sse_events.TEXT_DELTA, "content": buf[:start]}
                    buf = buf[start + len("<think>") :]
                    in_think = True

        # flush remainder
        if buf:
            yield {
                "type": sse_events.THINKING_DELTA
                if in_think
                else sse_events.TEXT_DELTA,
                "content": buf,
            }
