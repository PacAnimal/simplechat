import base64
import os
import uuid

import aiofiles
from openai import AsyncOpenAI

from ..config import settings


async def generate_image(prompt: str, size: str = "1024x1024") -> dict:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    valid_sizes = {"1024x1024", "1536x1024", "1024x1536"}
    if size not in valid_sizes:
        size = "1024x1024"

    response = await client.images.generate(
        model=settings.image_model,
        prompt=prompt,
        size=size,  # type: ignore
        n=1,
        response_format="b64_json",
    )

    image_data = base64.b64decode(response.data[0].b64_json)
    filename = f"{uuid.uuid4().hex}.png"
    dest_path = os.path.join(settings.generated_dir, filename)

    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(image_data)

    return {
        "path": dest_path,
        "url": f"/generated/{filename}",
        "prompt": prompt,
        "text": "I've generated the image. It will be displayed inline.",
    }
