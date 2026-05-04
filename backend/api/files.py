import json
import os
import uuid

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..models import Attachment, Profile
from ..schemas import AttachmentRead
from .deps import get_owned_chat

router = APIRouter(tags=["files"])

ALLOWED_MIME_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _validate_content(content: bytes, mime_type: str) -> None:
    """Reject files whose content doesn't match their claimed type."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "File content is not valid UTF-8 text")

    if mime_type == "application/json":
        try:
            json.loads(text)
        except Exception:
            raise HTTPException(
                415, "File claims to be JSON but content is not valid JSON"
            )


@router.post("/chats/{chat_id}/files", response_model=AttachmentRead)
async def upload_file(
    chat_id: int,
    file: UploadFile = File(...),
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_chat(chat_id, profile.id, db)

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 20 MB)")

    mime = file.content_type or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            415,
            f"Unsupported file type: {mime}. Supported: text/plain, text/markdown, text/csv, application/json",
        )

    _validate_content(content, mime)

    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(settings.uploads_dir, filename)
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    att = Attachment(
        chat_id=chat_id,
        filename=file.filename or filename,
        mime_type=mime,
        path=dest,
        size=len(content),
    )
    db.add(att)
    await db.commit()
    await db.refresh(att)
    return att


@router.get("/chats/{chat_id}/files", response_model=list[AttachmentRead])
async def list_files(
    chat_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    await get_owned_chat(chat_id, profile.id, db)
    result = await db.execute(
        select(Attachment)
        .where(Attachment.chat_id == chat_id)
        .order_by(Attachment.created_at)
    )
    return result.scalars().all()


@router.get("/files/{attachment_id}/download")
async def download_file(
    attachment_id: int,
    profile: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    att = await db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(404, "File not found")
    await get_owned_chat(att.chat_id, profile.id, db)
    if not os.path.exists(att.path):
        raise HTTPException(404, "File missing from disk")
    return FileResponse(att.path, filename=att.filename, media_type=att.mime_type)
