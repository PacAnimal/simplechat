import base64
import os
import uuid

import aiofiles
from openai import AsyncOpenAI

from ..config import settings


async def generate_image(prompt: str, size: str = "1024x1024", image_path: str | None = None) -> dict:
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not configured")
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    valid_sizes = {"1024x1024", "1536x1024", "1024x1536"}
    if size not in valid_sizes:
        size = "1024x1024"

    if image_path:
        # validate path is within generated dir to prevent traversal
        real_path = os.path.realpath(image_path)
        real_gen_dir = os.path.realpath(settings.generated_dir)
        if not real_path.startswith(real_gen_dir + os.sep) and real_path != real_gen_dir:
            raise ValueError("Invalid image_path: must be within generated directory")

        async with aiofiles.open(image_path, "rb") as f:
            src_bytes = await f.read()

        edit_kwargs: dict = {
            "model": settings.image_model,
            "image": ("image.png", src_bytes, "image/png"),
            "prompt": prompt,
            "size": size,
            "n": 1,
        }
        if settings.image_model.startswith("dall-e"):
            edit_kwargs["response_format"] = "b64_json"
        response = await client.images.edit(**edit_kwargs)  # type: ignore
    else:
        gen_kwargs: dict = {"model": settings.image_model, "prompt": prompt, "size": size, "n": 1}
        # dall-e-* models require response_format; gpt-image-* always returns b64
        if settings.image_model.startswith("dall-e"):
            gen_kwargs["response_format"] = "b64_json"
        response = await client.images.generate(**gen_kwargs)  # type: ignore

    image_data = base64.b64decode(response.data[0].b64_json)
    filename = f"{uuid.uuid4().hex}.png"
    dest_path = os.path.join(settings.generated_dir, filename)

    async with aiofiles.open(dest_path, "wb") as f:
        await f.write(image_data)

    return {
        "path": dest_path,
        "url": f"/api/generated/{filename}",
        "prompt": prompt,
        "text": "I've generated the image. It will be displayed inline.",
    }
