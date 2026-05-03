from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload
from ..database import get_db
from ..models import Chat, Message
from ..schemas import ChatCreate, ChatUpdate, ChatRead, MessageRead, PROVIDER_DEFAULTS

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=list[ChatRead])
async def list_chats(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Chat).order_by(desc(Chat.updated_at)))
    return result.scalars().all()


@router.post("", response_model=ChatRead)
async def create_chat(body: ChatCreate, db: AsyncSession = Depends(get_db)):
    model = body.model or PROVIDER_DEFAULTS.get(body.provider, "gpt-4o")
    chat = Chat(title=body.title, provider=body.provider, model=model)
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatRead)
async def get_chat(chat_id: int, db: AsyncSession = Depends(get_db)):
    chat = await db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    return chat


@router.patch("/{chat_id}", response_model=ChatRead)
async def update_chat(chat_id: int, body: ChatUpdate, db: AsyncSession = Depends(get_db)):
    chat = await db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    if body.title is not None:
        chat.title = body.title
    if body.web_search_enabled is not None:
        chat.web_search_enabled = body.web_search_enabled
    if body.model is not None:
        chat.model = body.model
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(chat_id: int, db: AsyncSession = Depends(get_db)):
    chat = await db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    await db.delete(chat)
    await db.commit()


@router.get("/{chat_id}/messages", response_model=list[MessageRead])
async def list_messages(chat_id: int, db: AsyncSession = Depends(get_db)):
    chat = await db.get(Chat, chat_id)
    if not chat:
        raise HTTPException(404, "Chat not found")
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(selectinload(Message.generated_images))
        .order_by(Message.created_at)
    )
    return result.scalars().all()
