import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .api.router import router
from .config import settings
from .database import run_migrations
from .model_registry import refresh as refresh_models
from .net import is_local


def _db_dir() -> str:
    # extract the directory containing the SQLite file from the DATABASE_URL
    path = settings.database_url.replace("sqlite+aiosqlite:///", "")
    return os.path.dirname(os.path.abspath(path))


class _LocalProxyMiddleware:
    """Rewrite client IP and scheme from forwarded headers, but only for local upstream connections."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            client_ip = (scope.get("client") or ("", 0))[0]
            if is_local(client_ip):
                headers = {k: v for k, v in scope.get("headers", [])}
                xff = headers.get(b"x-forwarded-for", b"").decode()
                if xff:
                    scope = {**scope, "client": (xff.split(",")[0].strip(), 0)}
                proto = headers.get(b"x-forwarded-proto", b"").decode().strip()
                if proto:
                    scope = {**scope, "scheme": proto}
        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs(settings.generated_dir, exist_ok=True)
    os.makedirs(_db_dir(), exist_ok=True)
    await run_migrations()
    try:
        await refresh_models()
    except Exception:
        pass  # startup continues with fallback model list
    yield


app = FastAPI(title="SimpleChat", lifespan=lifespan)

if settings.incoming_http_proxy:
    app.add_middleware(_LocalProxyMiddleware)

app.include_router(router)

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
