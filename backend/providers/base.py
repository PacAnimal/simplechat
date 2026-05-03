from typing import TypedDict, AsyncIterator, Any, Optional


class ChatMessage(TypedDict):
    role: str
    content: str


class StreamEvent(TypedDict, total=False):
    type: str           # text_delta | thinking_delta | tool_start | tool_result | image_generated | searching | done | error | chat_title
    content: str
    name: str
    url: str
    prompt: str
    message: str
    message_id: int
    title: str


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
