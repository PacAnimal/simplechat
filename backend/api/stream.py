import json
import logging

import aiofiles
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..models import Attachment, Chat, GeneratedImage, Message, Profile, utcnow
from ..providers import AnthropicProvider, OpenAIProvider
from ..providers.stub_provider import StubProvider
from ..schemas import SendMessageRequest

logger = logging.getLogger(__name__)

_TEXT_MIME_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}


async def _attachment_text(att: Attachment) -> str:
    if att.mime_type not in _TEXT_MIME_TYPES:
        return ""
    try:
        async with aiofiles.open(att.path, encoding="utf-8", errors="replace") as f:
            body = await f.read(50_000)
        return f"\n\n[Attached file: {att.filename}]\n```\n{body}\n```"
    except Exception:
        return ""

router = APIRouter(prefix="/chats", tags=["stream"])


def _get_provider(chat: Chat):
    if settings.stub_providers:
        return StubProvider(chat.provider)
    if chat.provider == "openai":
        return OpenAIProvider()
    if chat.provider == "anthropic":
        return AnthropicProvider()
    raise ValueError(f"Unknown provider: {chat.provider}")


async def _build_messages(chat_id: int, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .options(selectinload(Message.attachments))
        .order_by(Message.created_at)
    )
    rows = result.scalars().all()
    out = []
    for m in rows:
        if m.role == "user":
            content = m.content
            for att in m.attachments:
                content += await _attachment_text(att)
            out.append({"role": "user", "content": content})
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
    return out


async def _event_stream(chat_id: int, profile_id: int, user_content: str, attachment_ids: list[int], db: AsyncSession):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile_id:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Chat not found'})}\n\n"
        return

    # save user message
    user_msg = Message(chat_id=chat_id, role="user", content=user_content)
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)

    # link pending attachments
    if attachment_ids:
        result = await db.execute(
            select(Attachment).where(
                Attachment.id.in_(attachment_ids),
                Attachment.chat_id == chat_id,
                Attachment.message_id.is_(None),
            )
        )
        for att in result.scalars().all():
            att.message_id = user_msg.id
        await db.commit()

    messages = await _build_messages(chat_id, db)
    provider = _get_provider(chat)

    full_content = ""
    generated_images: list[dict] = []

    try:
        stream = provider._stream(messages, chat.model, chat.web_search_enabled)
        async for event in stream:
            etype = event.get("type")
            if etype == "text_delta":
                full_content += event.get("content", "")
            elif etype == "image_generated":
                generated_images.append(event)
            yield f"data: {json.dumps(event)}\n\n"

        # save assistant message and bump updated_at in one commit
        assistant_msg = Message(chat_id=chat_id, role="assistant", content=full_content)
        db.add(assistant_msg)
        chat.updated_at = utcnow()
        await db.commit()
        await db.refresh(assistant_msg)

        # record generated images
        for img in generated_images:
            gi = GeneratedImage(
                chat_id=chat_id,
                message_id=assistant_msg.id,
                prompt=img.get("prompt", ""),
                path=img.get("path", ""),
            )
            db.add(gi)
        if generated_images:
            await db.commit()

        # auto-title on first exchange when no explicit title was set
        if chat.title_is_default:
            chat.title = user_content[:60].strip() or "New Chat"
            chat.title_is_default = False
            await db.commit()
            yield f"data: {json.dumps({'type': 'chat_title', 'title': chat.title})}\n\n"

        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id})}\n\n"

    except Exception as e:
        logger.exception("Stream error for chat %d", chat_id)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: int,
    body: SendMessageRequest,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    chat = await db.get(Chat, chat_id)
    if not chat or chat.profile_id != profile.id:
        raise HTTPException(404, "Chat not found")

    return StreamingResponse(
        _event_stream(chat_id, profile.id, body.content, body.attachment_ids, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
