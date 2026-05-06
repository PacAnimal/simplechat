import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Auth enforcement — every file/message endpoint must reject unauthenticated
# requests with 401, not a redirect, not 403, not 404.
# ---------------------------------------------------------------------------


async def test_upload_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/chats/1/files",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 401


async def test_list_files_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/chats/1/files")
    assert r.status_code == 401


async def test_download_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/files/1/download")
    assert r.status_code == 401


async def test_send_message_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/chats/1/messages",
        json={"content": "hi", "attachment_ids": []},
    )
    assert r.status_code == 401


async def test_list_chats_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/chats")
    assert r.status_code == 401


async def test_create_chat_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/chats", json={"provider": "openai", "model": "gpt-4o"}
    )
    assert r.status_code == 401


async def test_list_messages_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/chats/1/messages")
    assert r.status_code == 401


async def test_delete_chat_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.delete("/api/chats/1")
    assert r.status_code == 401


async def test_bogus_token_rejected_on_upload(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/chats/1/files",
        files={"file": ("x.txt", b"hello", "text/plain")},
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 401


async def _create_chat(client: AsyncClient) -> int:
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    return r.json()["id"]


async def test_upload_text_file_accepted(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("hello.txt", b"Hello world", "text/plain")},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["filename"] == "hello.txt"
    assert data["mime_type"] == "text/plain"


async def test_upload_json_file_accepted(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("data.json", b'{"key":"value"}', "application/json")},
    )
    assert r.status_code == 200


async def test_upload_csv_file_accepted(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("data.csv", b"a,b,c\n1,2,3", "text/csv")},
    )
    assert r.status_code == 200


async def test_upload_image_accepted(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["mime_type"] == "image/png"


async def test_upload_pdf_accepted(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("doc.pdf", b"%PDF-1.4 binary content", "application/pdf")},
    )
    assert r.status_code == 200
    assert r.json()["mime_type"] == "application/pdf"


async def test_upload_binary_disguised_as_text_rejected(client: AsyncClient):
    chat_id = await _create_chat(client)
    # null bytes — not valid UTF-8
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("bad.txt", b"\x00\x01\x02binary\xff\xfe", "text/plain")},
    )
    assert r.status_code == 415


async def test_upload_invalid_json_rejected(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("bad.json", b"not json at all {{", "application/json")},
    )
    assert r.status_code == 415


async def test_upload_missing_chat(client: AsyncClient):
    r = await client.post(
        "/api/chats/99999/files",
        files={"file": ("test.txt", b"content", "text/plain")},
    )
    assert r.status_code == 404


async def test_delete_chat_removes_uploaded_file(client: AsyncClient):
    """Uploaded files must be deleted from disk when their chat is deleted."""
    import os

    chat_id = await _create_chat(client)

    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("hello.txt", b"Hello world", "text/plain")},
    )
    assert r.status_code == 200

    # retrieve current file list to find the on-disk path via the list endpoint
    files_r = await client.get(f"/api/chats/{chat_id}/files")
    assert len(files_r.json()) == 1

    # capture the uploads dir before deletion
    from backend.config import settings

    before = set(os.listdir(settings.uploads_dir))

    del_r = await client.delete(f"/api/chats/{chat_id}")
    assert del_r.status_code == 204

    # at least one file should have disappeared from disk
    after = set(os.listdir(settings.uploads_dir))
    assert len(after) < len(before), (
        "uploaded file was not removed from disk on chat delete"
    )


async def test_upload_file_timestamps_include_timezone(client: AsyncClient):
    chat_id = await _create_chat(client)
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": ("hello.txt", b"Hello world", "text/plain")},
    )
    assert r.status_code == 200
    ts = r.json()["created_at"]
    assert "+00:00" in ts or ts.endswith("Z")
