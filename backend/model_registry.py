import re
import asyncio
import time
from openai import AsyncOpenAI
import anthropic
from .config import settings
from .schemas import PROVIDER_DEFAULTS

_CHAT_RE = re.compile(r'^(gpt-4|gpt-3\.5-turbo|o[0-9]|chatgpt-)', re.IGNORECASE)
_EXCLUDE_RE = re.compile(r'(embed|whisper|tts-|instruct|realtime|transcr|moderat|search|audio)', re.IGNORECASE)

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


async def _fetch_openai() -> list[dict]:
    if not settings.openai_api_key:
        return []
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.models.list()
    models_with_ts = [
        ({"id": m.id, "label": m.id}, m.created)
        for m in resp.data
        if _CHAT_RE.match(m.id) and not _EXCLUDE_RE.search(m.id) and ":" not in m.id
    ]
    models_with_ts.sort(key=lambda x: x[1], reverse=True)
    return [m for m, _ in models_with_ts]


async def _fetch_anthropic() -> list[dict]:
    if not settings.anthropic_api_key:
        return []
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.models.list()
    return [
        {"id": m.id, "label": getattr(m, "display_name", m.id)}
        for m in resp.data
    ]


async def refresh() -> dict:
    global _cache, _cache_time
    results = await asyncio.gather(_fetch_openai(), _fetch_anthropic(), return_exceptions=True)
    openai_models = results[0] if isinstance(results[0], list) and results[0] else _FALLBACK_OPENAI
    anthropic_models = results[1] if isinstance(results[1], list) and results[1] else _FALLBACK_ANTHROPIC
    _cache = {"openai": openai_models, "anthropic": anthropic_models, "defaults": PROVIDER_DEFAULTS}
    _cache_time = time.monotonic()
    return _cache


async def get_models() -> dict:
    if _cache and time.monotonic() - _cache_time <= _CACHE_TTL:
        return _cache
    async with _refresh_lock:
        # re-check under lock in case another coroutine refreshed while we waited
        if _cache and time.monotonic() - _cache_time <= _CACHE_TTL:
            return _cache
        return await refresh()
