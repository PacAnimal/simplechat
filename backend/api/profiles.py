import asyncio
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import (
    create_token,
    get_current_profile,
    hash_password,
    invalidate_tokens,
    verify_password,
)
from ..config import settings
from ..database import get_db
from ..event_logging import log_event
from ..models import Profile
from ..net import is_local
from ..schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    ProfileAvatarUpdate,
    ProfileCreate,
    ProfileNameUpdate,
    ProfileRead,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def _can_create(request: Request) -> bool:
    if settings.create == "any":
        return True
    if settings.create == "none":
        return False
    client_ip = request.client.host if request.client else ""
    return is_local(client_ip)


@router.get("", response_model=list[ProfileRead])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).order_by(func.lower(Profile.name)))
    return result.scalars().all()


@router.post("", response_model=ProfileRead, status_code=201)
async def create_profile(
    request: Request, body: ProfileCreate, db: AsyncSession = Depends(get_db)
):
    if not _can_create(request):
        raise HTTPException(403, "Profile creation is not allowed from this address")
    existing = await db.execute(
        select(Profile).where(func.lower(Profile.name) == body.name.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Profile name already taken")
    profile = Profile(
        name=body.name,
        password_hash=hash_password(body.password),
        avatar=body.avatar,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    log_event(profile.name, "create_profile")
    return profile


@router.post("/{profile_id}/login", response_model=LoginResponse)
async def login(
    profile_id: int, body: LoginRequest, db: AsyncSession = Depends(get_db)
):
    t0 = time.monotonic()
    try:
        profile = await db.get(Profile, profile_id)
        if not profile:
            raise HTTPException(404, "Profile not found")
        if not verify_password(body.password, profile.password_hash):
            log_event(None, "login_failed", profile_id=profile_id)
            raise HTTPException(401, "Incorrect password")
        log_event(profile.name, "login")
        return LoginResponse(
            token=create_token(profile.id), profile=ProfileRead.model_validate(profile)
        )
    finally:
        elapsed = time.monotonic() - t0
        if elapsed < 4.0:
            await asyncio.sleep(4.0 - elapsed)


@router.patch("/{profile_id}/avatar", response_model=ProfileRead)
async def update_avatar(
    profile_id: int,
    body: ProfileAvatarUpdate,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if current.id != profile_id:
        raise HTTPException(403, "Cannot update another profile")
    current.avatar = body.avatar
    current.avatar_color = body.avatar_color
    await db.commit()
    await db.refresh(current)
    log_event(current.name, "update_avatar")
    return current


@router.patch("/{profile_id}/name", response_model=ProfileRead)
async def update_name(
    profile_id: int,
    body: ProfileNameUpdate,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if current.id != profile_id:
        raise HTTPException(403, "Cannot update another profile")
    existing = await db.execute(
        select(Profile).where(func.lower(Profile.name) == body.name.lower())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Profile name already taken")
    current.name = body.name
    await db.commit()
    await db.refresh(current)
    log_event(current.name, "update_name")
    return current


@router.post("/{profile_id}/change-password", status_code=204)
async def change_password(
    profile_id: int,
    body: PasswordChange,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if current.id != profile_id:
        raise HTTPException(403, "Cannot change another profile's password")
    if not verify_password(body.current_password, current.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    current.password_hash = hash_password(body.new_password)
    invalidate_tokens(current)
    await db.commit()
    log_event(current.name, "change_password")


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if current.id != profile_id:
        raise HTTPException(403, "Cannot delete another profile")
    name = current.name
    await db.delete(current)
    await db.commit()
    log_event(name, "delete_profile")
