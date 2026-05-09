import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("simplechat.events")

_audit_logger: logging.Logger | None = None


def setup_audit_log(data_dir: str) -> None:
    global _audit_logger
    _audit_logger = logging.getLogger("simplechat.audit")
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False
    path = os.path.join(data_dir, "audit.log")
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(handler)


def log_event(profile: str | None, action: str, **fields):
    who = profile or "-"
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("event %s %s%s", who, action, f" {detail}" if detail else "")


def audit_message(profile: str, chat_id: int, content: str, provider: str | None = None, model: str | None = None) -> None:
    if _audit_logger is None:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": profile,
        "chat_id": chat_id,
        "provider": provider,
        "model": model,
        "message": content,
    }
    _audit_logger.info(json.dumps(entry, ensure_ascii=False))
