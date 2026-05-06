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


# ---- _apply_spec unit tests ----


def _spec(spec, fetched):
    from backend.model_registry import _apply_spec

    store: dict = {}
    result = _apply_spec(spec, fetched, store)
    return result, store


def test_apply_spec_empty_returns_sorted():
    result, store = _spec(
        "", [{"id": "gpt-z", "label": "Z"}, {"id": "gpt-a", "label": "A"}]
    )
    assert [m["id"] for m in result] == ["gpt-a", "gpt-z"]
    assert store == {"gpt-z": "gpt-z", "gpt-a": "gpt-a"}


def test_apply_spec_whitespace_only_returns_sorted():
    result, _ = _spec(
        "   ", [{"id": "gpt-z", "label": "Z"}, {"id": "gpt-a", "label": "A"}]
    )
    assert [m["id"] for m in result] == ["gpt-a", "gpt-z"]


def test_apply_spec_filters_to_listed_models():
    fetched = [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ]
    result, store = _spec("gpt-4o", fetched)
    assert result == [{"id": "gpt-4o", "label": "GPT-4o"}]
    assert store == {"gpt-4o": "gpt-4o"}


def test_apply_spec_preserves_spec_order():
    fetched = [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ]
    result, _ = _spec("gpt-4o-mini gpt-4o", fetched)
    assert [m["id"] for m in result] == ["gpt-4o-mini", "gpt-4o"]


def test_apply_spec_label_override_hides_real_id():
    """Labeled models use the label as their public id — real id must not appear."""
    fetched = [{"id": "gpt-4o", "label": "GPT-4o"}]
    result, store = _spec("Default@gpt-4o", fetched)
    assert result == [{"id": "Default", "label": "Default"}]
    assert store == {"Default": "gpt-4o"}


def test_apply_spec_label_override_not_in_fetch():
    result, store = _spec("MyModel@gpt-99", [])
    assert result == [{"id": "MyModel", "label": "MyModel"}]
    assert store == {"MyModel": "gpt-99"}


def test_apply_spec_unknown_model_uses_id_as_label():
    fetched = [{"id": "gpt-4o", "label": "GPT-4o"}]
    result, store = _spec("gpt-99", fetched)
    assert result == [{"id": "gpt-99", "label": "gpt-99"}]
    assert store == {"gpt-99": "gpt-99"}


def test_apply_spec_mixed_override_and_plain():
    fetched = [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ]
    result, store = _spec("Preferred@gpt-4o gpt-4o-mini", fetched)
    assert result == [
        {"id": "Preferred", "label": "Preferred"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ]
    assert store == {"Preferred": "gpt-4o", "gpt-4o-mini": "gpt-4o-mini"}


def test_apply_spec_extra_spaces_between_entries():
    fetched = [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ]
    result, _ = _spec("gpt-4o   gpt-4o-mini", fetched)
    assert len(result) == 2


def test_apply_spec_trailing_space():
    fetched = [{"id": "gpt-4o", "label": "GPT-4o"}]
    result, _ = _spec("gpt-4o ", fetched)
    assert result == [{"id": "gpt-4o", "label": "GPT-4o"}]


# ---- resolve_model_id ----


async def test_resolve_model_id_labeled(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "Default@gpt-5.5")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        await reg.refresh()

    assert reg.resolve_model_id("openai", "Default") == "gpt-5.5"


async def test_resolve_model_id_unlabeled(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        await reg.refresh()

    assert reg.resolve_model_id("openai", "gpt-4o") == "gpt-4o"


async def test_resolve_model_id_same_label_different_providers(monkeypatch):
    """Same label on two providers resolves to different real IDs."""
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "Default@gpt-5.5")
    monkeypatch.setattr(cfg.settings, "anthropic_models", "Default@claude-opus-4-7")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with (
        patch(
            "backend.model_registry._fetch_openai_models",
            new=AsyncMock(return_value=_OPENAI_FETCH),
        ),
        patch(
            "backend.model_registry._fetch_anthropic_models",
            new=AsyncMock(return_value=_ANTHROPIC_MODELS),
        ),
    ):
        await reg.refresh()

    assert reg.resolve_model_id("openai", "Default") == "gpt-5.5"
    assert reg.resolve_model_id("anthropic", "Default") == "claude-opus-4-7"


def test_resolve_model_id_unknown_falls_back_to_alias():
    import backend.model_registry as reg

    reg._alias_map = {}
    assert reg.resolve_model_id("openai", "some-model") == "some-model"


# ---- refresh() integration tests with per-provider specs ----


async def test_openai_models_spec_filters(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        result = await reg.refresh()

    assert result["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]


async def test_openai_models_spec_label_override(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "Default@gpt-4o")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        result = await reg.refresh()

    # public id is the label; real id (gpt-4o) is not exposed
    assert result["openai"] == [{"id": "Default", "label": "Default"}]


async def test_anthropic_models_spec_filters(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "anthropic_models", "claude-sonnet-4-6")
    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_anthropic_models",
        new=AsyncMock(return_value=_ANTHROPIC_MODELS),
    ):
        result = await reg.refresh()

    assert result["anthropic"] == [
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}
    ]


async def test_per_provider_specs_are_independent(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "gpt-4o")
    monkeypatch.setattr(cfg.settings, "anthropic_models", "claude-sonnet-4-6")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with (
        patch(
            "backend.model_registry._fetch_openai_models",
            new=AsyncMock(return_value=_OPENAI_FETCH),
        ),
        patch(
            "backend.model_registry._fetch_anthropic_models",
            new=AsyncMock(return_value=_ANTHROPIC_MODELS),
        ),
    ):
        result = await reg.refresh()

    assert result["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]
    assert result["anthropic"] == [
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}
    ]


async def test_empty_spec_shows_all(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "")
    monkeypatch.setattr(cfg.settings, "anthropic_models", "")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with (
        patch(
            "backend.model_registry._fetch_openai_models",
            new=AsyncMock(return_value=_OPENAI_FETCH),
        ),
        patch(
            "backend.model_registry._fetch_anthropic_models",
            new=AsyncMock(return_value=_ANTHROPIC_MODELS),
        ),
    ):
        result = await reg.refresh()

    assert len(result["openai"]) == 2
    assert len(result["anthropic"]) == 2


async def test_spec_with_unknown_model_includes_it(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "nonexistent-model")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        result = await reg.refresh()

    assert result["openai"] == [
        {"id": "nonexistent-model", "label": "nonexistent-model"}
    ]


# ---- Unconfigured providers ----


async def test_openai_not_configured_returns_empty_no_fallback(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_anthropic_models",
        new=AsyncMock(return_value=_ANTHROPIC_MODELS),
    ):
        result = await reg.refresh()

    assert result["openai"] == []
    assert all(m["id"] != "gpt-4o" for m in result["openai"])
    assert len(result["anthropic"]) == 2


async def test_anthropic_not_configured_returns_empty_no_fallback(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        result = await reg.refresh()

    assert result["anthropic"] == []
    assert all(m["id"] != "claude-opus-4-7" for m in result["anthropic"])
    assert len(result["openai"]) == 2


async def test_both_providers_not_configured_returns_empty(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    result = await reg.refresh()

    assert result["openai"] == []
    assert result["anthropic"] == []


# ---- Alphabetical sorting (no spec) ----


async def test_models_sorted_alphabetically_when_no_spec(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    unsorted = [
        {"id": "gpt-z-model", "label": "Z"},
        {"id": "gpt-a-model", "label": "A"},
        {"id": "gpt-m-model", "label": "M"},
    ]
    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=(unsorted, set())),
    ):
        result = await reg.refresh()

    ids = [m["id"] for m in result["openai"]]
    assert ids == sorted(ids)


async def test_spec_preserves_custom_order(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_models", "gpt-4o-mini gpt-4o")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)

    with patch(
        "backend.model_registry._fetch_openai_models",
        new=AsyncMock(return_value=_OPENAI_FETCH),
    ):
        result = await reg.refresh()

    assert [m["id"] for m in result["openai"]] == ["gpt-4o-mini", "gpt-4o"]


# ---- log_available_models ----
# caplog can't capture these: simplechat logger has propagate=False so records
# never reach root. Mock the logger directly instead.


def _logged(mock_info):
    return [
        c.args[0] % c.args[1:] if len(c.args) > 1 else c.args[0]
        for c in mock_info.call_args_list
    ]


async def test_log_both_configured(monkeypatch):
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    fetched = {
        "openai": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}],
        "anthropic": [{"id": "claude-sonnet-4-6"}],
        "ollama": [],
    }
    alias_map = {
        "openai": {"gpt-4o": "gpt-4o", "gpt-4o-mini": "gpt-4o-mini"},
        "anthropic": {"claude-sonnet-4-6": "claude-sonnet-4-6"},
        "ollama": {},
    }
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(fetched, fetched, alias_map)

    msgs = _logged(mock_info)
    assert any("OpenAI models:" in s and "gpt-4o" in s for s in msgs)
    assert any("Anthropic models:" in s and "claude-sonnet-4-6" in s for s in msgs)
    assert any("OpenAI available models:" in s and "gpt-4o" in s for s in msgs)
    assert any("Anthropic available models:" in s and "claude-sonnet-4-6" in s for s in msgs)


async def test_log_neither_configured(monkeypatch):
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    empty = {"openai": [], "anthropic": [], "ollama": []}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(empty, empty, {"openai": {}, "anthropic": {}, "ollama": {}})

    msgs = _logged(mock_info)
    assert not any("OpenAI" in s for s in msgs)
    assert not any("Anthropic" in s for s in msgs)


async def test_log_one_configured_one_not(monkeypatch):
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    fetched = {"openai": [], "anthropic": [{"id": "claude-sonnet-4-6"}], "ollama": []}
    alias_map = {"openai": {}, "anthropic": {"claude-sonnet-4-6": "claude-sonnet-4-6"}, "ollama": {}}
    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(fetched, fetched, alias_map)

    msgs = _logged(mock_info)
    assert not any("OpenAI" in s for s in msgs)
    assert any("Anthropic" in s and "claude-sonnet-4-6" in s for s in msgs)


async def test_log_shows_real_ids_not_aliases(monkeypatch):
    """available line uses real model IDs from alias_map, not the public alias."""
    import backend.model_registry as reg
    from backend.model_registry import log_available_models

    fetched = {"openai": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}], "anthropic": [], "ollama": []}
    # spec filtered to one model, labeled "Fast" → real id "gpt-4o"
    final = {"openai": [{"id": "Fast"}], "anthropic": [], "ollama": []}
    alias_map = {"openai": {"Fast": "gpt-4o"}, "anthropic": {}, "ollama": {}}

    with patch.object(reg.logger, "info") as mock_info:
        log_available_models(fetched, final, alias_map)

    msgs = _logged(mock_info)
    # models line shows both real IDs
    assert any("OpenAI models:" in s and "gpt-4o-mini" in s for s in msgs)
    # available models line shows real ID, not alias
    assert any("OpenAI available models:" in s and "gpt-4o" in s for s in msgs)
    assert not any("Fast" in s for s in msgs)


# ---- /api/models endpoint ----


async def test_models_endpoint_returns_registry_data(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": [{"id": "gpt-4o", "label": "GPT-4o"}],
        "anthropic": [{"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}],
        "ollama": [],
        "defaults": {},
    }
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == [{"id": "gpt-4o", "label": "GPT-4o"}]
    assert data["anthropic"] == [
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"}
    ]


async def test_models_endpoint_empty_when_both_unconfigured(client):
    import backend.model_registry as reg

    reg._cache = {"openai": [], "anthropic": [], "ollama": [], "defaults": {}}
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == []
    assert data["anthropic"] == []


async def test_models_endpoint_respects_spec(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": [{"id": "gpt-4o", "label": "GPT-4o"}],
        "anthropic": [],
        "ollama": [],
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

    r = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
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
        "/api/profiles",
        json={"name": "noprovider", "password": "testPass1", "avatar": 0},
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

    r = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "claude-sonnet-4-6"}
    )
    assert r.status_code == 503


async def test_no_providers_stream_returns_503(client, monkeypatch):
    import backend.config as cfg

    # create the chat while keys are still available
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 201
    chat_id = r.json()["id"]

    # now remove the key — continuing the chat must fail before the stream starts
    monkeypatch.setattr(cfg.settings, "openai_api_key", None)

    r = await client.post(f"/api/chats/{chat_id}/messages", json={"content": "hello"})
    assert r.status_code == 503
    assert "OpenAI" in r.json()["detail"]


# ---- IMAGE_MODEL validation ----


async def test_image_model_warning_when_not_in_model_list(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-99")

    all_ids = {"gpt-4o", "gpt-image-2"}  # image-99 absent
    with (
        patch(
            "backend.model_registry._fetch_openai_models",
            new=AsyncMock(return_value=(_OPENAI_MODELS, all_ids)),
        ),
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
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-2")

    with (
        patch(
            "backend.model_registry._fetch_openai_models",
            new=AsyncMock(return_value=_OPENAI_FETCH),
        ),
        patch.object(reg.logger, "warning") as mock_warn,
    ):
        await reg.refresh()

    assert not mock_warn.called


async def test_no_image_model_warning_when_openai_unconfigured(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", None)
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
