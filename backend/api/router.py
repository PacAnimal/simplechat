from fastapi import APIRouter

from ..config import settings
from .chats import router as chats_router
from .files import router as files_router
from .models import router as models_router
from .profiles import router as profiles_router
from .stream import router as stream_router

router = APIRouter(prefix="/api")
router.include_router(profiles_router)
router.include_router(chats_router)
router.include_router(stream_router)
router.include_router(files_router)
router.include_router(models_router)

if settings.stub_providers or settings.allow_reset:
    from .testing import router as testing_router
    router.include_router(testing_router)
