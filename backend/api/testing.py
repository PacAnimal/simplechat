"""Test-only endpoints. Only mounted when STUB_PROVIDERS=true."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from ..database import get_db
from ..models import Chat, Message, Attachment, GeneratedImage

router = APIRouter(prefix="/test", tags=["test"])


@router.post("/reset", status_code=204)
async def reset_db(db: AsyncSession = Depends(get_db)):
    """Delete all data — E2E test isolation helper."""
    await db.execute(delete(GeneratedImage))
    await db.execute(delete(Attachment))
    await db.execute(delete(Message))
    await db.execute(delete(Chat))
    await db.commit()
