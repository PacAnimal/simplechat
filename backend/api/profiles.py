from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_token, get_current_profile, hash_password, verify_password
from ..config import settings
from ..net import is_local
from ..database import get_db
from ..models import Profile
from ..schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChange,
    ProfileAvatarUpdate,
    ProfileCreate,
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
    result = await db.execute(select(Profile).order_by(Profile.created_at))
    return result.scalars().all()


@router.post("", response_model=ProfileRead, status_code=201)
async def create_profile(request: Request, body: ProfileCreate, db: AsyncSession = Depends(get_db)):
    if not _can_create(request):
        raise HTTPException(403, "Profile creation is not allowed from this address")
    existing = await db.execute(select(Profile).where(Profile.name == body.name))
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
    return profile


@router.post("/{profile_id}/login", response_model=LoginResponse)
async def login(profile_id: int, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    if not verify_password(body.password, profile.password_hash):
        raise HTTPException(401, "Incorrect password")
    return LoginResponse(token=create_token(profile.id), profile=ProfileRead.model_validate(profile))


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
    await db.commit()
    await db.refresh(current)
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
    await db.commit()


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(
    profile_id: int,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    if current.id != profile_id:
        raise HTTPException(403, "Cannot delete another profile")
    await db.delete(current)
    await db.commit()
