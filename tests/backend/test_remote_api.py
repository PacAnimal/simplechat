"""Remote-control API: the contained surface a trusted server uses to act for its users."""

import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from backend.config import settings

pytestmark = pytest.mark.asyncio

SECRET = "s3cret-shared-value"
HEADER = "X-Remote-Control-Secret"
AUTH = {HEADER: SECRET}


@pytest.fixture
def remote_enabled():
    settings.remote_control_shared_secret = SECRET
    yield
    settings.remote_control_shared_secret = ""


async def _register(c: AsyncClient, name: str) -> int:
    r = await c.post(
        "/api/profiles", json={"name": name, "password": "testPass1", "avatar": 0}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _chat(c: AsyncClient, profile_id: int) -> int:
    r = await c.post(
        f"/api/remote/profiles/{profile_id}/chats",
        json={"provider": "openai", "model": "gpt-4o", "web_search_enabled": False},
        headers=AUTH,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _collect_sse(response) -> list[dict]:
    return [
        json.loads(line[6:])
        async for line in response.aiter_lines()
        if line.startswith("data: ")
    ]


# ─── the gate ──────────────────────────────────────────────────────────────────


async def test_disabled_by_default(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/remote/profiles", headers=AUTH)
    assert r.status_code == 503


async def test_missing_secret_rejected(unauthed_client: AsyncClient, remote_enabled):
    r = await unauthed_client.get("/api/remote/profiles")
    assert r.status_code == 401


async def test_wrong_secret_rejected(unauthed_client: AsyncClient, remote_enabled):
    r = await unauthed_client.get("/api/remote/profiles", headers={HEADER: "nope"})
    assert r.status_code == 401


async def test_gate_covers_the_whole_namespace(
    unauthed_client: AsyncClient, remote_enabled
):
    """Every route past /profiles carries the same gate — none of them is reachable unsecreted."""
    pid = await _register(unauthed_client, "someone")
    chat_id = await _chat(unauthed_client, pid)
    paths = [
        f"/api/remote/profiles/{pid}/models",
        f"/api/remote/profiles/{pid}/chats",
        f"/api/remote/profiles/{pid}/chats/{chat_id}",
        f"/api/remote/profiles/{pid}/chats/{chat_id}/messages",
        f"/api/remote/profiles/{pid}/generated/x.png",
    ]
    for path in paths:
        assert (await unauthed_client.get(path)).status_code == 401, path


async def test_unknown_profile_is_404(unauthed_client: AsyncClient, remote_enabled):
    r = await unauthed_client.get("/api/remote/profiles/9999/chats", headers=AUTH)
    assert r.status_code == 404


# ─── listing users ─────────────────────────────────────────────────────────────


async def test_lists_users_by_name(unauthed_client: AsyncClient, remote_enabled):
    await _register(unauthed_client, "Zoe")
    await _register(unauthed_client, "adam")

    r = await unauthed_client.get("/api/remote/profiles", headers=AUTH)
    assert r.status_code == 200, r.text
    assert [p["name"] for p in r.json()] == ["adam", "Zoe"]
    assert "password_hash" not in r.json()[0]


# ─── acting as a user ──────────────────────────────────────────────────────────


async def test_chats_are_scoped_to_the_named_user(
    unauthed_client: AsyncClient, remote_enabled
):
    mine = await _register(unauthed_client, "mine")
    theirs = await _register(unauthed_client, "theirs")
    await _chat(unauthed_client, mine)

    listed = await unauthed_client.get(
        f"/api/remote/profiles/{mine}/chats", headers=AUTH
    )
    assert len(listed.json()) == 1
    others = await unauthed_client.get(
        f"/api/remote/profiles/{theirs}/chats", headers=AUTH
    )
    assert others.json() == []


async def test_cannot_reach_another_users_chat(
    unauthed_client: AsyncClient, remote_enabled
):
    """Naming a user in the path is not a way into someone else's conversation."""
    mine = await _register(unauthed_client, "mine")
    theirs = await _register(unauthed_client, "theirs")
    chat_id = await _chat(unauthed_client, mine)

    r = await unauthed_client.get(
        f"/api/remote/profiles/{theirs}/chats/{chat_id}", headers=AUTH
    )
    assert r.status_code == 404


async def test_rename_and_delete_a_chat(unauthed_client: AsyncClient, remote_enabled):
    pid = await _register(unauthed_client, "someone")
    chat_id = await _chat(unauthed_client, pid)

    renamed = await unauthed_client.patch(
        f"/api/remote/profiles/{pid}/chats/{chat_id}",
        json={"title": "Groceries"},
        headers=AUTH,
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["title"] == "Groceries"

    gone = await unauthed_client.request(
        "DELETE", f"/api/remote/profiles/{pid}/chats/{chat_id}", headers=AUTH
    )
    assert gone.status_code == 204
    assert (
        await unauthed_client.get(f"/api/remote/profiles/{pid}/chats", headers=AUTH)
    ).json() == []


async def test_models_are_listed_for_the_user(
    unauthed_client: AsyncClient, remote_enabled
):
    pid = await _register(unauthed_client, "someone")
    r = await unauthed_client.get(f"/api/remote/profiles/{pid}/models", headers=AUTH)
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), dict)


async def test_send_streams_the_reply_and_persists_it(
    unauthed_client: AsyncClient, remote_enabled
):
    pid = await _register(unauthed_client, "someone")
    chat_id = await _chat(unauthed_client, pid)

    async def mock_stream(self, messages, model):
        yield {"type": "text_delta", "content": "Hello "}
        yield {"type": "text_delta", "content": "world!"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with unauthed_client.stream(
            "POST",
            f"/api/remote/profiles/{pid}/chats/{chat_id}/messages",
            json={"content": "Say hello"},
            headers=AUTH,
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            events = await _collect_sse(response)

    assert "".join(e["content"] for e in events if e["type"] == "text_delta") == "Hello world!"
    assert sum(1 for e in events if e["type"] == "done") == 1

    history = await unauthed_client.get(
        f"/api/remote/profiles/{pid}/chats/{chat_id}/messages", headers=AUTH
    )
    assert [(m["role"], m["content"]) for m in history.json()] == [
        ("user", "Say hello"),
        ("assistant", "Hello world!"),
    ]


async def test_generated_image_of_another_user_is_404(
    unauthed_client: AsyncClient, remote_enabled
):
    theirs = await _register(unauthed_client, "theirs")
    r = await unauthed_client.get(
        f"/api/remote/profiles/{theirs}/generated/nope.png", headers=AUTH
    )
    assert r.status_code == 404
