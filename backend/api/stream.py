import asyncio
import json
import logging
import time

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .. import sse_events
from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..event_logging import log_event
from ..models import Attachment, Chat, GeneratedImage, Message, Profile, utcnow
from ..providers import AnthropicProvider, OpenAIProvider
from ..providers.stub_provider import StubProvider
from ..schemas import SendMessageRequest
from .deps import get_owned_chat

logger = logging.getLogger(__name__)

_TEXT_MIME_TYPES = {"text/plain", "text/markdown", "text/csv", "application/json"}

# per-profile rate limiting: one active stream + 1s holdoff between messages
_profile_locks: dict[int, asyncio.Lock] = {}
_profile_last_done: dict[int, float] = {}
_HOLDOFF_SECS = 1.0


def _get_profile_lock(pid: int) -> asyncio.Lock:
    if pid not in _profile_locks:
        _profile_locks[pid] = asyncio.Lock()
    return _profile_locks[pid]


async def _attachment_text(att: Attachment) -> str:
    if att.mime_type not in _TEXT_MIME_TYPES:
        return ""
    try:
        async with aiofiles.open(att.path, encoding="utf-8", errors="replace") as f:
            body = await f.read()
        return f"\n\n[Attached file: {att.filename}]\n```\n{body}\n```"
    except Exception:
        return ""


router = APIRouter(prefix="/chats", tags=["stream"])


_PROVIDER_KEYS = {"openai": "openai_api_key", "anthropic": "anthropic_api_key"}
_PROVIDER_LABELS = {"openai": "OpenAI", "anthropic": "Anthropic"}


def _check_provider_configured(provider: str) -> None:
    """Raise 503 before the stream starts so the status code is still settable."""
    key_attr = _PROVIDER_KEYS.get(provider)
    if key_attr and not getattr(settings, key_attr, None):
        label = _PROVIDER_LABELS.get(provider, provider)
        raise HTTPException(status_code=503, detail=f"{label} is not configured on this server")


def _get_provider(chat: Chat):
    if settings.stub_providers:
        return StubProvider(chat.provider)
    if chat.provider == "openai":
        return OpenAIProvider()
    if chat.provider == "anthropic":
        return AnthropicProvider()
    raise HTTPException(status_code=400, detail=f"Unknown provider: {chat.provider}")


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


async def _save_user_message(
    chat_id: int, user_content: str, attachment_ids: list[int], db: AsyncSession
) -> Message:
    user_msg = Message(chat_id=chat_id, role="user", content=user_content)
    db.add(user_msg)
    await db.commit()
    await db.refresh(user_msg)
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
    return user_msg


async def _save_assistant_message(
    chat_id: int,
    content: str,
    thinking: str | None,
    generated_images: list[dict],
    chat: Chat,
    db: AsyncSession,
) -> Message:
    assistant_msg = Message(
        chat_id=chat_id, role="assistant", content=content, thinking=thinking
    )
    db.add(assistant_msg)
    chat.updated_at = utcnow()
    await db.commit()
    await db.refresh(assistant_msg)
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
    return assistant_msg


async def _generate_chat_title(
    user_content: str, assistant_content: str, provider: str
) -> str:
    """Use a lightweight LLM call to produce a short chat title (5 words max)."""
    if settings.stub_providers:
        return user_content[:60].strip() or "New Chat"
    prompt = (
        f"User: {user_content[:400]}\nAssistant: {assistant_content[:400]}\n\n"
        "Write a short title for this conversation (5 words max). "
        "Only the title — no quotes, no punctuation."
    )
    try:
        if provider == "anthropic" and settings.anthropic_api_key:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            resp = await client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()[:100]
        if provider == "openai" and settings.openai_api_key:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=settings.openai_api_key)
            resp = await client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            return (resp.choices[0].message.content or "").strip()[:100]
    except Exception:
        logger.exception("Title generation failed")
    return user_content[:60].strip() or "New Chat"


async def _event_stream(
    chat: Chat,
    user_content: str,
    attachment_ids: list[int],
    db: AsyncSession,
    request: Request,
    lock: asyncio.Lock,
    profile_id: int,
):
    lock_released = False

    def _release_lock():
        nonlocal lock_released
        if not lock_released:
            lock_released = True
            _profile_last_done[profile_id] = time.monotonic()
            lock.release()

    try:
        await _save_user_message(chat.id, user_content, attachment_ids, db)
        messages = await _build_messages(chat.id, db)
        provider = _get_provider(chat)

        full_content = ""
        thinking_content = ""
        generated_images: list[dict] = []

        async def _watch_disconnect():
            while not await request.is_disconnected():
                await asyncio.sleep(0.3)

        disconnect_task = asyncio.create_task(_watch_disconnect())
        try:
            stream = provider.stream_chat(messages, chat.model, chat.web_search_enabled)
            async for event in stream:
                if disconnect_task.done():
                    logger.info("Client disconnected mid-stream for chat %d", chat.id)
                    return
                etype = event.get("type")
                if etype == sse_events.TEXT_DELTA:
                    full_content += event.get("content", "")
                elif etype == sse_events.THINKING_DELTA:
                    thinking_content += event.get("content", "")
                elif etype == sse_events.IMAGE_GENERATED:
                    generated_images.append(event)
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            disconnect_task.cancel()

        assistant_msg = await _save_assistant_message(
            chat.id, full_content, thinking_content or None, generated_images, chat, db
        )

        # release lock here so the user can send another message while title generates
        yield f"data: {json.dumps({'type': sse_events.DONE, 'message_id': assistant_msg.id})}\n\n"
        _release_lock()

        if chat.title_is_default:
            title = await _generate_chat_title(
                user_content, full_content, chat.provider
            )
            chat.title = title
            chat.title_is_default = False
            await db.commit()
            yield f"data: {json.dumps({'type': sse_events.CHAT_TITLE, 'title': title})}\n\n"

    except Exception as e:
        logger.exception("Stream error for chat %d", chat.id)
        yield f"data: {json.dumps({'type': sse_events.ERROR, 'message': str(e)})}\n\n"
    finally:
        _release_lock()


@router.post("/{chat_id}/messages")
async def send_message(
    request: Request,
    chat_id: int,
    body: SendMessageRequest,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    # verify ownership before acquiring lock — prevents lock leak on 404
    chat = await get_owned_chat(chat_id, profile.id, db)

    if not settings.stub_providers:
        _check_provider_configured(chat.provider)

    lock = _get_profile_lock(profile.id)
    if lock.locked():
        raise HTTPException(
            429, "A message is already being processed for this profile"
        )
    await lock.acquire()

    last_done = _profile_last_done.get(profile.id, 0.0)
    holdoff = _HOLDOFF_SECS - (time.monotonic() - last_done)
    if holdoff > 0:
        await asyncio.sleep(holdoff)

    log_event(profile.name, "send_message", chat_id=chat_id)

    return StreamingResponse(
        _event_stream(
            chat, body.content, body.attachment_ids, db, request, lock, profile.id
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
