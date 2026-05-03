import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_profile
from ..database import get_db
from ..models import Attachment, Chat, GeneratedImage, Message, Profile
from ..schemas import PROVIDER_DEFAULTS, ChatCreate, ChatRead, ChatUpdate, MessageRead

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("", response_model=list[ChatRead])
async def list_chats(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Chat)
        .where(Chat.profile_id == profile.id)
        .order_by(desc(Chat.updated_at))
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("", response_model=ChatRead)
async def create_chat(
    body: ChatCreate,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    model = body.model or PROVIDER_DEFAULTS.get(body.provider, "gpt-4o")
    chat = Chat(
        profile_id=profile.id,
        title=body.title or "New Chat",
        title_is_default=(body.title is None),
        provider=body.provider,
        model=model,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    return chat


@router.get("/{chat_id}", response_model=ChatRead)
async def get_chat(
    chat_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile.id:
        raise HTTPException(404, "Chat not found")
    return chat


@router.patch("/{chat_id}", response_model=ChatRead)
async def update_chat(
    chat_id: int,
    body: ChatUpdate,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile.id:
        raise HTTPException(404, "Chat not found")
    if body.title is not None:
        chat.title = body.title
        chat.title_is_default = False
    if body.web_search_enabled is not None:
        chat.web_search_enabled = body.web_search_enabled
    if body.model is not None:
        chat.model = body.model
    if body.provider is not None:
        chat.provider = body.provider
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile.id:
        raise HTTPException(404, "Chat not found")

    att_result = await db.execute(select(Attachment.path).where(Attachment.chat_id == chat_id))
    img_result = await db.execute(select(GeneratedImage.path).where(GeneratedImage.chat_id == chat_id))
    file_paths = [r[0] for r in att_result.all()] + [r[0] for r in img_result.all()]

    await db.delete(chat)
    await db.commit()

    for path in file_paths:
        try:
            os.remove(path)
        except OSError:
            pass


@router.get("/{chat_id}/messages", response_model=list[MessageRead])
async def list_messages(
    chat_id: int,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile.id:
        raise HTTPException(404, "Chat not found")
    q = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(selectinload(Message.generated_images))
        .order_by(Message.created_at)
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()
