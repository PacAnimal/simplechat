from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from jwt.exceptions import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .database import get_db
from .models import Profile, utcnow

_ALGORITHM = "HS256"
_TOKEN_TTL_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def invalidate_tokens(profile: Profile) -> None:
    """Revoke all tokens issued to this profile before now."""
    profile.token_invalidated_at = utcnow()


def create_token(profile_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(profile_id),
        "iat": int(now.timestamp()),
        "exp": now + timedelta(days=_TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


async def get_current_profile(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> Profile:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid authorization header"
        )
    token = authorization[7:]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        profile_id = int(payload["sub"])
        issued_at = payload.get("iat")
    except (PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    profile = await db.get(Profile, profile_id)
    if not profile:
        raise HTTPException(status_code=401, detail="Profile not found")
    if issued_at and profile.token_invalidated_at:
        token_time = datetime.fromtimestamp(issued_at, tz=timezone.utc)
        if token_time <= profile.token_invalidated_at:
            raise HTTPException(status_code=401, detail="Token has been revoked")
    return profile
