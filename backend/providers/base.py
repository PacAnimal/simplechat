from typing import TypedDict

from .. import sse_events
from ..tools.calculator import calculate as _calculate
from ..tools.image_gen import generate_image as _generate_image

MAX_TOOL_ITERATIONS = 10


async def execute_tool(name: str, args: dict) -> dict:
    if name == "generate_image":
        return await _generate_image(
            args.get("prompt", ""), args.get("size", "1024x1024")
        )
    if name == "calculate":
        return _calculate(args.get("expression", ""))
    raise ValueError(f"Unknown tool: {name}")


class ChatMessage(TypedDict):
    role: str
    content: str


class StreamEvent(TypedDict, total=False):
    type: str  # see sse_events constants
    content: str
    name: str
    url: str
    prompt: str
    message: str
    message_id: int
    title: str
    error: str  # set on tool_result when the tool returned an error


CALCULATOR_TOOL = {
    "name": "calculate",
    "description": (
        "Evaluate a mathematical expression. Supports arithmetic (+, -, *, /, **, //, %), "
        "functions (sqrt, cbrt, sin, cos, tan, asin, acos, atan, log, log2, log10, exp, "
        "abs, ceil, floor, round, factorial, degrees, radians, hypot), "
        "and constants (pi, e, tau). Always use this for any arithmetic or math calculation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A mathematical expression, e.g. '2 + 2', 'sqrt(144)', 'sin(pi / 2)', 'factorial(10)'",
            },
        },
        "required": ["expression"],
    },
}

GENERATE_IMAGE_TOOL = {
    "name": "generate_image",
    "description": "Generate an image using DALL-E 3. Use this when the user asks you to create, draw, or generate an image or picture.",
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "A detailed description of the image to generate",
            },
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1792x1024", "1024x1792"],
                "description": "Image dimensions. Default 1024x1024.",
            },
        },
        "required": ["prompt"],
    },
}

WEB_SEARCH_TOOL_OPENAI = {
    "name": "web_search",
    "description": "Search the web for current information. Use when asked about recent events, current data, or anything that needs up-to-date information.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            }
        },
        "required": ["query"],
    },
}


def tool_result_event(name: str, result: dict) -> StreamEvent:
    """Build a tool_result event, flagging errors when present."""
    event: StreamEvent = {
        "type": sse_events.TOOL_RESULT,
        "name": name,
        "content": result.get("text", "Done."),
    }
    if "error" in result:
        event["error"] = result["error"]
    return event
