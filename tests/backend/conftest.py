import os

import httpx
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# use in-memory SQLite for tests
os.environ.setdefault("OPENAI_API_KEY", "sk-test-openai")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-anthropic")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("UPLOADS_DIR", "/tmp/simplechat_test_uploads")
os.environ.setdefault("GENERATED_DIR", "/tmp/simplechat_test_generated")

os.makedirs("/tmp/simplechat_test_uploads", exist_ok=True)
os.makedirs("/tmp/simplechat_test_generated", exist_ok=True)

from backend.database import Base, get_db  # noqa: E402
from backend.main import app  # noqa: E402

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DB_URL)
TestSession = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _override_get_db():
    async def override():
        async with TestSession() as session:
            yield session

    return override


class BearerAuth(httpx.Auth):
    """Attaches an Authorization: Bearer header to every request."""

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


async def _register_and_login(
    c: AsyncClient, name: str, password: str
) -> tuple[int, str]:
    """Create a profile and return (profile_id, token)."""
    r = await c.post(
        "/api/profiles", json={"name": name, "password": password, "avatar": 0}
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]
    login_r = await c.post(
        f"/api/profiles/{profile_id}/login", json={"password": password}
    )
    assert login_r.status_code == 200, login_r.text
    return profile_id, login_r.json()["token"]


@pytest_asyncio.fixture
async def unauthed_client():
    """Raw client with no auth headers — used for testing auth-layer behaviour."""
    app.dependency_overrides[get_db] = _override_get_db()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client(unauthed_client: AsyncClient):
    """Authenticated client pre-logged in as 'testuser'."""
    _, token = await _register_and_login(unauthed_client, "testuser", "testPass1")
    unauthed_client.auth = BearerAuth(token)
    yield unauthed_client
    unauthed_client.auth = None
