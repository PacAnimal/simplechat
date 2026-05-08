"""Test-only endpoints. Only mounted when STUB_PROVIDERS=true or ALLOW_RESET=true."""

import os

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Attachment, Chat, Dataset, DatasetFile, GeneratedImage, Message, Profile

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/reset", status_code=204)
async def reset_db(
    db: AsyncSession = Depends(get_db),
    x_reset_secret: str | None = Header(default=None),
):
    """Delete all data — E2E test isolation helper."""
    if not settings.reset_secret or x_reset_secret != settings.reset_secret:
        raise HTTPException(403, "Invalid or missing X-Reset-Secret header")

    att_paths = (await db.execute(select(Attachment.path))).scalars().all()
    img_paths = (await db.execute(select(GeneratedImage.path))).scalars().all()

    await db.execute(delete(GeneratedImage))
    await db.execute(delete(Attachment))
    await db.execute(delete(Message))
    await db.execute(delete(Chat))
    await db.execute(delete(DatasetFile))
    await db.execute(delete(Dataset))
    await db.execute(delete(Profile))
    await db.commit()

    uploads_real = os.path.realpath(settings.uploads_dir)
    generated_real = os.path.realpath(settings.generated_dir)
    for path in att_paths + img_paths:
        real = os.path.realpath(path)
        if not (real.startswith(uploads_real + os.sep) or real.startswith(generated_real + os.sep)):
            continue
        try:
            os.remove(real)
        except OSError:
            pass
