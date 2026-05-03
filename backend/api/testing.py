"""Test-only endpoints. Only mounted when STUB_PROVIDERS=true or ALLOW_RESET=true."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from ..database import get_db
from ..models import Chat, Message, Attachment, GeneratedImage
from ..config import settings

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/reset", status_code=204)
async def reset_db(
    db: AsyncSession = Depends(get_db),
    x_reset_secret: str | None = Header(default=None),
):
    """Delete all data — E2E test isolation helper."""
    if settings.reset_secret and x_reset_secret != settings.reset_secret:
        raise HTTPException(403, "Invalid or missing X-Reset-Secret header")
    await db.execute(delete(GeneratedImage))
    await db.execute(delete(Attachment))
    await db.execute(delete(Message))
    await db.execute(delete(Chat))
    await db.commit()
