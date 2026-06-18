import json

from sqlalchemy.ext.asyncio import AsyncSession

from .models import Profile, SystemConfig

_PROVIDERS = ("openai", "anthropic", "ollama")
_ALL_ENABLED = {p: True for p in _PROVIDERS}
_CONFIG_KEY = "provider_access_defaults"


async def get_defaults(db: AsyncSession) -> dict[str, bool]:
    row = await db.get(SystemConfig, _CONFIG_KEY)
    if row is None:
        return dict(_ALL_ENABLED)
    stored = json.loads(row.value)
    return {p: bool(stored.get(p, True)) for p in _PROVIDERS}


def effective_access(profile: Profile, defaults: dict[str, bool]) -> dict[str, bool]:
    if profile.provider_access is None:
        return dict(defaults)
    stored = json.loads(profile.provider_access)
    return {p: bool(stored.get(p, True)) for p in _PROVIDERS}


async def get_profile_access(profile: Profile, db: AsyncSession) -> dict[str, bool]:
    defaults = await get_defaults(db)
    return effective_access(profile, defaults)
