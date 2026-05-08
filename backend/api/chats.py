import os

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..event_logging import log_event
from ..models import Attachment, Chat, Dataset, GeneratedImage, Message, Profile, utcnow
from ..schemas import (
    PROVIDER_DEFAULTS,
    ChatCreate,
    ChatRead,
    ChatUpdate,
    MessageRead,
    MessageSearchResult,
)
from .deps import get_owned_chat

router = APIRouter(prefix="/chats", tags=["chats"])


@router.get("/messages/search", response_model=list[MessageSearchResult])
async def search_messages(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    q_safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = await db.execute(
        select(Message, Chat)
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Chat.profile_id == profile.id,
            Chat.discarded_at.is_(None),
            Message.content.ilike(f"%{q_safe}%", escape="\\"),
        )
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    rows = result.all()
    return [
        MessageSearchResult(
            message_id=msg.id,
            chat_id=chat.id,
            chat_title=chat.title,
            chat_provider=chat.provider,
            chat_model=chat.model,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )
        for msg, chat in rows
    ]


@router.get("", response_model=list[ChatRead])
async def list_chats(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Chat)
        .where(Chat.profile_id == profile.id, Chat.discarded_at.is_(None))
        .order_by(desc(Chat.updated_at))
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


_PROVIDER_KEY_ATTRS = {"openai": "openai_api_key", "anthropic": "anthropic_api_key"}
_PROVIDER_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic"}


@router.post("", response_model=ChatRead, status_code=201)
async def create_chat(
    body: ChatCreate,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    key_attr = _PROVIDER_KEY_ATTRS.get(body.provider)
    if (
        key_attr
        and not getattr(settings, key_attr, None)
        and not settings.stub_providers
    ):
        label = _PROVIDER_LABELS.get(body.provider, body.provider)
        raise HTTPException(
            status_code=503, detail=f"{label} is not configured on this server"
        )
    model = body.model or PROVIDER_DEFAULTS.get(body.provider, "gpt-4o")
    if body.dataset_id is not None:
        ds = await db.get(Dataset, body.dataset_id)
        if not ds or ds.profile_id != profile.id:
            raise HTTPException(404, "Dataset not found")
    chat = Chat(
        profile_id=profile.id,
        title=body.title or "New Chat",
        title_is_default=(body.title is None),
        provider=body.provider,
        model=model,
        dataset_id=body.dataset_id,
    )
    db.add(chat)
    await db.commit()
    await db.refresh(chat)
    log_event(
        profile.name,
        "create_chat",
        chat_id=chat.id,
        provider=chat.provider,
        model=chat.model,
    )
    return chat


@router.get("/{chat_id}", response_model=ChatRead)
async def get_chat(
    chat_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    return await get_owned_chat(chat_id, profile.id, db)


@router.patch("/{chat_id}", response_model=ChatRead)
async def update_chat(
    chat_id: int,
    body: ChatUpdate,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await get_owned_chat(chat_id, profile.id, db)
    if body.title is not None:
        chat.title = body.title
        chat.title_is_default = False
    if body.web_search_enabled is not None:
        chat.web_search_enabled = body.web_search_enabled
    if body.model is not None:
        if not settings.allow_switching_models:
            raise HTTPException(
                status_code=403, detail="Switching models is disabled on this server"
            )
        chat.model = body.model
    if body.provider is not None:
        if not settings.allow_switching_models:
            raise HTTPException(
                status_code=403, detail="Switching models is disabled on this server"
            )
        chat.provider = body.provider
    if "dataset_id" in body.model_fields_set:
        if body.dataset_id is not None:
            ds = await db.get(Dataset, body.dataset_id)
            if not ds or ds.profile_id != profile.id:
                raise HTTPException(404, "Dataset not found")
        chat.dataset_id = body.dataset_id
    await db.commit()
    await db.refresh(chat)
    return chat


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await get_owned_chat(chat_id, profile.id, db)

    if settings.soft_delete:
        chat.discarded_at = utcnow()
        await db.commit()
        log_event(profile.name, "discard_chat", chat_id=chat_id)
        return

    att_result = await db.execute(
        select(Attachment.path).where(Attachment.chat_id == chat.id)
    )
    img_result = await db.execute(
        select(GeneratedImage.path).where(GeneratedImage.chat_id == chat.id)
    )
    file_paths = [r[0] for r in att_result.all()] + [r[0] for r in img_result.all()]

    await db.delete(chat)
    await db.commit()

    log_event(profile.name, "delete_chat", chat_id=chat_id)
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
    await get_owned_chat(chat_id, profile.id, db)
    q = (
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(selectinload(Message.generated_images), selectinload(Message.attachments))
        .order_by(Message.created_at)
        .offset(offset)
    )
    if limit is not None:
        q = q.limit(limit)
    result = await db.execute(q)
    return result.scalars().all()
