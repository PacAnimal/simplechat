import logging
import time
from itertools import count

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("simplechat.http")
_req_counter = count()


def _hdr(headers: dict[bytes, bytes], name: bytes) -> str:
    return headers.get(name, b"").decode("latin-1")


def _parse_content_type(ct: str) -> tuple[str, str]:
    """Return (media_type, charset) or ("-", "-") if absent."""
    if not ct:
        return "-", "-"
    parts = ct.split(";")
    media = parts[0].strip()
    enc = next((p.split("=")[1].strip() for p in parts[1:] if "charset" in p), "-")
    return media, enc


class HttpLoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        req_id = next(_req_counter)
        client = scope.get("client") or ("", 0)
        ip = client[0] or "-"
        method = scope.get("method", "WS")
        path = scope.get("path", "/")
        query = scope.get("query_string", b"").decode()
        uri = f"{path}?{query}" if query else path

        req_headers = {k.lower(): v for k, v in scope.get("headers", [])}
        req_size = _hdr(req_headers, b"content-length") or "-"
        req_type, req_enc = _parse_content_type(_hdr(req_headers, b"content-type"))
        user_agent = _hdr(req_headers, b"user-agent") or "-"

        logger.info(
            "req:%d %s %s %s - %s %s %s - %s",
            req_id,
            ip,
            method,
            uri,
            req_size,
            req_type,
            req_enc,
            user_agent,
        )

        status_code = 500
        resp_size = "-"
        resp_type = "-"
        resp_enc = "-"
        start = time.perf_counter()

        async def _send(message):
            nonlocal status_code, resp_size, resp_type, resp_enc
            if message["type"] == "http.response.start":
                status_code = message["status"]
                resp_headers = {k.lower(): v for k, v in message.get("headers", [])}
                resp_size = _hdr(resp_headers, b"content-length") or "-"
                resp_type, resp_enc = _parse_content_type(
                    _hdr(resp_headers, b"content-type")
                )
            await send(message)

        try:
            await self.app(scope, receive, _send)
            elapsed = int((time.perf_counter() - start) * 1000)
            log = (
                logger.error
                if status_code >= 500
                else logger.warning
                if status_code >= 400
                else logger.info
            )
            log(
                "req:%d %s %s %s %d %s %s %s %dms",
                req_id,
                ip,
                method,
                uri,
                status_code,
                resp_size,
                resp_type,
                resp_enc,
                elapsed,
            )
        except Exception as exc:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.error(
                "req:%d %s %s %s exception after %dms",
                req_id,
                ip,
                method,
                uri,
                elapsed,
                exc_info=exc,
            )
            raise
