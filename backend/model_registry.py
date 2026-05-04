import asyncio
import logging
import re
import time

import anthropic
from openai import AsyncOpenAI

from .config import settings
from .schemas import PROVIDER_DEFAULTS

logger = logging.getLogger("simplechat.models")

_CHAT_RE = re.compile(r"^(gpt-|o[0-9]|chatgpt-)", re.IGNORECASE)
_EXCLUDE_RE = re.compile(
    r"(embed|whisper|tts-|dall-e|instruct|realtime|transcr|moderat|search|audio|image)",
    re.IGNORECASE,
)

_FALLBACK_OPENAI = [
    {"id": "gpt-4o", "label": "GPT-4o"},
    {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    {"id": "gpt-4-turbo", "label": "GPT-4 Turbo"},
    {"id": "o1-mini", "label": "o1-mini"},
]
_FALLBACK_ANTHROPIC = [
    {"id": "claude-opus-4-7", "label": "Claude Opus 4.7"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
    {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
]
_cache: dict = {}
_cache_time: float = 0.0
_CACHE_TTL = 3600.0
_refresh_lock = asyncio.Lock()


def _apply_allowed(models: list[dict]) -> list[dict]:
    """Filter models by ALLOWED_MODELS if set; empty = allow all."""
    allowed = {m.strip() for m in settings.allowed_models.split(",") if m.strip()}
    if not allowed:
        return models
    return [m for m in models if m["id"] in allowed]


async def _fetch_openai_models() -> tuple[list[dict], set[str]]:
    """Fetch live OpenAI models.

    Returns (chat_models, all_model_ids).  all_model_ids is the full unfiltered
    set, used to validate IMAGE_MODEL; empty set on failure.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        resp = await client.models.list()
        all_ids = {m.id for m in resp.data}
        models_with_ts = [
            ({"id": m.id, "label": m.id}, m.created)
            for m in resp.data
            if _CHAT_RE.match(m.id) and not _EXCLUDE_RE.search(m.id) and ":" not in m.id
        ]
        models_with_ts.sort(key=lambda x: x[1], reverse=True)
        result = [m for m, _ in models_with_ts]
        return (result if result else _FALLBACK_OPENAI, all_ids)
    except Exception:
        return (_FALLBACK_OPENAI, set())


async def _fetch_anthropic_models() -> list[dict]:
    """Fetch live Anthropic models; returns fallback on failure."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        resp = await client.models.list()
        result = [{"id": m.id, "label": getattr(m, "display_name", m.id)} for m in resp.data]
        return result if result else _FALLBACK_ANTHROPIC
    except Exception:
        return _FALLBACK_ANTHROPIC


def log_available_models(raw: dict, filtered: dict) -> None:
    """Log all configured models, then allowed subsets when ALLOWED_MODELS is set."""
    for provider, label in (("anthropic", "Anthropic"), ("openai", "OpenAI")):
        models = raw.get(provider, [])
        if models:
            logger.info("%s models: %s", label, ", ".join(m["id"] for m in models))

    allowed_set = {m.strip() for m in settings.allowed_models.split(",") if m.strip()}
    if allowed_set:
        for provider, label in (("anthropic", "Anthropic"), ("openai", "OpenAI")):
            if not raw.get(provider):
                continue
            models = filtered.get(provider, [])
            if models:
                logger.info("Allowed %s models: %s", label, ", ".join(m["id"] for m in models))
            else:
                logger.info("Allowed %s models: <none>", label)


def _warn_image_model(openai_all_ids: set[str]) -> None:
    """Warn if the configured image model is absent from the live OpenAI model list."""
    if openai_all_ids and settings.image_model not in openai_all_ids:
        logger.warning(
            "Image model %s is not available in this OpenAI account", settings.image_model
        )


async def refresh() -> dict:
    global _cache, _cache_time

    # fetch only for configured providers; unconfigured → empty (not fallback)
    openai_all_ids: set[str] = set()
    if settings.openai_api_key:
        openai_task = _fetch_openai_models()
        anthropic_task = _fetch_anthropic_models() if settings.anthropic_api_key else asyncio.sleep(0, result=[])
        (openai_raw, openai_all_ids), anthropic_raw = await asyncio.gather(openai_task, anthropic_task)
    else:
        openai_raw = []
        if settings.anthropic_api_key:
            anthropic_raw = await _fetch_anthropic_models()
        else:
            anthropic_raw = []

    openai_raw = sorted(openai_raw, key=lambda m: m["id"])
    anthropic_raw = sorted(anthropic_raw, key=lambda m: m["id"])

    openai_filtered = sorted(_apply_allowed(openai_raw), key=lambda m: m["id"])
    anthropic_filtered = sorted(_apply_allowed(anthropic_raw), key=lambda m: m["id"])

    _warn_image_model(openai_all_ids)
    log_available_models(
        {"openai": openai_raw, "anthropic": anthropic_raw},
        {"openai": openai_filtered, "anthropic": anthropic_filtered},
    )

    _cache = {
        "openai": openai_filtered,
        "anthropic": anthropic_filtered,
        "defaults": PROVIDER_DEFAULTS,
    }
    _cache_time = time.monotonic()
    return _cache


async def get_models() -> dict:
    if _cache and time.monotonic() - _cache_time <= _CACHE_TTL:
        return _cache
    async with _refresh_lock:
        if _cache and time.monotonic() - _cache_time <= _CACHE_TTL:
            return _cache
        return await refresh()
