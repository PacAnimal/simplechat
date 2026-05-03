"""Tests for _LocalProxyMiddleware and the is_local IP check."""

import pytest
from httpx import ASGITransport, AsyncClient

# ---- is_local unit tests ----

def test_loopback_ipv4():
    from backend.net import is_local
    assert is_local("127.0.0.1")


def test_loopback_ipv6():
    from backend.net import is_local
    assert is_local("::1")


def test_rfc1918_10():
    from backend.net import is_local
    assert is_local("10.0.0.1")
    assert is_local("10.255.255.255")


def test_rfc1918_172():
    from backend.net import is_local
    assert is_local("172.16.0.1")
    assert is_local("172.31.255.255")


def test_rfc1918_192():
    from backend.net import is_local
    assert is_local("192.168.1.100")


def test_ipv6_unique_local():
    from backend.net import is_local
    assert is_local("fd00::1")
    assert is_local("fc00::1")


def test_ipv6_link_local():
    from backend.net import is_local
    assert is_local("fe80::1")


def test_public_ipv4_rejected():
    from backend.net import is_local
    assert not is_local("8.8.8.8")
    assert not is_local("93.184.216.34")


def test_public_ipv6_rejected():
    from backend.net import is_local
    assert not is_local("2001:4860:4860::8888")


def test_invalid_ip_rejected():
    from backend.net import is_local
    assert not is_local("not-an-ip")
    assert not is_local("")


# ---- proxy middleware: header rewriting ----

def _mini_app():
    """Tiny FastAPI app that echoes back the resolved client IP and scheme."""
    from fastapi import FastAPI, Request
    mini = FastAPI()

    @mini.get("/ip")
    async def get_ip(request: Request):
        return {"ip": request.client.host, "scheme": request.scope.get("scheme")}

    return mini


@pytest.mark.asyncio
async def test_proxy_rewrites_ip_from_local_upstream():
    """X-Forwarded-For is trusted when the direct connection is local."""
    from backend.main import _LocalProxyMiddleware
    app = _mini_app()
    app.add_middleware(_LocalProxyMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # httpx test transport connects as 127.0.0.1 — a local IP, so header is trusted
        r = await c.get("/ip", headers={"X-Forwarded-For": "203.0.113.42"})
    assert r.json()["ip"] == "203.0.113.42"


@pytest.mark.asyncio
async def test_proxy_rewrites_scheme():
    """X-Forwarded-Proto is trusted when the direct connection is local."""
    from backend.main import _LocalProxyMiddleware
    app = _mini_app()
    app.add_middleware(_LocalProxyMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/ip", headers={"X-Forwarded-Proto": "https"})
    assert r.json()["scheme"] == "https"


@pytest.mark.asyncio
async def test_proxy_ignores_headers_when_disabled():
    """Without the middleware, forwarded headers are ignored."""
    app = _mini_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/ip", headers={"X-Forwarded-For": "203.0.113.42"})
    assert r.json()["ip"] != "203.0.113.42"


@pytest.mark.asyncio
async def test_proxy_does_not_trust_headers_from_public_upstream():
    """X-Forwarded-For is ignored when the direct connection is a public IP."""
    from backend.main import _LocalProxyMiddleware

    seen: dict = {}

    async def capture_scope(scope, receive, send):
        seen["client"] = (scope.get("client") or ("", 0))[0]
        from starlette.responses import JSONResponse
        await JSONResponse({"ip": seen["client"]})(scope, receive, send)

    middleware = _LocalProxyMiddleware(capture_scope)

    # build a scope that looks like it arrives from a public IP
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/ip",
        "query_string": b"",
        "headers": [(b"x-forwarded-for", b"203.0.113.42")],
        "client": ("8.8.8.8", 12345),
    }

    async def receive():
        return {"type": "http.request", "body": b""}

    sent = []

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    # public upstream — header must not have been applied
    assert seen["client"] == "8.8.8.8"
