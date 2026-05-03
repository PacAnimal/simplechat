from fastapi import APIRouter

from ..model_registry import get_models

router = APIRouter(prefix="", tags=["models"])


@router.get("/models")
async def list_models():
    return await get_models()
