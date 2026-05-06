import asyncio
import logging
import re
import time

import anthropic
import httpx
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

# alias → real model ID per provider; populated during refresh
_alias_map: dict[str, dict[str, str]] = {}


def resolve_model_id(provider: str, alias: str) -> str:
    """Translate a public model alias back to the real provider model ID.

    For unlabeled models the alias IS the real ID.  For labeled models the
    real ID is hidden behind the label.  Falls back to the alias unchanged if
    the map is empty (e.g. cache not yet populated).
    """
    return _alias_map.get(provider, {}).get(alias, alias)


def _apply_spec(
    spec: str, fetched: list[dict], alias_store: dict[str, str]
) -> list[dict]:
    """Apply a provider model spec against fetched models.

    Spec format: space-separated entries, each either `model-id` or `Label@model-id`.
    Empty spec → return fetched models sorted alphabetically (real IDs as public IDs).
    Non-empty spec → return models in spec order.  For labeled entries the public
    id is the label (hides the real model ID); for unlabeled entries the public id
    is the model ID itself.

    alias_store is mutated: maps public_id → real_model_id.
    """
    parts = spec.split()
    if not parts:
        for m in fetched:
            alias_store[m["id"]] = m["id"]
        return sorted(fetched, key=lambda m: m["id"])

    fetched_labels: dict[str, str] = {m["id"]: m["label"] for m in fetched}
    result = []
    for part in parts:
        if "@" in part:
            label, model_id = part.split("@", 1)
            alias_store[label] = model_id
            result.append({"id": label, "label": label})
        else:
            alias_store[part] = part
            result.append({"id": part, "label": fetched_labels.get(part, part)})
    return result


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
        result = [
            {"id": m.id, "label": getattr(m, "display_name", m.id)} for m in resp.data
        ]
        return result if result else _FALLBACK_ANTHROPIC
    except Exception:
        return _FALLBACK_ANTHROPIC


async def _fetch_ollama_models() -> list[dict]:
    """Fetch locally available Ollama models via /api/tags; returns [] on failure."""
    base = settings.ollama_api_url.rstrip("/")  # type: ignore[union-attr]
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        models = [{"id": m["name"], "label": m["name"]} for m in data.get("models", [])]
        return models
    except Exception:
        logger.warning("Could not reach Ollama at %s — no models available", base)
        return []


def log_available_models(
    fetched: dict, final: dict, alias_map: dict[str, dict[str, str]]
) -> None:
    for provider, label in (
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("ollama", "Ollama"),
    ):
        all_models = fetched.get(provider, [])
        available = final.get(provider, [])
        if not all_models and not available:
            continue
        if all_models:
            logger.info("%s models: %s", label, ", ".join(m["id"] for m in all_models))
        if available:
            pmap = alias_map.get(provider, {})
            real_names = [pmap.get(m["id"], m["id"]) for m in available]
            logger.info("%s available models: %s", label, ", ".join(real_names))


def _warn_image_model(openai_all_ids: set[str]) -> None:
    """Warn if the configured image model is absent from the live OpenAI model list."""
    if openai_all_ids and settings.image_model not in openai_all_ids:
        logger.warning(
            "Image model %s is not available in this OpenAI account",
            settings.image_model,
        )


async def refresh() -> dict:
    global _cache, _cache_time, _alias_map

    # fetch only for configured providers; unconfigured → empty (not fallback)
    openai_all_ids: set[str] = set()
    tasks = []
    task_keys = []

    if settings.openai_api_key:
        tasks.append(_fetch_openai_models())
        task_keys.append("openai")
    if settings.anthropic_api_key:
        tasks.append(_fetch_anthropic_models())
        task_keys.append("anthropic")
    if settings.ollama_api_url:
        tasks.append(_fetch_ollama_models())
        task_keys.append("ollama")

    results = await asyncio.gather(*tasks)
    fetched: dict[str, list] = {"openai": [], "anthropic": [], "ollama": []}
    for key, result in zip(task_keys, results):
        if key == "openai":
            openai_raw, openai_all_ids = result
            fetched["openai"] = openai_raw
        else:
            fetched[key] = result

    specs = {
        "openai": settings.openai_models,
        "anthropic": settings.anthropic_models,
        "ollama": settings.ollama_models,
    }
    new_alias_map: dict[str, dict[str, str]] = {}
    final: dict[str, list] = {}
    for key in fetched:
        store: dict[str, str] = {}
        final[key] = _apply_spec(specs[key], fetched[key], store)
        new_alias_map[key] = store

    _alias_map = new_alias_map

    _warn_image_model(openai_all_ids)
    log_available_models(fetched, final, new_alias_map)

    _cache = {
        "openai": final["openai"],
        "anthropic": final["anthropic"],
        "ollama": final["ollama"],
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
