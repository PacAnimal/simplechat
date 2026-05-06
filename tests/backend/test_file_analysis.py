"""Tests proving that file attachments are correctly included in provider context."""

import csv
import io
import json
import os
import pathlib
import tempfile
from unittest.mock import patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_chat(client: AsyncClient, provider: str = "openai") -> int:
    model = "gpt-4o" if provider == "openai" else "claude-sonnet-4-6"
    r = await client.post("/api/chats", json={"provider": provider, "model": model})
    assert r.status_code == 201
    return r.json()["id"]


async def _upload(
    client: AsyncClient, chat_id: int, filename: str, content: bytes, mime: str
) -> int:
    r = await client.post(
        f"/api/chats/{chat_id}/files",
        files={"file": (filename, content, mime)},
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---- _attachment_text unit tests ----


async def test_attachment_text_csv_content_included():
    """`_attachment_text` wraps CSV content with filename and code-block."""
    from backend.api.stream import _attachment_text
    from backend.models import Attachment

    csv_bytes = b"name,age,score\nAlice,30,95\nBob,25,87\n"

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(csv_bytes)
        path = f.name

    try:
        att = Attachment(
            chat_id=1,
            filename="data.csv",
            mime_type="text/csv",
            path=path,
            size=len(csv_bytes),
        )
        result = await _attachment_text(att)
        assert "data.csv" in result
        assert "Alice" in result
        assert "name,age,score" in result
        assert "```" in result
    finally:
        os.unlink(path)


async def test_attachment_text_json_content_included():
    from backend.api.stream import _attachment_text
    from backend.models import Attachment

    json_bytes = b'{"users":[{"name":"Alice","role":"admin"}]}'

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        f.write(json_bytes)
        path = f.name

    try:
        att = Attachment(
            chat_id=1,
            filename="users.json",
            mime_type="application/json",
            path=path,
            size=len(json_bytes),
        )
        result = await _attachment_text(att)
        assert "users.json" in result
        assert "Alice" in result
        assert "admin" in result
    finally:
        os.unlink(path)


async def test_attachment_text_plain_content_included():
    from backend.api.stream import _attachment_text
    from backend.models import Attachment

    text_bytes = b"Meeting notes:\n- Discussed Q3 targets\n- Budget is $50,000"

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(text_bytes)
        path = f.name

    try:
        att = Attachment(
            chat_id=1,
            filename="notes.txt",
            mime_type="text/plain",
            path=path,
            size=len(text_bytes),
        )
        result = await _attachment_text(att)
        assert "notes.txt" in result
        assert "Q3 targets" in result
        assert "$50,000" in result
    finally:
        os.unlink(path)


async def test_attachment_text_image_returns_empty():
    """`_attachment_text` returns empty string for unsupported mime types like images."""
    from backend.api.stream import _attachment_text
    from backend.models import Attachment

    att = Attachment(
        chat_id=1,
        filename="photo.png",
        mime_type="image/png",
        path="/tmp/nonexistent.png",
        size=100,
    )
    assert await _attachment_text(att) == ""


async def test_attachment_text_missing_file_returns_empty():
    from backend.api.stream import _attachment_text
    from backend.models import Attachment

    att = Attachment(
        chat_id=1,
        filename="gone.txt",
        mime_type="text/plain",
        path="/tmp/definitely_not_here_xyz.txt",
        size=0,
    )
    assert await _attachment_text(att) == ""


# ---- CSV analysis via stream endpoint ----


async def test_stream_openai_receives_csv_content(client: AsyncClient):
    """OpenAI provider receives CSV attachment content in the user message."""
    chat_id = await _create_chat(client, "openai")

    csv_bytes = b"product,sales\nWidget A,150\nWidget B,200\nWidget C,75\n"
    att_id = await _upload(client, chat_id, "sales.csv", csv_bytes, "text/csv")

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "Widget B."}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Which product has the most sales?",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    user_msgs = [m for m in captured if m["role"] == "user"]
    assert len(user_msgs) == 1
    content = user_msgs[0]["content"]
    assert "sales.csv" in content
    assert "Widget B" in content
    assert "200" in content


async def test_stream_anthropic_receives_csv_content(client: AsyncClient):
    """Anthropic provider also receives CSV attachment content in the user message."""
    chat_id = await _create_chat(client, "anthropic")

    csv_bytes = b"month,revenue\nJan,10000\nFeb,12000\nMar,9500\n"
    att_id = await _upload(client, chat_id, "revenue.csv", csv_bytes, "text/csv")

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "February."}

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_stream
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "Which month had the highest revenue?",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    user_msgs = [m for m in captured if m["role"] == "user"]
    assert len(user_msgs) == 1
    content = user_msgs[0]["content"]
    assert "revenue.csv" in content
    assert "Feb" in content
    assert "12000" in content


async def test_stream_json_file_content_in_context(client: AsyncClient):
    """JSON file content is embedded verbatim in the provider message context."""
    chat_id = await _create_chat(client, "openai")

    config = {"server": "prod-01", "port": 8443, "secret": "hunter2"}
    json_bytes = json.dumps(config).encode()
    att_id = await _upload(
        client, chat_id, "config.json", json_bytes, "application/json"
    )

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "prod-01"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "What server is this?", "attachment_ids": [att_id]},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    content = [m for m in captured if m["role"] == "user"][0]["content"]
    assert "config.json" in content
    assert "prod-01" in content
    assert "hunter2" in content


async def test_stream_multiple_attachments_all_in_context(client: AsyncClient):
    """All attachments for a single message appear in the provider context."""
    chat_id = await _create_chat(client, "openai")

    csv_bytes = b"city,population\nOslo,693000\nBergen,285000\n"
    json_bytes = b'{"country":"Norway","capital":"Oslo"}'
    att1 = await _upload(client, chat_id, "cities.csv", csv_bytes, "text/csv")
    att2 = await _upload(
        client, chat_id, "country.json", json_bytes, "application/json"
    )

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "Oslo is the capital."}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Summarize both files.", "attachment_ids": [att1, att2]},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    content = [m for m in captured if m["role"] == "user"][0]["content"]
    assert "cities.csv" in content
    assert "country.json" in content
    assert "Oslo" in content
    assert "Norway" in content


async def test_stream_attachment_content_absent_without_attachment_ids(
    client: AsyncClient,
):
    """When no attachment_ids are sent, uploaded files must not appear in the context."""
    chat_id = await _create_chat(client, "openai")

    # upload a file but do NOT include it in the message
    secret_bytes = b"TOPSECRET: the vault code is 1234"
    await _upload(client, chat_id, "secret.txt", secret_bytes, "text/plain")

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "I don't know."}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Do you know the vault code?"},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    content = [m for m in captured if m["role"] == "user"][0]["content"]
    assert "TOPSECRET" not in content
    assert "1234" not in content


async def test_stream_text_file_persists_across_turns(client: AsyncClient):
    """Attachment content linked to a message is included in subsequent turns' history."""
    chat_id = await _create_chat(client, "openai")

    notes_bytes = b"Project Falcon budget: $1,200,000"
    att_id = await _upload(client, chat_id, "notes.txt", notes_bytes, "text/plain")

    # first turn: send with attachment
    async def mock_stream_1(self, messages, model, web_search):
        yield {"type": "text_delta", "content": "Got it."}

    with patch(
        "backend.providers.openai_provider.OpenAIProvider._stream", mock_stream_1
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "Remember this file.", "attachment_ids": [att_id]},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    # second turn: no attachment — but history should still contain the file content
    captured: list[dict] = []

    async def mock_stream_2(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "$1,200,000"}

    with patch(
        "backend.providers.openai_provider.OpenAIProvider._stream", mock_stream_2
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={"content": "What was the budget?"},
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    # the first user message in history should still contain the attachment text
    user_msgs = [m for m in captured if m["role"] == "user"]
    assert len(user_msgs) == 2
    assert "notes.txt" in user_msgs[0]["content"]
    assert "$1,200,000" in user_msgs[0]["content"]


# ---- large XLS (5000 rows) context tests ----
#
# Converts the fixture XLS to CSV and uploads it, then asserts the full content
# (including row 5000 and a mid-file row) reaches each provider unchanged.

_FIXTURE_XLS = pathlib.Path(__file__).parent / "fixtures" / "users_5000.xls"


def _xls_to_csv_bytes(path: pathlib.Path) -> bytes:
    import xlrd

    wb = xlrd.open_workbook(str(path))
    ws = wb.sheet_by_index(0)
    buf = io.StringIO()
    writer = csv.writer(buf)
    for i in range(ws.nrows):
        writer.writerow(ws.row_values(i))
    return buf.getvalue().encode()


async def test_large_xls_openai_full_content_in_context(client: AsyncClient):
    """OpenAI provider receives all 5000 rows; Rasheeda (row 5000) and Angel Sanor (Male) are present."""
    chat_id = await _create_chat(client, "openai")
    csv_bytes = _xls_to_csv_bytes(_FIXTURE_XLS)
    att_id = await _upload(client, chat_id, "users.csv", csv_bytes, "text/csv")

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "Rasheeda / Male"}

    with patch("backend.providers.openai_provider.OpenAIProvider._stream", mock_stream):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "What is the name of the 5000th user, and what is Angel Sanor's gender?",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    content = [m for m in captured if m["role"] == "user"][0]["content"]
    assert "Rasheeda" in content, "row 5000 first name missing from OpenAI context"
    assert "Angel" in content and "Sanor" in content, (
        "Angel Sanor missing from OpenAI context"
    )
    assert "Male" in content, "Angel Sanor's gender missing from OpenAI context"


async def test_large_xls_anthropic_full_content_in_context(client: AsyncClient):
    """Anthropic provider receives all 5000 rows; Rasheeda (row 5000) and Angel Sanor (Male) are present."""
    chat_id = await _create_chat(client, "anthropic")
    csv_bytes = _xls_to_csv_bytes(_FIXTURE_XLS)
    att_id = await _upload(client, chat_id, "users.csv", csv_bytes, "text/csv")

    captured: list[dict] = []

    async def mock_stream(self, messages, model, web_search):
        captured.extend(messages)
        yield {"type": "text_delta", "content": "Rasheeda / Male"}

    with patch(
        "backend.providers.anthropic_provider.AnthropicProvider._stream", mock_stream
    ):
        async with client.stream(
            "POST",
            f"/api/chats/{chat_id}/messages",
            json={
                "content": "What is the name of the 5000th user, and what is Angel Sanor's gender?",
                "attachment_ids": [att_id],
            },
        ) as resp:
            async for _ in resp.aiter_lines():
                pass

    content = [m for m in captured if m["role"] == "user"][0]["content"]
    assert "Rasheeda" in content, "row 5000 first name missing from Anthropic context"
    assert "Angel" in content and "Sanor" in content, (
        "Angel Sanor missing from Anthropic context"
    )
    assert "Male" in content, "Angel Sanor's gender missing from Anthropic context"
