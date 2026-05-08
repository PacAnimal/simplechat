import asyncio
import json
import logging
from collections.abc import AsyncIterator

import openai
from openai import AsyncOpenAI

from .. import sse_events
from ..config import settings
from .base import (
    CALCULATOR_TOOL,
    GENERATE_IMAGE_TOOL,
    MAX_TOOL_ITERATIONS,
    WEB_SEARCH_TOOL_OPENAI,
    ChatMessage,
    StreamEvent,
    tool_result_event,
)
from .base import execute_tool as _execute_tool

logger = logging.getLogger(__name__)

# populated at runtime when chat completions rejects a model with the responses-only error
_responses_api_models: set[str] = set()


def _to_openai_content(content: str | list) -> str | list:
    if isinstance(content, str):
        return content
    result = []
    for blk in content:
        if blk.get("type") == "text":
            result.append({"type": "text", "text": blk["text"]})
        elif blk.get("type") == "image":
            result.append({
                "type": "image_url",
                "image_url": {"url": f"data:{blk['media_type']};base64,{blk['data']}"},
            })
    return result


def _to_responses_input(messages: list[ChatMessage]) -> list:
    result = []
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            result.append({"role": m["role"], "content": content})
        else:
            parts = []
            for blk in content:
                if blk.get("type") == "text":
                    parts.append({"type": "input_text", "text": blk["text"]})
                elif blk.get("type") == "image":
                    parts.append({
                        "type": "input_image",
                        "image_url": f"data:{blk['media_type']};base64,{blk['data']}",
                    })
            result.append({"role": m["role"], "content": parts})
    return result


def _responses_tools(include_web_search: bool) -> list:
    tools = [
        {
            "type": "function",
            "name": GENERATE_IMAGE_TOOL["name"],
            "description": GENERATE_IMAGE_TOOL["description"],
            "parameters": GENERATE_IMAGE_TOOL["parameters"],
        },
        {
            "type": "function",
            "name": CALCULATOR_TOOL["name"],
            "description": CALCULATOR_TOOL["description"],
            "parameters": CALCULATOR_TOOL["parameters"],
        },
    ]
    if include_web_search:
        tools.append({
            "type": "function",
            "name": WEB_SEARCH_TOOL_OPENAI["name"],
            "description": WEB_SEARCH_TOOL_OPENAI["description"],
            "parameters": WEB_SEARCH_TOOL_OPENAI["parameters"],
        })
    return tools


async def _web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS

        def _sync():
            return list(DDGS().text(query, max_results=6))

        results = await asyncio.to_thread(_sync)
        if not results:
            return "No results found."
        lines = []
        for r in results:
            lines.append(
                f"**{r.get('title', '')}**\n{r.get('body', '')}\nSource: {r.get('href', '')}"
            )
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"Search failed: {e}"


class OpenAIProvider:
    def __init__(self):
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        if model in _responses_api_models:
            return self._stream_responses(messages, model, web_search)
        return self._stream_with_fallback(messages, model, web_search)

    async def _stream_with_fallback(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool,
    ) -> AsyncIterator[StreamEvent]:
        try:
            async for event in self._stream(messages, model, web_search):
                yield event
        except openai.APIStatusError as e:
            if "v1/responses" in str(e):
                _responses_api_models.add(model)
                logger.info("Model %s requires /v1/responses — switching automatically", model)
                async for event in self._stream_responses(messages, model, web_search):
                    yield event
            else:
                raise

    async def _stream(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool,
    ) -> AsyncIterator[StreamEvent]:
        tools = [
            {"type": "function", "function": GENERATE_IMAGE_TOOL},
            {"type": "function", "function": CALCULATOR_TOOL},
        ]
        if web_search:
            tools.append({"type": "function", "function": WEB_SEARCH_TOOL_OPENAI})

        current_messages: list = [
            {"role": m["role"], "content": _to_openai_content(m["content"])}
            for m in messages
        ]
        iteration = 0

        while True:
            iteration += 1
            if iteration > MAX_TOOL_ITERATIONS:
                yield {
                    "type": sse_events.ERROR,
                    "message": "Tool loop exceeded maximum iterations",
                }
                break

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
                    yield {"type": sse_events.TEXT_DELTA, "content": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_call_accum[idx]["id"] = tc.id
                        if tc.function and tc.function.name:
                            tool_call_accum[idx]["name"] = tc.function.name
                        if tc.function and tc.function.arguments:
                            tool_call_accum[idx]["arguments"] += tc.function.arguments

            if not tool_call_accum:
                break

            assistant_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in tool_call_accum.values()
            ]
            current_messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": assistant_tool_calls,
                }
            )  # type: ignore

            for tc in tool_call_accum.values():
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}

                if tc["name"] == "web_search":
                    yield {"type": sse_events.SEARCHING, "name": "web_search"}
                    result_text = await _web_search(args.get("query", ""))
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_text,
                        }
                    )  # type: ignore
                else:
                    yield {"type": sse_events.TOOL_START, "name": tc["name"]}
                    try:
                        result = await _execute_tool(tc["name"], args)
                        if tc["name"] == "generate_image":
                            yield {
                                "type": sse_events.IMAGE_GENERATED,
                                "url": result["url"],
                                "prompt": result["prompt"],
                                "path": result["path"],
                            }
                        yield tool_result_event(tc["name"], result)
                        current_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result.get("text", "Done."),
                            }
                        )  # type: ignore
                    except Exception as e:
                        logger.exception("Tool %s failed", tc["name"])
                        err = f"Tool error: {e}"
                        yield {
                            "type": sse_events.TOOL_RESULT,
                            "name": tc["name"],
                            "content": err,
                            "error": err,
                        }
                        current_messages.append(
                            {"role": "tool", "tool_call_id": tc["id"], "content": err}
                        )  # type: ignore

    async def _stream_responses(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool,
    ) -> AsyncIterator[StreamEvent]:
        tools = _responses_tools(web_search)
        current_input = _to_responses_input(messages)
        iteration = 0

        while True:
            iteration += 1
            if iteration > MAX_TOOL_ITERATIONS:
                yield {
                    "type": sse_events.ERROR,
                    "message": "Tool loop exceeded maximum iterations",
                }
                break

            tool_calls: list[dict] = []

            stream = await self.client.responses.create(
                model=model,
                input=current_input,  # type: ignore
                tools=tools,  # type: ignore
                stream=True,
            )

            async for event in stream:
                if event.type == "response.output_text.delta":
                    yield {"type": sse_events.TEXT_DELTA, "content": event.delta}
                elif event.type == "response.output_item.done":
                    item = event.item
                    if getattr(item, "type", None) == "function_call":
                        tool_calls.append({
                            "call_id": item.call_id,
                            "name": item.name,
                            "arguments": item.arguments,
                        })
                        current_input.append({
                            "type": "function_call",
                            "call_id": item.call_id,
                            "name": item.name,
                            "arguments": item.arguments,
                        })

            if not tool_calls:
                break

            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}

                if tc["name"] == "web_search":
                    yield {"type": sse_events.SEARCHING, "name": "web_search"}
                    result_text = await _web_search(args.get("query", ""))
                    current_input.append({
                        "type": "function_call_output",
                        "call_id": tc["call_id"],
                        "output": result_text,
                    })
                else:
                    yield {"type": sse_events.TOOL_START, "name": tc["name"]}
                    try:
                        result = await _execute_tool(tc["name"], args)
                        if tc["name"] == "generate_image":
                            yield {
                                "type": sse_events.IMAGE_GENERATED,
                                "url": result["url"],
                                "prompt": result["prompt"],
                                "path": result["path"],
                            }
                        yield tool_result_event(tc["name"], result)
                        current_input.append({
                            "type": "function_call_output",
                            "call_id": tc["call_id"],
                            "output": result.get("text", "Done."),
                        })
                    except Exception as e:
                        logger.exception("Tool %s failed", tc["name"])
                        err = f"Tool error: {e}"
                        yield {
                            "type": sse_events.TOOL_RESULT,
                            "name": tc["name"],
                            "content": err,
                            "error": err,
                        }
                        current_input.append({
                            "type": "function_call_output",
                            "call_id": tc["call_id"],
                            "output": err,
                        })
