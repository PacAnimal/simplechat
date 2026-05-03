import json
from collections.abc import AsyncIterator

import anthropic

from ..config import settings
from .base import GENERATE_IMAGE_TOOL, MAX_TOOL_ITERATIONS, ChatMessage, StreamEvent
from .base import execute_tool as _execute_tool

_ANTHROPIC_IMAGE_TOOL = {
    "name": GENERATE_IMAGE_TOOL["name"],
    "description": GENERATE_IMAGE_TOOL["description"],
    "input_schema": GENERATE_IMAGE_TOOL["parameters"],
}

_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
}


class AnthropicProvider:
    def __init__(self):
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured")
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        return self._stream(messages, model, web_search)

    async def _stream(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool,
    ) -> AsyncIterator[StreamEvent]:
        tools: list = [_ANTHROPIC_IMAGE_TOOL]
        if web_search:
            tools.append(_WEB_SEARCH_TOOL)

        current_messages = list(messages)
        iteration = 0

        while True:
            iteration += 1
            if iteration > MAX_TOOL_ITERATIONS:
                yield {"type": "error", "message": "Tool loop exceeded maximum iterations"}
                break

            content_blocks: list[dict] = []
            current_block: dict | None = None
            custom_tool_calls: list[dict] = []

            async with self.client.messages.stream(
                model=model,
                messages=current_messages,  # type: ignore
                max_tokens=8096,
                tools=tools,  # type: ignore
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        blk = event.content_block
                        current_block = None
                        if blk.type == "text":
                            current_block = {"type": "text", "content": ""}
                        elif blk.type == "thinking":
                            current_block = {"type": "thinking", "content": ""}
                        elif blk.type in ("tool_use", "server_tool_use"):
                            current_block = {
                                "type": blk.type,
                                "id": blk.id,
                                "name": blk.name,
                                "input_str": "",
                            }
                            if blk.type == "server_tool_use":
                                yield {"type": "searching", "name": blk.name}
                        if current_block is not None:
                            content_blocks.append(current_block)

                    elif event.type == "content_block_delta":
                        if current_block is None:
                            continue
                        delta = event.delta
                        if delta.type == "text_delta":
                            current_block["content"] = current_block.get("content", "") + delta.text
                            yield {"type": "text_delta", "content": delta.text}
                        elif delta.type == "thinking_delta":
                            text = getattr(delta, "thinking", "")
                            current_block["content"] = current_block.get("content", "") + text
                            if text:
                                yield {"type": "thinking_delta", "content": text}
                        elif delta.type == "input_json_delta":
                            current_block["input_str"] = current_block.get("input_str", "") + delta.partial_json

                    elif event.type == "content_block_stop":
                        if current_block and current_block["type"] == "tool_use":
                            try:
                                current_block["input"] = json.loads(current_block.get("input_str", "{}"))
                            except json.JSONDecodeError:
                                current_block["input"] = {}
                            custom_tool_calls.append(current_block)
                        current_block = None

            if not custom_tool_calls:
                break

            # build assistant turn with all content blocks
            assistant_content = []
            for blk in content_blocks:
                if blk["type"] == "text":
                    assistant_content.append({"type": "text", "text": blk["content"]})
                elif blk["type"] == "tool_use":
                    assistant_content.append({
                        "type": "tool_use",
                        "id": blk["id"],
                        "name": blk["name"],
                        "input": blk.get("input", {}),
                    })
                # server_tool_use blocks are handled by Anthropic, skip from history
            current_messages.append({"role": "assistant", "content": assistant_content})  # type: ignore

            # execute custom tools and collect results
            tool_results = []
            for tc in custom_tool_calls:
                yield {"type": "tool_start", "name": tc["name"]}
                try:
                    result = await _execute_tool(tc["name"], tc.get("input", {}))
                    if tc["name"] == "generate_image":
                        yield {
                            "type": "image_generated",
                            "url": result["url"],
                            "prompt": result["prompt"],
                            "path": result["path"],
                        }
                    yield {"type": "tool_result", "name": tc["name"], "content": result.get("text", "Done.")}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result.get("text", "Done."),
                    })
                except Exception as e:
                    err = f"Tool error: {e}"
                    yield {"type": "tool_result", "name": tc["name"], "content": err}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": err,
                    })

            current_messages.append({"role": "user", "content": tool_results})  # type: ignore
