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
        tools.append({"type": "web_search"})
    return tools


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
        # web search always uses the Responses API — native web_search tool works for
        # all current OpenAI models and eliminates the need for a third-party search client
        if web_search or model in _responses_api_models:
            return self._stream_responses(messages, model, web_search)
        return self._stream_with_fallback(messages, model, web_search)

    async def _stream_with_fallback(
        self,
        messages: list[ChatMessage],
        model: str,
        web_search: bool,
    ) -> AsyncIterator[StreamEvent]:
        try:
            async for event in self._stream(messages, model):
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
    ) -> AsyncIterator[StreamEvent]:
        tools = [
            {"type": "function", "function": GENERATE_IMAGE_TOOL},
            {"type": "function", "function": CALCULATOR_TOOL},
        ]

        current_messages: list = [
            {"role": m["role"], "content": _to_openai_content(m["content"])}
            for m in messages
        ]
        iteration = 0

        while True:
            iteration += 1
            if iteration > MAX_TOOL_ITERATIONS:
                logger.warning("Tool loop hit max iterations (%d) for model %s — stopping", MAX_TOOL_ITERATIONS, model)
                from .. import sse_events as _sse
                yield {"type": _sse.ERROR, "message": f"Tool loop reached maximum iterations ({MAX_TOOL_ITERATIONS}) — stopping to prevent an infinite loop"}
                return

            tool_call_accum: dict[int, dict] = {}

            create_kwargs: dict = dict(model=model, messages=current_messages, stream=True, tools=tools)
            stream = await self.client.chat.completions.create(**create_kwargs)  # type: ignore

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
            exceeded = iteration > MAX_TOOL_ITERATIONS
            if exceeded:
                logger.warning("Tool loop hit max iterations (%d) for model %s — forcing final response", MAX_TOOL_ITERATIONS, model)

            # custom function_calls only (web search is native and handled within the response)
            tool_calls: list[dict] = []
            # buffer text per iteration so intermediate tool-loop text never reaches the client
            pending_text: list[str] = []

            stream = await self.client.responses.create(
                model=model,
                input=current_input,  # type: ignore
                tools=[] if exceeded else tools,  # type: ignore
                stream=True,
            )

            async for event in stream:
                if event.type == "response.output_text.delta":
                    pending_text.append(event.delta)
                elif event.type == "response.web_search_call.in_progress":
                    yield {"type": sse_events.SEARCHING, "name": "web_search"}
                elif event.type == "response.output_item.done":
                    item = event.item
                    item_type = getattr(item, "type", None)
                    if item_type == "web_search_call":
                        # extract source URLs from the completed search result
                        sources = [
                            r.url
                            for r in (getattr(item, "results", None) or [])
                            if getattr(r, "url", None)
                        ]
                        yield {
                            "type": sse_events.TOOL_RESULT,
                            "name": "web_search",
                            "content": "",
                            "sources": sources,
                        }
                    elif not exceeded and item_type == "function_call":
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

            if not tool_calls or exceeded:
                # final iteration — flush buffered text to the client
                for chunk in pending_text:
                    yield {"type": sse_events.TEXT_DELTA, "content": chunk}
                break

            # intermediate iteration: execute custom tool calls, discard intermediate text
            for tc in tool_calls:
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}

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
