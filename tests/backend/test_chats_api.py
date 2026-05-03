import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_chats_empty(client: AsyncClient):
    r = await client.get("/api/chats")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_chat_openai(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"
    assert data["title"] == "New Chat"
    assert data["web_search_enabled"] is False
    assert "id" in data


async def test_create_chat_anthropic(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"})
    assert r.status_code == 200
    data = r.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-sonnet-4-6"


async def test_create_chat_default_model(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai"})
    assert r.status_code == 200
    assert r.json()["model"] == "gpt-4o"


async def test_create_chat_invalid_provider(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "gemini"})
    assert r.status_code == 422


async def test_list_chats_returns_created(client: AsyncClient):
    await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    await client.post("/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"})
    r = await client.get("/api/chats")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_get_chat(client: AsyncClient):
    create = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    chat_id = create.json()["id"]
    r = await client.get(f"/api/chats/{chat_id}")
    assert r.status_code == 200
    assert r.json()["id"] == chat_id


async def test_get_chat_not_found(client: AsyncClient):
    r = await client.get("/api/chats/99999")
    assert r.status_code == 404


async def test_update_chat_title(client: AsyncClient):
    create = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"title": "My awesome chat"})
    assert r.status_code == 200
    assert r.json()["title"] == "My awesome chat"


async def test_update_web_search(client: AsyncClient):
    create = await client.post("/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"})
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"web_search_enabled": True})
    assert r.status_code == 200
    assert r.json()["web_search_enabled"] is True


async def test_delete_chat(client: AsyncClient):
    create = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    chat_id = create.json()["id"]
    r = await client.delete(f"/api/chats/{chat_id}")
    assert r.status_code == 204
    r2 = await client.get(f"/api/chats/{chat_id}")
    assert r2.status_code == 404


async def test_list_messages_empty(client: AsyncClient):
    create = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    chat_id = create.json()["id"]
    r = await client.get(f"/api/chats/{chat_id}/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_messages_for_missing_chat(client: AsyncClient):
    r = await client.get("/api/chats/99999/messages")
    assert r.status_code == 404
