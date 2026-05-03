import json
from typing import AsyncIterator
from openai import AsyncOpenAI
from .base import StreamEvent, ChatMessage, GENERATE_IMAGE_TOOL, WEB_SEARCH_TOOL_OPENAI
from ..tools.image_gen import generate_image as _generate_image
from ..config import settings


async def _web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(query, max_results=6))
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(f"**{r.get('title', '')}**\n{r.get('body', '')}\nSource: {r.get('href', '')}")
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


async def _execute_tool(name: str, args: dict) -> dict:
    if name == "generate_image":
        return await _generate_image(args.get("prompt", ""), args.get("size", "1024x1024"))
    raise ValueError(f"Unknown tool: {name}")


class OpenAIProvider:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def stream_chat(
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
        tools = [
            {"type": "function", "function": GENERATE_IMAGE_TOOL},
        ]
        if web_search:
            tools.append({"type": "function", "function": WEB_SEARCH_TOOL_OPENAI})

        current_messages = list(messages)

        while True:
            tool_call_accum: dict[int, dict] = {}

            stream = await self.client.chat.completions.create(
                model=model,
                messages=current_messages,  # type: ignore
                tools=tools,  # type: ignore
                stream=True,
            )

            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    yield {"type": "text_delta", "content": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc.id:
                            tool_call_accum[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_call_accum[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_call_accum[idx]["arguments"] += tc.function.arguments

            if not tool_call_accum:
                break

            # build assistant message with tool calls
            assistant_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_call_accum.values()
            ]
            current_messages.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})  # type: ignore

            # execute each tool
            for tc in tool_call_accum.values():
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}

                if tc["name"] == "web_search":
                    yield {"type": "searching", "name": "web_search"}
                    result_text = await _web_search(args.get("query", ""))
                    current_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result_text})  # type: ignore
                else:
                    yield {"type": "tool_start", "name": tc["name"]}
                    try:
                        result = await _execute_tool(tc["name"], args)
                        if tc["name"] == "generate_image":
                            yield {
                                "type": "image_generated",
                                "url": result["url"],
                                "prompt": result["prompt"],
                                "path": result["path"],
                            }
                        yield {"type": "tool_result", "name": tc["name"], "content": result.get("text", "Done.")}
                        current_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result.get("text", "Done.")})  # type: ignore
                    except Exception as e:
                        err = f"Tool error: {e}"
                        yield {"type": "tool_result", "name": tc["name"], "content": err}
                        current_messages.append({"role": "tool", "tool_call_id": tc["id"], "content": err})  # type: ignore
