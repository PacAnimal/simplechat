import secrets

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models import Profile
from ..schemas import (
    ChatCreate,
    ChatRead,
    ChatUpdate,
    MessageRead,
    ProfileRead,
    SendMessageRequest,
)
from . import chats as chats_api
from . import images as images_api
from . import models as models_api
from . import stream as stream_api

router = APIRouter(prefix="/remote", tags=["remote"])

# The header a trusted remote system presents. Deliberately not an Authorization scheme: this is one
# server vouching for itself, not a user logging in, and keeping it off Authorization stops a proxy or a
# client library treating it as a credential it should refresh.
SECRET_HEADER = "X-Remote-Control-Secret"


async def require_remote_secret(
    x_remote_control_secret: str | None = Header(default=None),
) -> None:
    """Gate for every route below.

    Read from settings per request rather than captured at import, so the surface can be switched on and
    off without a code change. An unset secret disables the whole namespace — a server nobody configured
    for this must never accept it by accident.
    """
    if not settings.remote_control_shared_secret:
        raise HTTPException(503, "Remote control is not enabled on this server")
    if not x_remote_control_secret or not secrets.compare_digest(
        x_remote_control_secret, settings.remote_control_shared_secret
    ):
        raise HTTPException(401, "Invalid remote control secret")


async def acting_profile(
    profile_id: int,
    _: None = Depends(require_remote_secret),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    """The user this request runs as — the one dependency every route past /profiles carries.

    Resolving it here is what makes the namespace self-contained: each route below hands this profile to
    the very handler the web app's own route uses, so there is one implementation of listing a chat or
    sending a message, not two that can drift apart.
    """
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    return profile


@router.get("/profiles", response_model=list[ProfileRead])
async def list_profiles(
    _: None = Depends(require_remote_secret), db: AsyncSession = Depends(get_db)
):
    """Every user on this server, name-sorted — what the remote system offers for selection."""
    result = await db.execute(select(Profile).order_by(func.lower(Profile.name)))
    return result.scalars().all()


@router.get("/profiles/{profile_id}/models")
async def list_models(
    acting: Profile = Depends(acting_profile), db: AsyncSession = Depends(get_db)
):
    return await models_api.list_models(current=acting, db=db)


@router.get("/profiles/{profile_id}/chats", response_model=list[ChatRead])
async def list_chats(
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    return await chats_api.list_chats(limit=limit, offset=offset, profile=acting, db=db)


@router.post("/profiles/{profile_id}/chats", response_model=ChatRead, status_code=201)
async def create_chat(
    body: ChatCreate,
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    return await chats_api.create_chat(body=body, profile=acting, db=db)


@router.get("/profiles/{profile_id}/chats/{chat_id}", response_model=ChatRead)
async def get_chat(
    chat_id: int,
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    return await chats_api.get_chat(chat_id=chat_id, profile=acting, db=db)


@router.patch("/profiles/{profile_id}/chats/{chat_id}", response_model=ChatRead)
async def update_chat(
    chat_id: int,
    body: ChatUpdate,
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    return await chats_api.update_chat(
        chat_id=chat_id, body=body, profile=acting, db=db
    )


@router.delete("/profiles/{profile_id}/chats/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: int,
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    await chats_api.delete_chat(chat_id=chat_id, profile=acting, db=db)


@router.get(
    "/profiles/{profile_id}/chats/{chat_id}/messages",
    response_model=list[MessageRead],
)
async def list_messages(
    chat_id: int,
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    return await chats_api.list_messages(
        chat_id=chat_id, limit=limit, offset=offset, profile=acting, db=db
    )


@router.post("/profiles/{profile_id}/chats/{chat_id}/messages")
async def send_message(
    request: Request,
    chat_id: int,
    body: SendMessageRequest = Body(...),
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
):
    """Send as this user and stream the reply back — the same SSE body the web app reads."""
    return await stream_api.send_message(
        request=request, chat_id=chat_id, body=body, profile=acting, db=db
    )


@router.get("/profiles/{profile_id}/generated/{filename}", include_in_schema=False)
async def generated_image(
    filename: str,
    acting: Profile = Depends(acting_profile),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """An image this user's chats produced. `MessageRead.images[].url` names the file."""
    return await images_api.serve_for_profile(filename, acting.id, db)
