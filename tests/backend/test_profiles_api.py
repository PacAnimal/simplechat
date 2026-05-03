"""Profile management and cross-profile isolation tests."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ─── helpers ───────────────────────────────────────────────────────────────────

async def _register(c: AsyncClient, name: str, password: str, avatar: int) -> dict:
    r = await c.post("/api/profiles", json={"name": name, "password": password, "avatar": avatar})
    assert r.status_code == 201, r.text
    return r.json()


async def _login(c: AsyncClient, profile_id: int, password: str) -> str:
    r = await c.post(f"/api/profiles/{profile_id}/login", json={"password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def _auth_headers(c: AsyncClient, name: str, password: str) -> dict[str, str]:
    p = await _register(c, name, password, avatar=0)
    token = await _login(c, p["id"], password)
    return {"Authorization": f"Bearer {token}"}


async def _create_chat(c: AsyncClient, headers: dict) -> int:
    r = await c.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ─── profile CRUD ──────────────────────────────────────────────────────────────

async def test_list_profiles_empty(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/profiles")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_profile(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/profiles", json={"name": "Alice", "password": "secret", "avatar": 3})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Alice"
    assert data["avatar"] == 3
    assert "id" in data
    assert "password" not in data
    assert "password_hash" not in data


async def test_list_profiles_shows_created(unauthed_client: AsyncClient):
    await _register(unauthed_client, "Alice", "passA", avatar=0)
    await _register(unauthed_client, "Bob", "passB", avatar=1)
    r = await unauthed_client.get("/api/profiles")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "Alice" in names
    assert "Bob" in names


async def test_duplicate_profile_name_rejected(unauthed_client: AsyncClient):
    await _register(unauthed_client, "Alice", "first", avatar=0)
    r = await unauthed_client.post("/api/profiles", json={"name": "Alice", "password": "second", "avatar": 0})
    assert r.status_code == 409


async def test_duplicate_profile_name_case_sensitive(unauthed_client: AsyncClient):
    """Names are compared as-is; 'alice' and 'Alice' are currently distinct."""
    await _register(unauthed_client, "Alice", "pass1", avatar=0)
    r = await unauthed_client.post("/api/profiles", json={"name": "alice", "password": "pass2", "avatar": 0})
    assert r.status_code == 201


async def test_profile_password_not_exposed_in_list(unauthed_client: AsyncClient):
    await _register(unauthed_client, "Alice", "supersecret", avatar=0)
    profiles = (await unauthed_client.get("/api/profiles")).json()
    alice = next(p for p in profiles if p["name"] == "Alice")
    assert "password" not in alice
    assert "password_hash" not in alice


# ─── login ─────────────────────────────────────────────────────────────────────

async def test_login_correct_password_returns_token(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "correct", avatar=0)
    r = await unauthed_client.post(f"/api/profiles/{p['id']}/login", json={"password": "correct"})
    assert r.status_code == 200
    assert "token" in r.json()
    assert r.json()["profile"]["name"] == "Alice"


async def test_login_wrong_password_rejected(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "correct", avatar=0)
    r = await unauthed_client.post(f"/api/profiles/{p['id']}/login", json={"password": "wrong"})
    assert r.status_code == 401


async def test_login_nonexistent_profile(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/profiles/99999/login", json={"password": "anything"})
    assert r.status_code == 404


# ─── unauthenticated access ────────────────────────────────────────────────────

async def test_chats_require_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/chats")
    assert r.status_code == 401


async def test_create_chat_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 401


async def test_stream_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/chats/1/messages", json={"content": "hi"})
    assert r.status_code == 401


async def test_files_require_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/chats/1/files",
        files={"file": ("test.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 401


async def test_download_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/files/1/download")
    assert r.status_code == 401


async def test_invalid_token_rejected(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/chats", headers={"Authorization": "Bearer notavalidtoken"})
    assert r.status_code == 401


async def test_expired_token_rejected(unauthed_client: AsyncClient):
    from datetime import datetime, timedelta, timezone

    import jwt
    payload = {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(days=1)}
    token = jwt.encode(payload, "simplechat-dev-secret-change-in-production", algorithm="HS256")
    r = await unauthed_client.get("/api/chats", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# ─── authenticated access works ────────────────────────────────────────────────

async def test_authenticated_can_list_chats(unauthed_client: AsyncClient):
    headers = await _auth_headers(unauthed_client, "Alice", "alicepass")
    r = await unauthed_client.get("/api/chats", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


async def test_authenticated_can_create_and_fetch_chat(unauthed_client: AsyncClient):
    headers = await _auth_headers(unauthed_client, "Alice", "alicepass")
    chat_id = await _create_chat(unauthed_client, headers)
    r = await unauthed_client.get(f"/api/chats/{chat_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == chat_id


# ─── cross-profile chat isolation ──────────────────────────────────────────────

async def test_cross_profile_cannot_see_others_chats(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    # Bob's chat list must not include Alice's chat
    r = await unauthed_client.get("/api/chats", headers=bob)
    assert r.status_code == 200
    assert all(c["id"] != alice_chat for c in r.json())


async def test_cross_profile_cannot_get_others_chat(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.get(f"/api/chats/{alice_chat}", headers=bob)
    assert r.status_code == 404


async def test_cross_profile_cannot_update_others_chat(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.patch(
        f"/api/chats/{alice_chat}", json={"title": "Hijacked"}, headers=bob
    )
    assert r.status_code == 404


async def test_cross_profile_cannot_delete_others_chat(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.delete(f"/api/chats/{alice_chat}", headers=bob)
    assert r.status_code == 404

    # Alice's chat must be untouched
    r2 = await unauthed_client.get(f"/api/chats/{alice_chat}", headers=alice)
    assert r2.status_code == 200


async def test_cross_profile_cannot_read_others_messages(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.get(f"/api/chats/{alice_chat}/messages", headers=bob)
    assert r.status_code == 404


async def test_cross_profile_cannot_send_message_to_others_chat(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.post(
        f"/api/chats/{alice_chat}/messages",
        json={"content": "gotcha"},
        headers=bob,
    )
    assert r.status_code == 404


async def test_chat_histories_are_separate(unauthed_client: AsyncClient):
    """Each profile sees exactly its own chats — no bleed-through."""
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    await _create_chat(unauthed_client, alice)
    await _create_chat(unauthed_client, alice)
    await _create_chat(unauthed_client, bob)

    alice_chats = (await unauthed_client.get("/api/chats", headers=alice)).json()
    bob_chats = (await unauthed_client.get("/api/chats", headers=bob)).json()

    assert len(alice_chats) == 2
    assert len(bob_chats) == 1

    alice_ids = {c["id"] for c in alice_chats}
    bob_ids = {c["id"] for c in bob_chats}
    assert alice_ids.isdisjoint(bob_ids)


# ─── cross-profile file isolation ──────────────────────────────────────────────

async def test_cross_profile_cannot_upload_to_others_chat(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)

    r = await unauthed_client.post(
        f"/api/chats/{alice_chat}/files",
        files={"file": ("test.txt", b"bob's file", "text/plain")},
        headers=bob,
    )
    assert r.status_code == 404


async def test_cross_profile_cannot_list_others_files(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)
    await unauthed_client.post(
        f"/api/chats/{alice_chat}/files",
        files={"file": ("secret.txt", b"alice's file", "text/plain")},
        headers=alice,
    )

    r = await unauthed_client.get(f"/api/chats/{alice_chat}/files", headers=bob)
    assert r.status_code == 404


async def test_cross_profile_cannot_download_others_file(unauthed_client: AsyncClient):
    alice = await _auth_headers(unauthed_client, "Alice", "alicepass")
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    alice_chat = await _create_chat(unauthed_client, alice)
    upload = await unauthed_client.post(
        f"/api/chats/{alice_chat}/files",
        files={"file": ("secret.txt", b"alice's secret", "text/plain")},
        headers=alice,
    )
    att_id = upload.json()["id"]

    r = await unauthed_client.get(f"/api/files/{att_id}/download", headers=bob)
    assert r.status_code == 404


# ─── cross-profile settings isolation ─────────────────────────────────────────

async def test_cannot_update_another_profiles_avatar(unauthed_client: AsyncClient):
    alice_profile = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    r = await unauthed_client.patch(
        f"/api/profiles/{alice_profile['id']}/avatar",
        json={"avatar": 5},
        headers=bob,
    )
    assert r.status_code == 403


async def test_cannot_change_another_profiles_password(unauthed_client: AsyncClient):
    alice_profile = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    r = await unauthed_client.post(
        f"/api/profiles/{alice_profile['id']}/change-password",
        json={"current_password": "alicepass", "new_password": "hacked"},
        headers=bob,
    )
    assert r.status_code == 403


async def test_cannot_delete_another_profile(unauthed_client: AsyncClient):
    alice_profile = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    bob = await _auth_headers(unauthed_client, "Bob", "bobpass")

    r = await unauthed_client.delete(f"/api/profiles/{alice_profile['id']}", headers=bob)
    assert r.status_code == 403

    # Alice's profile is unaffected
    names = [p["name"] for p in (await unauthed_client.get("/api/profiles")).json()]
    assert "Alice" in names


# ─── own-profile settings ──────────────────────────────────────────────────────

async def test_can_update_own_avatar(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    token = await _login(unauthed_client, p["id"], "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await unauthed_client.patch(
        f"/api/profiles/{p['id']}/avatar", json={"avatar": 7}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["avatar"] == 7


async def test_can_change_own_password(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "oldpass", avatar=0)
    token = await _login(unauthed_client, p["id"], "oldpass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await unauthed_client.post(
        f"/api/profiles/{p['id']}/change-password",
        json={"current_password": "oldpass", "new_password": "newpass"},
        headers=headers,
    )
    assert r.status_code == 204

    # old password no longer valid
    r2 = await unauthed_client.post(f"/api/profiles/{p['id']}/login", json={"password": "oldpass"})
    assert r2.status_code == 401

    # new password works
    r3 = await unauthed_client.post(f"/api/profiles/{p['id']}/login", json={"password": "newpass"})
    assert r3.status_code == 200


async def test_change_password_wrong_current_rejected(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "correct", avatar=0)
    token = await _login(unauthed_client, p["id"], "correct")
    headers = {"Authorization": f"Bearer {token}"}

    r = await unauthed_client.post(
        f"/api/profiles/{p['id']}/change-password",
        json={"current_password": "wrong", "new_password": "newpass"},
        headers=headers,
    )
    assert r.status_code == 401


async def test_can_delete_own_profile(unauthed_client: AsyncClient):
    p = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    token = await _login(unauthed_client, p["id"], "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    r = await unauthed_client.delete(f"/api/profiles/{p['id']}", headers=headers)
    assert r.status_code == 204

    names = [x["name"] for x in (await unauthed_client.get("/api/profiles")).json()]
    assert "Alice" not in names


async def test_deleting_profile_removes_its_chats(unauthed_client: AsyncClient):
    """Cascade: all of a profile's chats are gone when the profile is deleted."""
    p = await _register(unauthed_client, "Alice", "alicepass", avatar=0)
    token = await _login(unauthed_client, p["id"], "alicepass")
    headers = {"Authorization": f"Bearer {token}"}

    chat_id = await _create_chat(unauthed_client, headers)

    await unauthed_client.delete(f"/api/profiles/{p['id']}", headers=headers)

    # re-register under the same name — should start with zero chats
    p2 = await _register(unauthed_client, "Alice", "alicepass2", avatar=0)
    token2 = await _login(unauthed_client, p2["id"], "alicepass2")
    headers2 = {"Authorization": f"Bearer {token2}"}

    chats = (await unauthed_client.get("/api/chats", headers=headers2)).json()
    assert all(c["id"] != chat_id for c in chats)


# ─── avatar index validation ───────────────────────────────────────────────────

async def test_invalid_avatar_index_rejected(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/profiles", json={"name": "Alice", "password": "alicepass", "avatar": 100}
    )
    assert r.status_code == 422


async def test_negative_avatar_rejected(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/profiles", json={"name": "Alice", "password": "alicepass", "avatar": -1}
    )
    assert r.status_code == 422
