"""Security regression tests — one test per fixed vulnerability."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

# explicit asyncio mark per test rather than module-level to avoid warnings on sync tests


def _make_token(profile_id: int, secret: str, *, delta_days: int = 1) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(profile_id),
        "iat": int(now.timestamp()),
        "exp": now + timedelta(days=delta_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def _create_and_login(
    c: AsyncClient, name: str, password: str
) -> tuple[int, str]:
    r = await c.post(
        "/api/profiles", json={"name": name, "password": password, "avatar": 0}
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    lr = await c.post(f"/api/profiles/{pid}/login", json={"password": password})
    assert lr.status_code == 200
    return pid, lr.json()["token"]


# ---------------------------------------------------------------------------
# SEC-002: Reset endpoint fails closed when reset_secret is None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_blocked_when_no_secret_configured():
    """When RESET_SECRET is not set, the reset endpoint must always return 403."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException

    import backend.api.testing as m

    original = m.settings.reset_secret
    m.settings.reset_secret = None
    try:
        db = AsyncMock()
        db.execute.return_value = MagicMock(
            **{"scalars.return_value.all.return_value": []}
        )
        with pytest.raises(HTTPException) as exc:
            await m.reset_db(db=db, x_reset_secret=None)
        assert exc.value.status_code == 403
    finally:
        m.settings.reset_secret = original


# ---------------------------------------------------------------------------
# SEC-005: Token revocation after password change
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_revoked_after_password_change(
    client: AsyncClient, unauthed_client: AsyncClient
):
    """A token issued before a password change must be rejected afterward."""
    old_token = client.auth.token  # type: ignore[union-attr]

    profiles_r = await unauthed_client.get("/api/profiles")
    profile_id = profiles_r.json()[0]["id"]

    r = await client.post(
        f"/api/profiles/{profile_id}/change-password",
        json={"current_password": "testPass1", "new_password": "newPass1!"},
    )
    assert r.status_code == 204

    # use a fresh client so no auth fixture interferes
    from backend.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        r2 = await c.get("/api/chats", headers={"Authorization": f"Bearer {old_token}"})
    assert r2.status_code == 401


# ---------------------------------------------------------------------------
# SEC-012: Generated images require Bearer authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generated_image_requires_bearer_auth(unauthed_client: AsyncClient):
    """Unauthenticated requests to /api/generated/ must get 401, not 200."""
    r = await unauthed_client.get("/api/generated/anything.png")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generated_image_rejects_invalid_token(unauthed_client: AsyncClient):
    """Requests with a forged/invalid Bearer token must get 401."""
    r = await unauthed_client.get(
        "/api/generated/anything.png",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_generated_image_rejects_query_param_token(unauthed_client: AsyncClient):
    """Tokens must NOT be accepted via query parameter — Bearer header only."""
    from backend.config import settings

    token = _make_token(1, settings.jwt_secret)
    # clear client auth so we can test the endpoint directly
    old_auth = unauthed_client.auth
    unauthed_client.auth = None
    try:
        r = await unauthed_client.get(f"/api/generated/anything.png?token={token}")
        assert r.status_code == 401
    finally:
        unauthed_client.auth = old_auth


@pytest.mark.asyncio
async def test_generated_image_ownership_enforced(
    client: AsyncClient, unauthed_client: AsyncClient
):
    """A profile must not be able to access another profile's generated image."""
    from backend.config import settings
    from backend.main import app

    # create thief profile via unauthed_client (shares same DB override as the app)
    _, tok_b = await _create_and_login(unauthed_client, "img_thief", "ThiefPass1")

    create_r = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    assert create_r.status_code == 201
    chat_id = create_r.json()["id"]

    gen_dir = settings.generated_dir
    os.makedirs(gen_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", dir=gen_dir, delete=False) as f:
        f.write(b"\x89PNG\r\n")
        img_path = os.path.realpath(
            f.name
        )  # resolve symlinks (/tmp → /private/tmp on macOS)
    filename = os.path.basename(img_path)

    async def mock_stream(self, messages, model, web_search):
        yield {
            "type": "image_generated",
            "url": f"/api/generated/{filename}",
            "prompt": "test",
            "path": img_path,
        }
        yield {"type": "text_delta", "content": "done"}

    try:
        with patch(
            "backend.providers.openai_provider.OpenAIProvider._stream", mock_stream
        ):
            async with client.stream(
                "POST", f"/api/chats/{chat_id}/messages", json={"content": "draw"}
            ) as resp:
                async for _ in resp.aiter_lines():
                    pass

        # owner can access their image
        r_owner = await client.get(f"/api/generated/{filename}")
        assert r_owner.status_code == 200

        # thief uses a fresh client so testuser's auth doesn't override the token
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as thief_client:
            r_thief = await thief_client.get(
                f"/api/generated/{filename}",
                headers={"Authorization": f"Bearer {tok_b}"},
            )
        assert r_thief.status_code == 404
    finally:
        if os.path.exists(img_path):
            os.unlink(img_path)


@pytest.mark.asyncio
async def test_generated_image_dotfile_rejected(unauthed_client: AsyncClient):
    """Filenames starting with '.' must be rejected."""
    from backend.config import settings

    token = _make_token(1, settings.jwt_secret)
    old_auth = unauthed_client.auth
    unauthed_client.auth = None
    try:
        r = await unauthed_client.get(
            "/api/generated/.hidden_file",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
    finally:
        unauthed_client.auth = old_auth


# ---------------------------------------------------------------------------
# SEC-020: LIKE wildcard injection in message search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_percent_wildcard_not_matched(client: AsyncClient):
    """`%` in a search query must be treated as a literal, not a SQL wildcard."""
    r = await client.get("/api/chats/messages/search?q=%25")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_search_underscore_not_matched(client: AsyncClient):
    """`_` in a search query must be treated as a literal, not a SQL wildcard."""
    r = await client.get("/api/chats/messages/search?q=_")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# SEC-022: FastAPI docs disabled by default
# ---------------------------------------------------------------------------


def test_docs_disabled_by_default():
    """FastAPI docs_url/redoc_url must be None when SHOW_DOCS is not set."""
    from backend.config import settings
    from backend.main import app

    assert not settings.show_docs, "SHOW_DOCS must default to false"
    assert app.docs_url is None, "/docs must be disabled"
    assert app.redoc_url is None, "/redoc must be disabled"
