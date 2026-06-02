"""
Integration tests for web search with real API calls.

These tests read API keys from the project's .env file, bypassing the fake keys
that conftest.py injects for unit tests. They auto-skip when real keys are absent.

Run them alongside the normal suite — they won't fail, just skip.
To run only these:
  pytest tests/backend/test_web_search_integration.py -v
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio

_SEARCH_QUERY = "What is the latest stable release version of Python?"
_FAKE_ANTHROPIC = "sk-test-anthropic"
_FAKE_OPENAI = "sk-test-openai"


def _read_dot_env() -> dict[str, str]:
    env_path = Path(__file__).parents[2] / ".env"
    if not env_path.exists():
        return {}
    result = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


@pytest.fixture
def real_anthropic_key(monkeypatch):
    key = _read_dot_env().get("ANTHROPIC_API_KEY")
    if not key or key == _FAKE_ANTHROPIC:
        pytest.skip("Real ANTHROPIC_API_KEY not in .env")
    from backend.config import settings
    monkeypatch.setattr(settings, "anthropic_api_key", key)
    return key


@pytest.fixture
def real_openai_key(monkeypatch):
    key = _read_dot_env().get("OPENAI_API_KEY")
    if not key or key == _FAKE_OPENAI:
        pytest.skip("Real OPENAI_API_KEY not in .env")
    from backend.config import settings
    monkeypatch.setattr(settings, "openai_api_key", key)
    return key


async def test_anthropic_web_search_returns_sources(real_anthropic_key):
    """Anthropic web search must return at least one source URL in a tool_result event."""
    from backend.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    events = []
    async for event in provider.stream_chat(
        [{"role": "user", "content": _SEARCH_QUERY}],
        model="claude-sonnet-4-6",
        web_search=True,
    ):
        events.append(event)

    assert any(e["type"] == "searching" for e in events), (
        "No 'searching' event — web search was not triggered"
    )

    tool_results = [
        e for e in events
        if e["type"] == "tool_result" and e.get("name") == "web_search"
    ]
    assert tool_results, f"No web_search tool_result event. All events: {[e['type'] for e in events]}"

    sources = tool_results[0].get("sources", [])
    assert sources, f"tool_result carries no sources: {tool_results[0]}"
    assert all(s.startswith("http") for s in sources), f"Unexpected source URLs: {sources}"

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert len(text) > 20, f"Response text too short: {text!r}"


async def test_openai_web_search_returns_sources(real_openai_key):
    """OpenAI Responses API web search must return at least one source URL in a tool_result event."""
    from backend.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    events = []
    async for event in provider.stream_chat(
        [{"role": "user", "content": _SEARCH_QUERY}],
        model="gpt-4o-mini",
        web_search=True,
    ):
        events.append(event)

    assert any(e["type"] == "searching" for e in events), (
        "No 'searching' event — web search was not triggered"
    )

    tool_results = [
        e for e in events
        if e["type"] == "tool_result" and e.get("name") == "web_search"
    ]
    assert tool_results, f"No web_search tool_result event. All events: {[e['type'] for e in events]}"

    sources = tool_results[0].get("sources", [])
    assert sources, f"tool_result carries no sources: {tool_results[0]}"
    assert all(s.startswith("http") for s in sources), f"Unexpected source URLs: {sources}"

    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert len(text) > 20, f"Response text too short: {text!r}"
