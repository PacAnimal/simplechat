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
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}
_BINARY_MIME_TYPES = ALLOWED_MIME_TYPES - {"text/plain", "text/markdown", "text/csv", "application/json"}

# fallback when browser sends application/octet-stream
_EXT_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


_MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/webp": [b"RIFF"],  # RIFF????WEBP — check WEBP tag at offset 8
    "image/bmp": [b"BM"],
    "application/pdf": [b"%PDF-"],
}


def _validate_content(content: bytes, mime_type: str) -> None:
    """Reject files whose content doesn't match their claimed type."""
    if mime_type in _MAGIC_BYTES:
        magic_list = _MAGIC_BYTES[mime_type]
        if not any(content.startswith(m) for m in magic_list):
            raise HTTPException(415, f"File content does not match claimed type {mime_type}")
        if mime_type == "image/webp" and len(content) >= 12 and content[8:12] != b"WEBP":
            raise HTTPException(415, "File content does not match claimed type image/webp")
        return

    if mime_type in _BINARY_MIME_TYPES:
        return  # office docs — no magic byte standard, skip

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
        # browser sometimes sends application/octet-stream — try to recover from extension
        ext = os.path.splitext(file.filename or "")[1].lower()
        mime = _EXT_TO_MIME.get(ext, mime)
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            415,
            "Unsupported file type. Supported: text, csv, json, pdf, images (png/jpeg/gif/webp), Excel (xls/xlsx), Word (docx), PowerPoint (pptx)",
        )

    _validate_content(content, mime)

    ext = os.path.splitext(file.filename or "")[1] or ".bin"
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(settings.uploads_dir, filename)
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    safe_filename = os.path.basename((file.filename or filename).replace("\r", "").replace("\n", ""))
    att = Attachment(
        chat_id=chat_id,
        filename=safe_filename or filename,
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
    full_path = os.path.realpath(att.path)
    uploads_dir = os.path.realpath(settings.uploads_dir)
    if not full_path.startswith(uploads_dir + os.sep) or not os.path.exists(full_path):
        raise HTTPException(404, "File missing from disk")
    return FileResponse(full_path, filename=att.filename, media_type=att.mime_type)
