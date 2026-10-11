import asyncio
import logging
import time

import anthropic
import httpx
from openai import AsyncOpenAI

from .config import settings
from .schemas import CHAT_TIERS, CLOUD_PROVIDERS, PROVIDER_DEFAULTS, tier_model

logger = logging.getLogger("simplechat.models")

_TIERS = ("task", *CHAT_TIERS)
_cache: dict = {}
_cache_time: float = 0.0
_CACHE_TTL = 3600.0
_refresh_lock = asyncio.Lock()

# ollama alias → real model ID; populated during refresh
_ollama_alias_map: dict[str, str] = {}


def resolve_model_id(provider: str, alias: str) -> str:
    """Translate a chat's stored model to the real provider model ID.

    Cloud chats store a tier, resolved against the current config so a config change moves every
    chat on that tier.  Ollama chats store a public alias (a label hides the real ID).  Anything
    unrecognised passes through unchanged.
    """
    if provider in CLOUD_PROVIDERS:
        return tier_model(provider, alias) if alias in CHAT_TIERS else alias
    return _ollama_alias_map.get(alias, alias)


def _tier_models() -> list[dict]:
    return [{"id": tier, "label": label} for tier, label in CHAT_TIERS.items()]


def _apply_spec(
    spec: str, fetched: list[dict], alias_store: dict[str, str]
) -> list[dict]:
    """Apply an Ollama model spec against fetched models.

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


async def _fetch_openai_ids() -> set[str]:
    """Fetch live OpenAI model IDs; empty set on failure."""
    try:
        resp = await AsyncOpenAI(api_key=settings.openai_api_key).models.list()
        return {m.id for m in resp.data}
    except Exception:
        return set()


async def _fetch_anthropic_ids() -> set[str]:
    """Fetch live Anthropic model IDs; empty set on failure."""
    try:
        resp = await anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key).models.list()
        return {m.id for m in resp.data}
    except Exception:
        return set()


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
    configured: tuple[str, ...], ollama_fetched: list[dict], ollama_final: list[dict], ollama_alias_map: dict[str, str]
) -> None:
    for provider, label in (("openai", "OpenAI"), ("anthropic", "Anthropic")):
        if provider in configured:
            tiers = ", ".join(f"{tier}={tier_model(provider, tier)}" for tier in _TIERS)
            logger.info("%s models: %s", label, tiers)
    if ollama_fetched:
        logger.info("Ollama models: %s", ", ".join(m["id"] for m in ollama_fetched))
    if ollama_final:
        real_names = [ollama_alias_map.get(m["id"], m["id"]) for m in ollama_final]
        logger.info("Ollama available models: %s", ", ".join(real_names))


def _warn_missing_models(provider: str, live_ids: set[str]) -> None:
    """Warn about configured models absent from the provider's live model list."""
    if not live_ids:
        return
    wanted = [tier_model(provider, tier) for tier in _TIERS]
    if provider == "openai":
        wanted.append(settings.image_model)
    for model in wanted:
        if model not in live_ids:
            logger.warning("Model %s is not available in this %s account", model, provider)


async def refresh() -> dict:
    global _cache, _cache_time, _ollama_alias_map

    configured = tuple(p for p in CLOUD_PROVIDERS if getattr(settings, f"{p}_api_key"))
    fetchers = {"openai": _fetch_openai_ids, "anthropic": _fetch_anthropic_ids}
    tasks = [fetchers[p]() for p in configured]
    if settings.ollama_api_url:
        tasks.append(_fetch_ollama_models())

    results = await asyncio.gather(*tasks)
    for provider, live_ids in zip(configured, results):
        _warn_missing_models(provider, live_ids)
    ollama_fetched = results[len(configured)] if settings.ollama_api_url else []

    alias_store: dict[str, str] = {}
    ollama_final = _apply_spec(settings.ollama_models, ollama_fetched, alias_store)
    _ollama_alias_map = alias_store

    log_available_models(configured, ollama_fetched, ollama_final, alias_store)

    # unconfigured providers → empty, so the UI hides them
    _cache = {
        **{p: _tier_models() if p in configured else [] for p in CLOUD_PROVIDERS},
        "ollama": ollama_final,
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
