"""Tests for the /api/datasets endpoints."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


async def test_list_datasets_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/datasets")
    assert r.status_code == 401


async def test_create_dataset_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/datasets", json={"name": "test"})
    assert r.status_code == 401


async def test_delete_dataset_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.delete("/api/datasets/1")
    assert r.status_code == 401


async def test_upload_file_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post(
        "/api/datasets/1/files",
        files={"file": ("x.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 401


async def test_delete_file_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.delete("/api/datasets/1/files/1")
    assert r.status_code == 401


async def test_reindex_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.post("/api/datasets/1/reindex")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# CRUD — helpers
# ---------------------------------------------------------------------------


async def _create_dataset(client: AsyncClient, name: str = "My DS") -> dict:
    r = await client.post("/api/datasets", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Create + list + get
# ---------------------------------------------------------------------------


async def test_create_dataset(client: AsyncClient):
    ds = await _create_dataset(client, "Alpha")
    assert ds["name"] == "Alpha"
    assert ds["files"] == []
    assert "id" in ds


async def test_list_datasets(client: AsyncClient):
    await _create_dataset(client, "A")
    await _create_dataset(client, "B")
    r = await client.get("/api/datasets")
    assert r.status_code == 200
    names = [d["name"] for d in r.json()]
    assert "A" in names
    assert "B" in names


async def test_get_dataset(client: AsyncClient):
    ds = await _create_dataset(client, "Gamma")
    r = await client.get(f"/api/datasets/{ds['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "Gamma"


async def test_get_dataset_not_found(client: AsyncClient):
    r = await client.get("/api/datasets/9999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_dataset(client: AsyncClient):
    with patch("backend.api.datasets.delete_collection"):
        ds = await _create_dataset(client)
        r = await client.delete(f"/api/datasets/{ds['id']}")
        assert r.status_code == 204
        r2 = await client.get(f"/api/datasets/{ds['id']}")
        assert r2.status_code == 404


async def test_delete_dataset_not_found(client: AsyncClient):
    with patch("backend.api.datasets.delete_collection"):
        r = await client.delete("/api/datasets/9999")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Profile isolation
# ---------------------------------------------------------------------------


async def test_cannot_access_other_profiles_dataset(unauthed_client: AsyncClient):
    from tests.backend.conftest import BearerAuth, _register_and_login

    _, token_a = await _register_and_login(unauthed_client, "alice", "passWord1")
    _, token_b = await _register_and_login(unauthed_client, "bob", "passWord1")

    unauthed_client.auth = BearerAuth(token_a)
    r = await unauthed_client.post("/api/datasets", json={"name": "Alice's DS"})
    assert r.status_code == 201
    ds_id = r.json()["id"]

    unauthed_client.auth = BearerAuth(token_b)
    r2 = await unauthed_client.get(f"/api/datasets/{ds_id}")
    assert r2.status_code == 404

    r3 = await unauthed_client.delete(f"/api/datasets/{ds_id}")
    assert r3.status_code == 404

    unauthed_client.auth = None


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------


async def test_upload_file_no_ollama(client: AsyncClient):
    """Returns 503 when Ollama is not configured."""
    ds = await _create_dataset(client)
    with patch("backend.api.datasets.settings") as mock_settings:
        mock_settings.ollama_api_url = None
        r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
    assert r.status_code == 503


async def test_upload_file_success(client: AsyncClient):
    from backend.rag.indexer import index_file

    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 3
        ds = await _create_dataset(client)
        r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("notes.txt", b"some notes here", "text/plain")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["filename"] == "notes.txt"
        assert data["size"] == len(b"some notes here")

        mock_thread.assert_called_once()
        fn, *args = mock_thread.call_args[0]
        assert fn is index_file
        assert args[2] == "notes.txt"   # filename
        assert args[3] == b"some notes here"  # content
        assert args[4] == "text/plain"  # mime_type
        assert args[5] == "http://mock-ollama"  # base_url


async def test_upload_file_too_large(client: AsyncClient):
    with patch("backend.api.datasets.settings") as mock_settings:
        mock_settings.ollama_api_url = "http://mock-ollama"
        ds = await _create_dataset(client)
        big = b"x" * (20 * 1024 * 1024 + 1)
        r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("big.txt", big, "text/plain")},
        )
        assert r.status_code == 413


async def test_upload_file_unsupported_type(client: AsyncClient):
    with patch("backend.api.datasets.settings") as mock_settings:
        mock_settings.ollama_api_url = "http://mock-ollama"
        ds = await _create_dataset(client)
        r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("pic.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )
        assert r.status_code == 415


# ---------------------------------------------------------------------------
# File delete + reindex
# ---------------------------------------------------------------------------


async def test_delete_file(client: AsyncClient):
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 0
        ds = await _create_dataset(client)
        upload_r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("doc.txt", b"content", "text/plain")},
        )
        assert upload_r.status_code == 200
        file_id = upload_r.json()["id"]

        del_r = await client.delete(f"/api/datasets/{ds['id']}/files/{file_id}")
        assert del_r.status_code == 204

        # dataset should have no files now
        ds_r = await client.get(f"/api/datasets/{ds['id']}")
        assert ds_r.json()["files"] == []


async def test_reindex_no_ollama(client: AsyncClient):
    ds = await _create_dataset(client)
    with patch("backend.api.datasets.settings") as mock_settings:
        mock_settings.ollama_api_url = None
        r = await client.post(f"/api/datasets/{ds['id']}/reindex")
    assert r.status_code == 503


async def test_reindex_success(client: AsyncClient):
    from backend.rag.indexer import reindex_dataset

    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 0
        ds = await _create_dataset(client)
        r = await client.post(f"/api/datasets/{ds['id']}/reindex")
        assert r.status_code == 204

        mock_thread.assert_called_once()
        fn, *args = mock_thread.call_args[0]
        assert fn is reindex_dataset
        assert args[0] == ds["id"]      # dataset_id
        assert args[2] == "http://mock-ollama"  # base_url


async def test_delete_file_without_ollama_clears_collection(client: AsyncClient):
    """File deletion works even when Ollama is unavailable; collection is cleared."""
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 0
        ds = await _create_dataset(client)
        upload_r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("doc.txt", b"content", "text/plain")},
        )
        file_id = upload_r.json()["id"]

    # now delete the file with Ollama unavailable
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = None
        mock_thread.return_value = None
        del_r = await client.delete(f"/api/datasets/{ds['id']}/files/{file_id}")
        assert del_r.status_code == 204
        # delete_collection should have been called (not reindex_dataset)
        mock_thread.assert_called_once()
        call_args = mock_thread.call_args[0]
        from backend.rag.store import delete_collection
        assert call_args[0] is delete_collection

    ds_r = await client.get(f"/api/datasets/{ds['id']}")
    assert ds_r.json()["files"] == []


# ---------------------------------------------------------------------------
# Dataset ownership enforced via chat endpoints
# ---------------------------------------------------------------------------


async def test_create_chat_rejects_foreign_dataset(unauthed_client: AsyncClient):
    from tests.backend.conftest import BearerAuth, _register_and_login

    _, token_a = await _register_and_login(unauthed_client, "alice2", "passWord1")
    _, token_b = await _register_and_login(unauthed_client, "bob2", "passWord1")

    # alice creates a dataset
    unauthed_client.auth = BearerAuth(token_a)
    r = await unauthed_client.post("/api/datasets", json={"name": "Alice DS"})
    assert r.status_code == 201
    ds_id = r.json()["id"]

    # bob tries to create a chat referencing alice's dataset
    unauthed_client.auth = BearerAuth(token_b)
    r2 = await unauthed_client.post(
        "/api/chats",
        json={"provider": "ollama", "model": "llama3", "dataset_id": ds_id},
    )
    assert r2.status_code == 404

    unauthed_client.auth = None


async def test_update_chat_rejects_foreign_dataset(unauthed_client: AsyncClient):
    from tests.backend.conftest import BearerAuth, _register_and_login

    _, token_a = await _register_and_login(unauthed_client, "alice3", "passWord1")
    _, token_b = await _register_and_login(unauthed_client, "bob3", "passWord1")

    # alice creates a dataset
    unauthed_client.auth = BearerAuth(token_a)
    r = await unauthed_client.post("/api/datasets", json={"name": "Alice DS2"})
    ds_id = r.json()["id"]

    # bob creates a chat, then tries to assign alice's dataset
    unauthed_client.auth = BearerAuth(token_b)
    chat_r = await unauthed_client.post(
        "/api/chats", json={"provider": "ollama", "model": "llama3"}
    )
    chat_id = chat_r.json()["id"]

    patch_r = await unauthed_client.patch(
        f"/api/chats/{chat_id}", json={"dataset_id": ds_id}
    )
    assert patch_r.status_code == 404

    unauthed_client.auth = None


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------


async def test_download_file_requires_auth(unauthed_client: AsyncClient):
    r = await unauthed_client.get("/api/datasets/1/files/1/download")
    assert r.status_code == 401


async def test_download_file_success(client: AsyncClient):
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1
        ds = await _create_dataset(client)
        upload_r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("report.txt", b"hello world", "text/plain")},
        )
        assert upload_r.status_code == 200
        file_id = upload_r.json()["id"]

    dl_r = await client.get(f"/api/datasets/{ds['id']}/files/{file_id}/download")
    assert dl_r.status_code == 200
    assert dl_r.content == b"hello world"
    assert dl_r.headers["content-type"].startswith("text/plain")
    assert "report.txt" in dl_r.headers["content-disposition"]


async def test_download_file_not_found(client: AsyncClient):
    ds = await _create_dataset(client)
    r = await client.get(f"/api/datasets/{ds['id']}/files/9999/download")
    assert r.status_code == 404


async def test_download_file_wrong_dataset(client: AsyncClient):
    """File exists but belongs to a different dataset — must 404."""
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1
        ds_a = await _create_dataset(client, "DSA")
        ds_b = await _create_dataset(client, "DSB")
        upload_r = await client.post(
            f"/api/datasets/{ds_a['id']}/files",
            files={"file": ("x.txt", b"data", "text/plain")},
        )
        file_id = upload_r.json()["id"]

    r = await client.get(f"/api/datasets/{ds_b['id']}/files/{file_id}/download")
    assert r.status_code == 404


async def test_download_file_profile_isolation(unauthed_client: AsyncClient):
    from tests.backend.conftest import BearerAuth, _register_and_login

    _, token_a = await _register_and_login(unauthed_client, "alice4", "passWord1")
    _, token_b = await _register_and_login(unauthed_client, "bob4", "passWord1")

    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1

        unauthed_client.auth = BearerAuth(token_a)
        r = await unauthed_client.post("/api/datasets", json={"name": "Alice DS"})
        ds_id = r.json()["id"]
        upload_r = await unauthed_client.post(
            f"/api/datasets/{ds_id}/files",
            files={"file": ("secret.txt", b"secret", "text/plain")},
        )
        file_id = upload_r.json()["id"]

    unauthed_client.auth = BearerAuth(token_b)
    r2 = await unauthed_client.get(f"/api/datasets/{ds_id}/files/{file_id}/download")
    assert r2.status_code == 404

    unauthed_client.auth = None


# ---------------------------------------------------------------------------
# created_at in file metadata
# ---------------------------------------------------------------------------


async def test_upload_response_includes_created_at(client: AsyncClient):
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1
        ds = await _create_dataset(client)
        r = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("dated.txt", b"data", "text/plain")},
        )
    assert r.status_code == 200
    data = r.json()
    assert "created_at" in data
    assert data["created_at"] is not None


async def test_list_files_include_created_at(client: AsyncClient):
    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1
        ds = await _create_dataset(client)
        await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("dated2.txt", b"data", "text/plain")},
        )

    r = await client.get(f"/api/datasets/{ds['id']}")
    assert r.status_code == 200
    file_meta = r.json()["files"][0]
    assert "created_at" in file_meta
    assert file_meta["created_at"] is not None


# ---------------------------------------------------------------------------
# Delete file triggers reindex with remaining files
# ---------------------------------------------------------------------------


async def test_delete_file_reindexes_remaining_files(client: AsyncClient):
    """After deleting one file, reindex_dataset is called with the remaining files."""
    from backend.rag.indexer import reindex_dataset

    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = 1
        ds = await _create_dataset(client)
        r1 = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("keep.txt", b"keep this", "text/plain")},
        )
        r2 = await client.post(
            f"/api/datasets/{ds['id']}/files",
            files={"file": ("delete_me.txt", b"delete this", "text/plain")},
        )
        file_to_keep = r1.json()["id"]
        file_to_delete = r2.json()["id"]

    with (
        patch("backend.api.datasets.settings") as mock_settings,
        patch("backend.api.datasets.asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
    ):
        mock_settings.ollama_api_url = "http://mock-ollama"
        mock_thread.return_value = None

        del_r = await client.delete(f"/api/datasets/{ds['id']}/files/{file_to_delete}")
        assert del_r.status_code == 204

        # reindex_dataset should have been called
        mock_thread.assert_called_once()
        fn, *args = mock_thread.call_args[0]
        assert fn is reindex_dataset
        remaining_ids = [f.id for f in args[1]]
        assert file_to_keep in remaining_ids
        assert file_to_delete not in remaining_ids
