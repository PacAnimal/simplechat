from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

_OPENAI_MODELS = [
    {"id": "gpt-4o", "label": "GPT-4o"},
    {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
]
# full id set returned alongside chat models; includes image model so tests don't trigger warnings
_OPENAI_ALL_IDS = {"gpt-4o", "gpt-4o-mini", "gpt-image-2"}
_OPENAI_FETCH = (_OPENAI_MODELS, _OPENAI_ALL_IDS)
_ANTHROPIC_MODELS = [
    {"id": "claude-opus-4-7", "label": "Claude Opus 4.7"},
    {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
]


@pytest.fixture(autouse=True)
def reset_registry_cache():
    import backend.model_registry as reg

    reg._cache = {}
    reg._cache_time = 0.0
    yield
    reg._cache = {}
    reg._cache_time = 0.0


# ---- ALLOWED_MODELS filtering ----


async def test_allowed_models_filters_openai(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)

    with patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)):
        result = await reg.refresh()

    assert result["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]


async def test_allowed_models_filters_anthropic(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", "claude-sonnet-4-6")
    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")

    with patch("backend.model_registry._fetch_anthropic_models", new=AsyncMock(return_value=_ANTHROPIC_MODELS)):
        result = await reg.refresh()

    assert result["anthropic"] == [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}]


async def test_allowed_models_filters_both_providers(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", "gpt-4o,claude-sonnet-4-6")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")

    with (
        patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)),
        patch("backend.model_registry._fetch_anthropic_models", new=AsyncMock(return_value=_ANTHROPIC_MODELS)),
    ):
        result = await reg.refresh()

    assert result["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]
    assert result["anthropic"] == [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}]


async def test_empty_allowed_models_shows_all(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")

    with (
        patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)),
        patch("backend.model_registry._fetch_anthropic_models", new=AsyncMock(return_value=_ANTHROPIC_MODELS)),
    ):
        result = await reg.refresh()

    assert len(result["openai"]) == 2
    assert len(result["anthropic"]) == 2


async def test_allowed_models_no_match_returns_empty(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", "nonexistent-model")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)

    with patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)):
        result = await reg.refresh()

    assert result["openai"] == []


async def test_allowed_models_ignores_whitespace(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "allowed_models", " gpt-4o , gpt-4o-mini ")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)

    with patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)):
        result = await reg.refresh()

    assert len(result["openai"]) == 2


# ---- Unconfigured providers ----


async def test_openai_not_configured_returns_empty_no_fallback(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "allowed_models", "")

    with patch("backend.model_registry._fetch_anthropic_models", new=AsyncMock(return_value=_ANTHROPIC_MODELS)):
        result = await reg.refresh()

    assert result["openai"] == []
    # fallback ids must not leak through
    assert all(m["id"] != "gpt-4o" for m in result["openai"])
    assert len(result["anthropic"]) == 2


async def test_anthropic_not_configured_returns_empty_no_fallback(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "allowed_models", "")

    with patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)):
        result = await reg.refresh()

    assert result["anthropic"] == []
    assert all(m["id"] != "claude-opus-4-7" for m in result["anthropic"])
    assert len(result["openai"]) == 2


async def test_both_providers_not_configured_returns_empty(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "allowed_models", "")

    result = await reg.refresh()

    assert result["openai"] == []
    assert result["anthropic"] == []


# ---- Alphabetical sorting ----


async def test_models_sorted_alphabetically(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "allowed_models", "")

    unsorted = [
        {"id": "gpt-z-model", "label": "Z"},
        {"id": "gpt-a-model", "label": "A"},
        {"id": "gpt-m-model", "label": "M"},
    ]
    with patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=(unsorted, set()))):
        result = await reg.refresh()

    ids = [m["id"] for m in result["openai"]]
    assert ids == sorted(ids)


# ---- log_available_models ----
# caplog can't capture these: simplechat logger has propagate=False so records
# never reach root. Mock the logger directly instead.

def _logged(mock_info):
    return [c.args[0] % c.args[1:] if len(c.args) > 1 else c.args[0] for c in mock_info.call_args_list]


async def test_log_both_configured(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    raw = {"openai": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}],
           "anthropic": [{"id": "claude-sonnet-4-6"}]}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(raw, raw)

    msgs = _logged(mock_info)
    assert any("OpenAI models:" in s and "gpt-4o" in s for s in msgs)
    assert any("Anthropic models:" in s and "claude-sonnet-4-6" in s for s in msgs)
    assert not any("Allowed" in s for s in msgs)


async def test_log_neither_configured(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    empty = {"openai": [], "anthropic": []}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(empty, empty)

    msgs = _logged(mock_info)
    assert not any("OpenAI" in s for s in msgs)
    assert not any("Anthropic" in s for s in msgs)


async def test_log_one_configured_one_not(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    raw = {"openai": [], "anthropic": [{"id": "claude-sonnet-4-6"}]}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(raw, raw)

    msgs = _logged(mock_info)
    assert not any("OpenAI" in s for s in msgs)
    assert any("Anthropic models:" in s and "claude-sonnet-4-6" in s for s in msgs)


async def test_log_allowed_lines_shown_when_filter_set(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    monkeypatch.setattr(cfg.settings, "allowed_models", "gpt-4o,claude-sonnet-4-6")
    raw = {"openai": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}],
           "anthropic": [{"id": "claude-opus-4-7"}, {"id": "claude-sonnet-4-6"}]}
    filtered = {"openai": [{"id": "gpt-4o"}], "anthropic": [{"id": "claude-sonnet-4-6"}]}

    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(raw, filtered)

    msgs = _logged(mock_info)
    # all-models lines contain the full lists
    assert any("OpenAI models:" in s and "gpt-4o-mini" in s for s in msgs)
    assert any("Anthropic models:" in s and "claude-opus-4-7" in s for s in msgs)
    # allowed lines contain only filtered models
    assert any("Allowed OpenAI models:" in s and "gpt-4o" in s and "gpt-4o-mini" not in s for s in msgs)
    assert any("Allowed Anthropic models:" in s and "claude-sonnet-4-6" in s and "claude-opus-4-7" not in s for s in msgs)


async def test_log_no_allowed_lines_when_filter_empty(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    raw = {"openai": [{"id": "gpt-4o"}], "anthropic": [{"id": "claude-sonnet-4-6"}]}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(raw, raw)

    msgs = _logged(mock_info)
    assert not any("Allowed" in s for s in msgs)


# ---- /api/models endpoint ----


async def test_models_endpoint_returns_registry_data(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": [{"id": "gpt-4o", "label": "GPT-4o"}],
        "anthropic": [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}],
        "defaults": {},
    }
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]
    assert data["anthropic"] == [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}]


async def test_models_endpoint_empty_when_both_unconfigured(client):
    import backend.model_registry as reg

    reg._cache = {"openai": [], "anthropic": [], "defaults": {}}
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == []
    assert data["anthropic"] == []


async def test_models_endpoint_filtered_by_allowed_models(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": [{"id": "gpt-4o", "label": "GPT-4o"}],
        "anthropic": [],
        "defaults": {},
    }
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert len(data["openai"]) == 1
    assert data["openai"][0]["id"] == "gpt-4o"


# ---- OpenAI not configured disables image generation ----


async def test_openai_provider_raises_without_key_disabling_image_tool():
    """No OpenAI key means OpenAIProvider (and thus image generation) cannot be used."""
    import backend.providers.openai_provider as m

    original = m.settings.openai_api_key
    m.settings.openai_api_key = None
    try:
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            m.OpenAIProvider()
    finally:
        m.settings.openai_api_key = original


# ---- Unconfigured provider returns 503 on create_chat and stream ----


async def test_create_chat_503_when_openai_not_configured(client, monkeypatch):
    import backend.api.chats as chats_module
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(chats_module.settings, "openai_api_key", None)

    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 503
    assert "OpenAI" in r.json()["detail"]


async def test_create_chat_503_when_anthropic_not_configured(client, monkeypatch):
    import backend.api.chats as chats_module
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(chats_module.settings, "anthropic_api_key", None)

    r = await client.post("/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"})
    assert r.status_code == 503
    assert "Anthropic" in r.json()["detail"]


async def test_create_chat_succeeds_when_configured(client):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201


# ---- Both providers unconfigured: app usable but no chats ----


async def test_no_providers_profile_creation_still_works(unauthed_client, monkeypatch):
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)

    r = await unauthed_client.post(
        "/api/profiles", json={"name": "noprovider", "password": "testPass1", "avatar": 0}
    )
    assert r.status_code == 201
    profile_id = r.json()["id"]

    login = await unauthed_client.post(
        f"/api/profiles/{profile_id}/login", json={"password": "testPass1"}
    )
    assert login.status_code == 200
    assert "token" in login.json()


async def test_no_providers_create_chat_returns_503(client, monkeypatch):
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)

    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 503

    r = await client.post("/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"})
    assert r.status_code == 503


async def test_no_providers_stream_returns_503(client, monkeypatch):
    import backend.config as cfg

    # create the chat while keys are still available
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201
    chat_id = r.json()["id"]

    # now remove the key — continuing the chat must fail before the stream starts
    monkeypatch.setattr(cfg.settings, "openai_api_key", None)

    r = await client.post(
        f"/api/chats/{chat_id}/messages", json={"content": "hello"}
    )
    assert r.status_code == 503
    assert "OpenAI" in r.json()["detail"]


# ---- IMAGE_MODEL validation ----


async def test_image_model_warning_when_not_in_model_list(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-99")

    all_ids = {"gpt-4o", "gpt-image-2"}  # image-99 absent
    with (
        patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=(_OPENAI_MODELS, all_ids))),
        patch.object(reg.logger, "warning") as mock_warn,
    ):
        await reg.refresh()

    assert mock_warn.called
    warned = str(mock_warn.call_args_list)
    assert "gpt-image-99" in warned


async def test_no_image_model_warning_when_model_available(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-2")

    with (
        patch("backend.model_registry._fetch_openai_models", new=AsyncMock(return_value=_OPENAI_FETCH)),
        patch.object(reg.logger, "warning") as mock_warn,
    ):
        await reg.refresh()

    assert not mock_warn.called


async def test_no_image_model_warning_when_openai_unconfigured(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "allowed_models", "")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-2")

    with patch.object(reg.logger, "warning") as mock_warn:
        await reg.refresh()

    assert not mock_warn.called


async def test_image_model_used_in_generation(monkeypatch):
    """image_gen.py must pass settings.image_model to the API, not a hardcoded string."""
    import backend.config as cfg
    from backend.tools.image_gen import generate_image

    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-custom")

    captured = {}

    async def fake_generate(**kwargs):
        captured["model"] = kwargs.get("model")

        class FakeData:
            b64_json = "aGVsbG8="  # base64 for "hello"

        class FakeResp:
            data = [FakeData()]

        return FakeResp()

    from unittest.mock import MagicMock
    mock_client = MagicMock()
    mock_client.images.generate = fake_generate

    with patch("backend.tools.image_gen.AsyncOpenAI", return_value=mock_client):
        await generate_image("a cat")

    assert captured["model"] == "gpt-image-custom"
