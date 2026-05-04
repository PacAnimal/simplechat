"""Tests for password complexity requirements and PASSWORD_MIN_LENGTH override."""

import pytest
from httpx import AsyncClient

import backend.config as config_module

pytestmark = pytest.mark.asyncio

# ─── helpers ───────────────────────────────────────────────────────────────────


async def _register(c: AsyncClient, name: str, password: str) -> dict:
    r = await c.post("/api/profiles", json={"name": name, "password": password, "avatar": 0})
    return r


async def _login(c: AsyncClient, profile_id: int, password: str) -> dict:
    return await c.post(f"/api/profiles/{profile_id}/login", json={"password": password})


async def _register_and_token(c: AsyncClient, name: str, password: str) -> tuple[int, str]:
    r = await c.post("/api/profiles", json={"name": name, "password": password, "avatar": 0})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    lr = await c.post(f"/api/profiles/{pid}/login", json={"password": password})
    assert lr.status_code == 200
    return pid, lr.json()["token"]


# ─── default rules (min_length=8) ──────────────────────────────────────────────


async def test_password_too_short_rejected(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "Alice", "abc1A")  # 5 chars
    assert r.status_code == 422


async def test_password_no_digit_rejected(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "Alice", "abcdefgh")  # 8 chars, no digit
    assert r.status_code == 422


async def test_password_no_letter_rejected(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "Alice", "12345678")  # 8 chars, no letter
    assert r.status_code == 422


async def test_password_exactly_8_chars_accepted(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "Alice", "abcdefg1")  # 8 chars, letter+digit
    assert r.status_code == 201


async def test_password_change_too_short_rejected(unauthed_client: AsyncClient):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    r = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "validPw1", "new_password": "short1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_password_change_no_digit_rejected(unauthed_client: AsyncClient):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    r = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "validPw1", "new_password": "noDights!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_password_change_no_letter_rejected(unauthed_client: AsyncClient):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    r = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "validPw1", "new_password": "123456789"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


# ─── blank name guard ──────────────────────────────────────────────────────────


async def test_blank_name_rejected(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "   ", "validPw1")
    assert r.status_code == 422


async def test_whitespace_only_name_rejected(unauthed_client: AsyncClient):
    r = await _register(unauthed_client, "\t\n ", "validPw1")
    assert r.status_code == 422


async def test_rename_to_blank_rejected(unauthed_client: AsyncClient):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    r = await unauthed_client.patch(
        f"/api/profiles/{pid}/name",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


# ─── PASSWORD_MIN_LENGTH=12 ────────────────────────────────────────────────────


async def test_custom_min_length_enforced(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 12)
    r = await _register(unauthed_client, "Alice", "short1A")  # 7 chars — under 12
    assert r.status_code == 422


async def test_custom_min_length_met_accepted(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 12)
    r = await _register(unauthed_client, "Alice", "longEnough12")  # 12 chars
    assert r.status_code == 201


async def test_custom_min_length_enforced_on_password_change(unauthed_client: AsyncClient, monkeypatch):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    monkeypatch.setattr(config_module.settings, "password_min_length", 12)
    r = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "validPw1", "new_password": "short1A"},  # 7 chars — under 12
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


async def test_custom_min_length_password_change_met_accepted(unauthed_client: AsyncClient, monkeypatch):
    pid, token = await _register_and_token(unauthed_client, "Alice", "validPw1")
    monkeypatch.setattr(config_module.settings, "password_min_length", 12)
    r = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "validPw1", "new_password": "longEnough12"},  # 12 chars
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204


async def test_config_endpoint_reflects_custom_min_length(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 12)
    r = await unauthed_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["password_min_length"] == 12


# ─── PASSWORD_MIN_LENGTH=0 (no requirement) ────────────────────────────────────


async def test_zero_min_length_allows_any_password(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 0)
    r = await _register(unauthed_client, "Alice", "x")  # 1 char, no digit/letter requirement
    assert r.status_code == 201


async def test_zero_min_length_allows_empty_password(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 0)
    r = await _register(unauthed_client, "Alice", "")
    assert r.status_code == 201


async def test_zero_min_length_change_password_unrestricted(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 0)
    r = await _register(unauthed_client, "Alice", "any")
    assert r.status_code == 201
    pid = r.json()["id"]
    lr = await _login(unauthed_client, pid, "any")
    assert lr.status_code == 200
    token = lr.json()["token"]

    r2 = await unauthed_client.post(
        f"/api/profiles/{pid}/change-password",
        json={"current_password": "any", "new_password": "1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 204


async def test_config_endpoint_reflects_zero_min_length(unauthed_client: AsyncClient, monkeypatch):
    monkeypatch.setattr(config_module.settings, "password_min_length", 0)
    r = await unauthed_client.get("/api/config")
    assert r.json()["password_min_length"] == 0
