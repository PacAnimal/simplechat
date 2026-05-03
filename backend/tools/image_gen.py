import os
import uuid

import aiofiles
import httpx
from openai import AsyncOpenAI

from ..config import settings


async def generate_image(prompt: str, size: str = "1024x1024") -> dict:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    valid_sizes = {"1024x1024", "1792x1024", "1024x1792"}
    if size not in valid_sizes:
        size = "1024x1024"

    response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,  # type: ignore
        n=1,
    )

    image_url = response.data[0].url
    filename = f"{uuid.uuid4().hex}.png"
    dest_path = os.path.join(settings.generated_dir, filename)

    async with httpx.AsyncClient() as http:
        img_response = await http.get(image_url, timeout=60)
        img_response.raise_for_status()
        async with aiofiles.open(dest_path, "wb") as f:
            await f.write(img_response.content)

    return {
        "path": dest_path,
        "url": f"/generated/{filename}",
        "prompt": prompt,
        "text": "I've generated the image. It will be displayed inline.",
    }
