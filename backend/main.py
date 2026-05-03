import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .database import init_db
from .api.router import router
from .config import settings
from .model_registry import refresh as refresh_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        await refresh_models()
    except Exception:
        pass  # startup continues with fallback model list
    yield


app = FastAPI(title="SimpleChat", lifespan=lifespan)

app.include_router(router)

# serve generated images
os.makedirs(settings.generated_dir, exist_ok=True)
app.mount("/generated", StaticFiles(directory=settings.generated_dir), name="generated")

# serve the React SPA (built into ./static)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(_static_dir, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
