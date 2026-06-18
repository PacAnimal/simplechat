from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .. import provider_access as pa
from ..auth import get_current_profile
from ..database import get_db
from ..model_registry import get_models
from ..models import Profile

router = APIRouter(prefix="", tags=["models"])


@router.get("/models")
async def list_models(
    current: Profile = Depends(get_current_profile),
    db: AsyncSession = Depends(get_db),
):
    models = await get_models()
    access = await pa.get_profile_access(current, db)
    return {k: v for k, v in models.items() if k not in access or access.get(k, True)}
