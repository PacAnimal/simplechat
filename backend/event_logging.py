import logging

logger = logging.getLogger("simplechat.events")


def log_event(profile: str | None, action: str, **fields):
    who = profile or "-"
    detail = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("event %s %s%s", who, action, f" {detail}" if detail else "")
