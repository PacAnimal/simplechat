import logging
import sys

_initialized = False


_LEVEL_ABBREV = {
    logging.DEBUG: "dbug",
    logging.INFO: "info",
    logging.WARNING: "warn",
    logging.ERROR: "fail",
    logging.CRITICAL: "crit",
}


class _Formatter(logging.Formatter):
    def format(self, record):
        record = logging.makeLogRecord(record.__dict__)
        record.levelname = _LEVEL_ABBREV.get(record.levelno, "trce")
        return super().format(record)


def reformat_root_handlers() -> None:
    """Reformat any handlers on the root logger to match our style.
    Called after alembic migrations, which installs its own root handler."""
    formatter = _Formatter("%(levelname)s: %(message)s")
    for h in logging.getLogger().handlers:
        h.setFormatter(formatter)


def setup_loggers():
    """Attach uvicorn's handler to the simplechat parent logger.
    Must be called lazily (after uvicorn configures its own loggers)."""
    global _initialized
    if _initialized:
        return
    _initialized = True
    logger = logging.getLogger("simplechat")
    logger.setLevel(logging.DEBUG)
    logger.disabled = False
    logger.propagate = False  # stop messages reaching alembic's root handler
    formatter = _Formatter("%(levelname)s: %(message)s")
    uvicorn_handlers = logging.getLogger("uvicorn").handlers
    stream = uvicorn_handlers[0].stream if uvicorn_handlers else None
    # reformat uvicorn's own handlers so startup messages match our style
    for h in uvicorn_handlers:
        h.setFormatter(formatter)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # uvicorn.access duplicates our middleware output;
    # clear handlers so alembic's fileConfig(disable_existing_loggers=False) can't re-enable it
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    # alembic's fileConfig (disable_existing_loggers=True by default) may have
    # disabled child loggers created at import time — clear that flag on all of them
    for name, obj in logging.Logger.manager.loggerDict.items():
        if name.startswith("simplechat.") and isinstance(obj, logging.Logger):
            obj.disabled = False
