"""Test-only endpoints. Only mounted when STUB_PROVIDERS=true or ALLOW_RESET=true."""
import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Attachment, Chat, GeneratedImage, Message, Profile

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/reset", status_code=204)
async def reset_db(
    db: AsyncSession = Depends(get_db),
    x_reset_secret: str | None = Header(default=None),
):
    """Delete all data — E2E test isolation helper."""
    if settings.reset_secret and x_reset_secret != settings.reset_secret:
        raise HTTPException(403, "Invalid or missing X-Reset-Secret header")

    att_paths = (await db.execute(select(Attachment.path))).scalars().all()
    img_paths = (await db.execute(select(GeneratedImage.path))).scalars().all()

    await db.execute(delete(GeneratedImage))
    await db.execute(delete(Attachment))
    await db.execute(delete(Message))
    await db.execute(delete(Chat))
    await db.execute(delete(Profile))
    await db.commit()

    for path in att_paths + img_paths:
        try:
            os.remove(path)
        except OSError:
            pass
