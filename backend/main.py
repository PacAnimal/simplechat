import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.router import router
from .app_logging import setup_loggers
from .config import settings
from .database import SessionLocal, run_migrations
from .event_logging import setup_audit_log
from .http_logging import HttpLoggingMiddleware
from .jwt_secret import resolve as resolve_jwt_secret
from .model_registry import refresh as refresh_models
from .net import is_local

setup_loggers()


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


async def _normalize_stored_paths():
    """Normalize legacy Attachment and GeneratedImage path records to bare filenames."""
    import logging

    from sqlalchemy import select

    from .models import Attachment, GeneratedImage

    logger = logging.getLogger(__name__)
    async with SessionLocal() as db:
        updated = 0
        for model in (Attachment, GeneratedImage):
            result = await db.execute(select(model))
            for row in result.scalars().all():
                if row.path and os.sep in row.path:
                    row.path = os.path.basename(row.path)
                    updated += 1
        if updated:
            await db.commit()
            logger.info("Normalized %d stored path(s) to filename", updated)


async def _warn_missing_admin():
    import logging

    from sqlalchemy import func, select

    from .models import Profile

    logger = logging.getLogger(__name__)
    async with SessionLocal() as db:
        result = await db.execute(
            select(Profile).where(func.lower(Profile.name) == settings.admin.lower())
        )
        if not result.scalar_one_or_none():
            logger.warning(
                "ADMIN is set to %r but no profile with that name exists — "
                "impersonation will be unavailable until the account is created",
                settings.admin,
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    data_dir = _db_dir()
    os.makedirs(data_dir, exist_ok=True)
    settings.jwt_secret = resolve_jwt_secret(data_dir, os.environ.get("JWT_SECRET"))
    if settings.audit_log:
        setup_audit_log(data_dir)
    os.makedirs(settings.uploads_dir, exist_ok=True)
    os.makedirs(settings.generated_dir, exist_ok=True)
    await run_migrations()
    await _normalize_stored_paths()
    if settings.admin:
        await _warn_missing_admin()
    try:
        await refresh_models()
    except Exception:
        pass  # startup continues; model cache pre-warmed on first request
    if settings.ollama_api_url:
        import asyncio

        from .rag.embedder import EMBED_MODEL, ensure_embed_model
        asyncio.create_task(ensure_embed_model(settings.ollama_api_url, EMBED_MODEL))
    yield


app = FastAPI(
    title="SimpleChat",
    lifespan=lifespan,
    docs_url="/docs" if settings.show_docs else None,
    redoc_url="/redoc" if settings.show_docs else None,
)

# logging must be added before proxy middleware so proxy rewrites IP first
app.add_middleware(HttpLoggingMiddleware)

if settings.incoming_http_proxy:
    app.add_middleware(_LocalProxyMiddleware)

app.include_router(router)

os.makedirs(settings.generated_dir, exist_ok=True)

# serve the React SPA (built into ./static)
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(_static_dir, "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        index = os.path.join(_static_dir, "index.html")
        return FileResponse(index)
