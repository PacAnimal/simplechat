"""Verify HTTP and event logs are emitted by a real uvicorn process."""

import os
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port: int, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"uvicorn did not start on port {port} within {timeout}s")


@pytest.fixture
def uvicorn_proc():
    port = _free_port()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db.name}",
        "OPENAI_API_KEY": "sk-test",
        "ANTHROPIC_API_KEY": "sk-test",
        "STUB_PROVIDERS": "true",
        "CREATE": "any",
        "UPLOADS_DIR": tempfile.mkdtemp(),
        "GENERATED_DIR": tempfile.mkdtemp(),
        "PYTHONUNBUFFERED": "1",
    }

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    try:
        _wait_ready(port)
        yield f"http://127.0.0.1:{port}", proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        os.unlink(db.name)


def test_http_and_event_logs_emitted(uvicorn_proc):
    base_url, proc = uvicorn_proc

    # create profile → should emit event log
    r = httpx.post(
        f"{base_url}/api/profiles",
        json={"name": "Alice", "password": "passWord1", "avatar": 0},
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]

    # login → should emit event log
    r = httpx.post(
        f"{base_url}/api/profiles/{profile_id}/login", json={"password": "passWord1"}
    )
    assert r.status_code == 200, r.text

    proc.terminate()
    stdout, stderr = proc.communicate(timeout=10)
    output = (stdout + stderr).decode(errors="replace")

    assert "req:" in output, f"no HTTP log lines in output:\n{output}"
    assert "event Alice create_profile" in output, (
        f"'event Alice create_profile' not in output:\n{output}"
    )
    assert "event Alice login" in output, (
        f"'event Alice login' not in output:\n{output}"
    )


def test_log_format(uvicorn_proc):
    base_url, proc = uvicorn_proc

    httpx.get(f"{base_url}/api/chats")

    proc.terminate()
    stdout, stderr = proc.communicate(timeout=10)
    output = (stdout + stderr).decode(errors="replace")
    lines = output.splitlines()

    abbrevs = ("dbug: ", "info: ", "warn: ", "fail: ", "crit: ")

    # no line should contain uvicorn-style padded levels like "INFO:     "
    for line in lines:
        assert ":  " not in line, f"padded level format found: {line!r}"

    # no uppercase INFO anywhere — all levels must be abbreviated
    for line in lines:
        assert "INFO" not in line, f"uppercase INFO found: {line!r}"

    # uvicorn startup messages must use our format (not "INFO:     ")
    for line in lines:
        if "startup complete" in line.lower() or "uvicorn running on" in line.lower():
            assert line.startswith(abbrevs), (
                f"startup message not reformatted: {line!r}"
            )

    # HTTP request lines must use our format — no "INFO:     req:"
    for line in lines:
        if "req:" in line and line.startswith("INFO"):
            assert False, f"HTTP log line not reformatted: {line!r}"
        if "req:" in line:
            assert line.startswith(abbrevs), f"unexpected HTTP log format: {line!r}"

    # alembic migration lines must use our format
    for line in lines:
        if "alembic" in line.lower() or "migration" in line.lower():
            assert line.startswith(abbrevs), f"alembic line not reformatted: {line!r}"

    # uvicorn access log must be suppressed — no raw IP access lines
    for line in lines:
        assert '" 200' not in line and '" 404' not in line, (
            f"uvicorn access log line leaked through: {line!r}"
        )

    # each request produces exactly 2 lines (start + finish), no duplicates
    req_lines = [line for line in lines if "req:0 " in line]
    assert len(req_lines) == 2, (
        f"expected 2 lines for req:0, got {len(req_lines)}:\n{output}"
    )


def test_startup_logs_available_models(uvicorn_proc):
    """On startup, one log line per configured provider lists model IDs alphabetically."""
    _base_url, proc = uvicorn_proc
    proc.terminate()
    stdout, stderr = proc.communicate(timeout=10)
    output = (stdout + stderr).decode(errors="replace")

    # uvicorn_proc sets both OPENAI_API_KEY and ANTHROPIC_API_KEY,
    # so both providers are configured and must each produce one log line
    lines = output.splitlines()
    openai_lines = [line for line in lines if "OpenAI models:" in line]
    anthropic_lines = [line for line in lines if "Anthropic models:" in line]

    assert len(openai_lines) == 1, f"expected 1 OpenAI log line, got:\n{output}"
    assert len(anthropic_lines) == 1, f"expected 1 Anthropic log line, got:\n{output}"


def test_startup_logs_unconfigured_provider():
    """Unconfigured provider produces no log line; configured provider still logs."""
    port = _free_port()
    db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db.close()

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db.name}",
        "ANTHROPIC_API_KEY": "sk-test",
        "STUB_PROVIDERS": "true",
        "CREATE": "any",
        "UPLOADS_DIR": tempfile.mkdtemp(),
        "GENERATED_DIR": tempfile.mkdtemp(),
        "PYTHONUNBUFFERED": "1",
    }
    env["OPENAI_API_KEY"] = ""  # empty shadows .env file; falsy → unconfigured

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    try:
        _wait_ready(port)
    finally:
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=10)
        os.unlink(db.name)

    output = (stdout + stderr).decode(errors="replace")
    lines = output.splitlines()
    assert not any("OpenAI models:" in line for line in lines), (
        f"unconfigured OpenAI should not produce a log line:\n{output}"
    )
    assert any("Anthropic models:" in line for line in lines), (
        f"expected Anthropic model line in output:\n{output}"
    )
