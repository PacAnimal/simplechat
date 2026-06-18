"""Tests for admin provider-access endpoints."""

import pytest
from httpx import AsyncClient

from backend.config import settings

pytestmark = pytest.mark.asyncio


async def _make_admin_client(c: AsyncClient, monkeypatch) -> AsyncClient:
    """Create an admin profile, log in, and patch settings.admin."""
    r = await c.post(
        "/api/profiles", json={"name": "Admin", "password": "adminPass1", "avatar": 0}
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]
    r2 = await c.post(f"/api/profiles/{profile_id}/login", json={"password": "adminPass1"})
    assert r2.status_code == 200, r2.text
    token = r2.json()["token"]
    monkeypatch.setattr(settings, "admin", "Admin")
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


async def _make_user(c: AsyncClient, name: str = "Alice") -> int:
    r = await c.post(
        "/api/profiles", json={"name": name, "password": "userPass1", "avatar": 0}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ─── get provider access ───────────────────────────────────────────────────────

async def test_get_provider_access_requires_admin(client: AsyncClient):
    r = await client.get("/api/admin/provider-access")
    assert r.status_code == 403


async def test_get_provider_access_returns_defaults_and_users(
    unauthed_client: AsyncClient, monkeypatch
):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    await _make_user(c, "Bob")

    r = await c.get("/api/admin/provider-access")
    assert r.status_code == 200
    data = r.json()
    assert data["defaults"] == {"openai": True, "anthropic": True, "ollama": True}
    assert len(data["users"]) == 2  # admin + Bob
    names = {u["name"] for u in data["users"]}
    assert "Admin" in names and "Bob" in names


async def test_get_provider_access_user_inherits_defaults(
    unauthed_client: AsyncClient, monkeypatch
):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    r = await c.get("/api/admin/provider-access")
    assert r.status_code == 200
    data = r.json()
    for u in data["users"]:
        assert u["provider_access"] is None  # no custom override yet
        assert u["effective_access"] == {"openai": True, "anthropic": True, "ollama": True}


# ─── update defaults ──────────────────────────────────────────────────────────

async def test_update_defaults_requires_admin(client: AsyncClient):
    r = await client.put(
        "/api/admin/provider-access/defaults",
        json={"openai": False, "anthropic": True, "ollama": False},
    )
    assert r.status_code == 403


async def test_update_defaults_persists(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)

    r = await c.put(
        "/api/admin/provider-access/defaults",
        json={"openai": False, "anthropic": True, "ollama": False},
    )
    assert r.status_code == 204

    r2 = await c.get("/api/admin/provider-access")
    assert r2.json()["defaults"] == {"openai": False, "anthropic": True, "ollama": False}


async def test_new_user_inherits_updated_defaults(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)

    await c.put(
        "/api/admin/provider-access/defaults",
        json={"openai": True, "anthropic": False, "ollama": False},
    )
    user_id = await _make_user(c)

    r = await c.get("/api/admin/provider-access")
    user = next(u for u in r.json()["users"] if u["id"] == user_id)
    assert user["effective_access"] == {"openai": True, "anthropic": False, "ollama": False}


# ─── update per-user access ───────────────────────────────────────────────────

async def test_update_user_access_requires_admin(client: AsyncClient):
    r = await client.put(
        "/api/admin/provider-access/99",
        json={"openai": True, "anthropic": True, "ollama": True},
    )
    assert r.status_code == 403


async def test_update_user_access_persists(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    user_id = await _make_user(c)

    r = await c.put(
        f"/api/admin/provider-access/{user_id}",
        json={"openai": True, "anthropic": False, "ollama": True},
    )
    assert r.status_code == 204

    r2 = await c.get("/api/admin/provider-access")
    user = next(u for u in r2.json()["users"] if u["id"] == user_id)
    assert user["provider_access"] == {"openai": True, "anthropic": False, "ollama": True}
    assert user["effective_access"] == {"openai": True, "anthropic": False, "ollama": True}


async def test_update_user_access_overrides_defaults(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    user_id = await _make_user(c)

    # set default: all off
    await c.put(
        "/api/admin/provider-access/defaults",
        json={"openai": False, "anthropic": False, "ollama": False},
    )
    # give user explicit access to openai only
    await c.put(
        f"/api/admin/provider-access/{user_id}",
        json={"openai": True, "anthropic": False, "ollama": False},
    )

    r = await c.get("/api/admin/provider-access")
    user = next(u for u in r.json()["users"] if u["id"] == user_id)
    assert user["effective_access"]["openai"] is True
    assert user["effective_access"]["anthropic"] is False


async def test_update_nonexistent_user_returns_404(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    r = await c.put(
        "/api/admin/provider-access/9999",
        json={"openai": True, "anthropic": True, "ollama": True},
    )
    assert r.status_code == 404


async def test_reset_user_access_clears_override(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    user_id = await _make_user(c)

    # set custom access
    await c.put(
        f"/api/admin/provider-access/{user_id}",
        json={"openai": False, "anthropic": True, "ollama": True},
    )

    # reset
    r = await c.delete(f"/api/admin/provider-access/{user_id}")
    assert r.status_code == 204

    # user should be back on defaults
    r2 = await c.get("/api/admin/provider-access")
    user = next(u for u in r2.json()["users"] if u["id"] == user_id)
    assert user["provider_access"] is None
    assert user["effective_access"] == {"openai": True, "anthropic": True, "ollama": True}


async def test_reset_nonexistent_user_returns_404(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    r = await c.delete("/api/admin/provider-access/9999")
    assert r.status_code == 404


# ─── enforcement ──────────────────────────────────────────────────────────────

async def test_disabled_provider_blocks_chat_creation(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    user_id = await _make_user(c)

    # disable openai for this user
    await c.put(
        f"/api/admin/provider-access/{user_id}",
        json={"openai": False, "anthropic": True, "ollama": True},
    )

    # log in as that user
    r = await c.post(f"/api/profiles/{user_id}/login", json={"password": "userPass1"})
    user_token = r.json()["token"]
    c.headers.update({"Authorization": f"Bearer {user_token}"})

    r2 = await c.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r2.status_code == 403


async def test_disabled_provider_hidden_in_models(unauthed_client: AsyncClient, monkeypatch):
    c = await _make_admin_client(unauthed_client, monkeypatch)
    user_id = await _make_user(c)

    await c.put(
        f"/api/admin/provider-access/{user_id}",
        json={"openai": False, "anthropic": True, "ollama": False},
    )

    r = await c.post(f"/api/profiles/{user_id}/login", json={"password": "userPass1"})
    user_token = r.json()["token"]
    c.headers.update({"Authorization": f"Bearer {user_token}"})

    r2 = await c.get("/api/models")
    assert r2.status_code == 200
    models = r2.json()
    assert "openai" not in models
    assert "anthropic" in models
