import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import router
from .config import settings
from .database import run_migrations
from .model_registry import refresh as refresh_models


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs("./data", exist_ok=True)
    await run_migrations()
    try:
        await refresh_models()
    except Exception:
        pass  # startup continues with fallback model list
    yield


app = FastAPI(title="SimpleChat", lifespan=lifespan)

app.include_router(router)

# StaticFiles requires the directory to exist at mount time (before lifespan runs)
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
