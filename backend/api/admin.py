import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import provider_access as pa
from ..auth import get_current_profile
from ..config import settings
from ..database import get_db
from ..models import Profile, SystemConfig

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(current: Profile) -> None:
    if not settings.admin or current.name.lower() != settings.admin.lower():
        raise HTTPException(403, "Admin access required")


class ProviderAccessBody(BaseModel):
    openai: bool
    anthropic: bool
    ollama: bool


@router.get("/provider-access")
async def get_provider_access(
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current)
    defaults = await pa.get_defaults(db)
    result = await db.execute(select(Profile).order_by(func.lower(Profile.name)))
    profiles = result.scalars().all()
    users = [
        {
            "id": p.id,
            "name": p.name,
            "avatar": p.avatar,
            "avatar_color": p.avatar_color,
            "provider_access": json.loads(p.provider_access) if p.provider_access else None,
            "effective_access": pa.effective_access(p, defaults),
        }
        for p in profiles
    ]
    return {"defaults": defaults, "users": users}


@router.put("/provider-access/defaults", status_code=204)
async def update_defaults(
    body: ProviderAccessBody,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current)
    row = await db.get(SystemConfig, pa._CONFIG_KEY)
    value = json.dumps({"openai": body.openai, "anthropic": body.anthropic, "ollama": body.ollama})
    if row is None:
        db.add(SystemConfig(key=pa._CONFIG_KEY, value=value))
    else:
        row.value = value
    await db.commit()


@router.put("/provider-access/{profile_id}", status_code=204)
async def update_profile_access(
    profile_id: int,
    body: ProviderAccessBody,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current)
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    profile.provider_access = json.dumps({"openai": body.openai, "anthropic": body.anthropic, "ollama": body.ollama})
    await db.commit()


@router.delete("/provider-access/{profile_id}", status_code=204)
async def reset_profile_access(
    profile_id: int,
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current)
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(404, "Profile not found")
    profile.provider_access = None
    await db.commit()
