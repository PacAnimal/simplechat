import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_list_chats_empty(client: AsyncClient):
    r = await client.get("/api/chats")
    assert r.status_code == 200
    assert r.json() == []


async def test_create_chat_openai(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201
    data = r.json()
    assert data["provider"] == "openai"
    assert data["model"] == "gpt-4o"
    assert data["title"] == "New Chat"
    assert data["web_search_enabled"] is False
    assert "id" in data


async def test_create_chat_anthropic(client: AsyncClient):
    r = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
    assert r.status_code == 201
    data = r.json()
    assert data["provider"] == "anthropic"
    assert data["model"] == "claude-sonnet-4-6"


async def test_create_chat_default_model(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai"})
    assert r.status_code == 201
    assert r.json()["model"] == "gpt-4o"


async def test_create_chat_invalid_provider(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "gemini"})
    assert r.status_code == 422


async def test_list_chats_returns_created(client: AsyncClient):
    await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
    r = await client.get("/api/chats")
    assert r.status_code == 200
    assert len(r.json()) == 2


async def test_get_chat(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.get(f"/api/chats/{chat_id}")
    assert r.status_code == 200
    assert r.json()["id"] == chat_id


async def test_get_chat_not_found(client: AsyncClient):
    r = await client.get("/api/chats/99999")
    assert r.status_code == 404


async def test_update_chat_title(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"title": "My awesome chat"})
    assert r.status_code == 200
    assert r.json()["title"] == "My awesome chat"


async def test_update_web_search(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"web_search_enabled": True})
    assert r.status_code == 200
    assert r.json()["web_search_enabled"] is True


async def test_delete_chat(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.delete(f"/api/chats/{chat_id}")
    assert r.status_code == 204
    r2 = await client.get(f"/api/chats/{chat_id}")
    assert r2.status_code == 404


async def test_list_messages_empty(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.get(f"/api/chats/{chat_id}/messages")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_messages_for_missing_chat(client: AsyncClient):
    r = await client.get("/api/chats/99999/messages")
    assert r.status_code == 404


async def test_list_chats_pagination_limit(client: AsyncClient):
    for _ in range(5):
        await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    r = await client.get("/api/chats?limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3


async def test_list_chats_pagination_offset(client: AsyncClient):
    for _ in range(5):
        await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    r_all = await client.get("/api/chats")
    all_ids = [c["id"] for c in r_all.json()]

    r = await client.get("/api/chats?limit=2&offset=2")
    assert r.status_code == 200
    page_ids = [c["id"] for c in r.json()]
    assert page_ids == all_ids[2:4]


async def test_list_chats_no_params_returns_all(client: AsyncClient):
    for _ in range(3):
        await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    r = await client.get("/api/chats")
    assert r.status_code == 200
    assert len(r.json()) == 3


async def test_list_chats_invalid_limit(client: AsyncClient):
    r = await client.get("/api/chats?limit=0")
    assert r.status_code == 422


async def test_update_chat_model_requires_provider(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"model": "claude-sonnet-4-6"})
    assert r.status_code == 422


async def test_update_chat_model_with_provider(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.patch(
        f"/api/chats/{chat_id}",
        json={"model": "claude-sonnet-4-6", "provider": "anthropic"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["model"] == "claude-sonnet-4-6"
    assert data["provider"] == "anthropic"


async def test_update_chat_title_too_long(client: AsyncClient):
    create = await client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    chat_id = create.json()["id"]
    r = await client.patch(f"/api/chats/{chat_id}", json={"title": "x" * 256})
    assert r.status_code == 422


async def test_timestamps_include_timezone(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201
    data = r.json()
    # must include UTC offset so JS new Date() interprets correctly
    assert "+00:00" in data["created_at"] or data["created_at"].endswith("Z")
    assert "+00:00" in data["updated_at"] or data["updated_at"].endswith("Z")


async def test_create_chat_with_explicit_title(client: AsyncClient):
    r = await client.post(
        "/api/chats",
        json={"provider": "openai", "model": "gpt-4o", "title": "My Project"},
    )
    assert r.status_code == 201
    assert r.json()["title"] == "My Project"


async def test_create_chat_without_title_defaults_to_new_chat(client: AsyncClient):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201
    assert r.json()["title"] == "New Chat"
