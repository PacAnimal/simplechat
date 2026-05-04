import os

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from jwt.exceptions import PyJWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Chat, GeneratedImage

router = APIRouter(prefix="/generated", tags=["images"])

_ALGORITHM = "HS256"


@router.get("/{filename}", include_in_schema=False)
async def serve_generated_image(
    filename: str,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(404)

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    raw_token = authorization[7:]

    try:
        payload = jwt.decode(raw_token, settings.jwt_secret, algorithms=[_ALGORITHM])
        profile_id = int(payload["sub"])
    except (PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    full_path = os.path.realpath(os.path.join(settings.generated_dir, filename))
    gen_dir = os.path.realpath(settings.generated_dir)
    if not full_path.startswith(gen_dir + os.sep) or not os.path.exists(full_path):
        raise HTTPException(404)

    result = await db.execute(
        select(GeneratedImage)
        .join(Chat, Chat.id == GeneratedImage.chat_id)
        .where(GeneratedImage.path == full_path, Chat.profile_id == profile_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404)

    return FileResponse(full_path)
