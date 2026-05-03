from fastapi import APIRouter, Request

from ..config import settings
from .chats import router as chats_router
from .files import router as files_router
from .models import router as models_router
from .profiles import _can_create
from .profiles import router as profiles_router
from .stream import router as stream_router

router = APIRouter(prefix="/api")
router.include_router(profiles_router)
router.include_router(chats_router)
router.include_router(stream_router)
router.include_router(files_router)
router.include_router(models_router)


@router.get("/config")
async def get_config(request: Request):
    return {"can_create_profile": _can_create(request)}


if settings.stub_providers or settings.allow_reset:
    from .testing import router as testing_router
    router.include_router(testing_router)
