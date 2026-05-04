from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Chat


async def get_owned_chat(chat_id: int, profile_id: int, db: AsyncSession) -> Chat:
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile_id or chat.discarded_at is not None:
        raise HTTPException(404, "Chat not found")
    return chat
