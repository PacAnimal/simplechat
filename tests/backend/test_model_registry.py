from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

_TIERS = [{"id": "chat", "label": "Chat"}, {"id": "thinking", "label": "Thinking"}]


def _live_ids(provider: str) -> set[str]:
    """Live model list containing every model this provider is configured to use."""
    from backend.config import settings
    from backend.schemas import tier_model

    ids = {tier_model(provider, t) for t in ("task", "chat", "thinking")}
    return ids | {settings.image_model} if provider == "openai" else ids


def _configure(monkeypatch, openai: bool, anthropic: bool, ollama: str | None = None):
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "openai_api_key", "sk-test" if openai else None)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "sk-test" if anthropic else None)
    monkeypatch.setattr(cfg.settings, "ollama_api_url", ollama)


def _live(openai_ids: set[str] | None = None, anthropic_ids: set[str] | None = None):
    """Patch the live listings; None means "everything configured is available"."""
    import contextlib

    stack = contextlib.ExitStack()
    stack.enter_context(patch(
        "backend.model_registry._fetch_openai_ids",
        new=AsyncMock(return_value=_live_ids("openai") if openai_ids is None else openai_ids),
    ))
    stack.enter_context(patch(
        "backend.model_registry._fetch_anthropic_ids",
        new=AsyncMock(return_value=_live_ids("anthropic") if anthropic_ids is None else anthropic_ids),
    ))
    return stack


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
    fetched = _TIERS
    result, store = _spec("Default@gpt-4o", fetched)
    assert result == [{"id": "Default", "label": "Default"}]
    assert store == {"Default": "gpt-4o"}


def test_apply_spec_label_override_not_in_fetch():
    result, store = _spec("MyModel@gpt-99", [])
    assert result == [{"id": "MyModel", "label": "MyModel"}]
    assert store == {"MyModel": "gpt-99"}


def test_apply_spec_unknown_model_uses_id_as_label():
    fetched = _TIERS
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


# ---- cloud tiers ----


async def test_cloud_providers_offer_exactly_the_chat_and_thinking_tiers(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=True, anthropic=True)
    with _live():
        result = await reg.refresh()

    assert result["openai"] == _TIERS
    assert result["anthropic"] == _TIERS
    assert result["defaults"]["openai"] == "chat"
    assert result["defaults"]["anthropic"] == "chat"


async def test_real_model_ids_are_never_offered(monkeypatch):
    """Clients only ever see tier names; the task tier is not offered at all."""
    import backend.model_registry as reg
    from backend.schemas import tier_model

    _configure(monkeypatch, openai=True, anthropic=True)
    with _live():
        result = await reg.refresh()

    offered = str(result["openai"] + result["anthropic"])
    for provider in ("openai", "anthropic"):
        for tier in ("task", "chat", "thinking"):
            assert tier_model(provider, tier) not in offered
    assert "task" not in offered


async def test_tier_resolves_against_current_config(monkeypatch):
    """Changing a tier's model moves every chat on that tier — no refresh, no data change."""
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "anthropic_model_thinking", "claude-opus-4-7")
    assert reg.resolve_model_id("anthropic", "thinking") == "claude-opus-4-7"

    monkeypatch.setattr(cfg.settings, "anthropic_model_thinking", "claude-opus-9")
    assert reg.resolve_model_id("anthropic", "thinking") == "claude-opus-9"


async def test_each_provider_resolves_its_own_tier_models(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    monkeypatch.setattr(cfg.settings, "openai_model_chat", "gpt-chat")
    monkeypatch.setattr(cfg.settings, "anthropic_model_chat", "claude-chat")

    assert reg.resolve_model_id("openai", "chat") == "gpt-chat"
    assert reg.resolve_model_id("anthropic", "chat") == "claude-chat"


def test_resolve_model_id_unknown_falls_back_to_alias():
    import backend.model_registry as reg

    reg._ollama_alias_map = {}
    assert reg.resolve_model_id("openai", "some-model") == "some-model"
    assert reg.resolve_model_id("ollama", "some-model") == "some-model"


async def test_ollama_label_resolves_to_real_model_and_only_for_ollama(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    _configure(monkeypatch, openai=False, anthropic=False, ollama="http://ollama.local:11434")
    monkeypatch.setattr(cfg.settings, "ollama_models", "Dark@llama3")
    with patch(
        "backend.model_registry._fetch_ollama_models",
        new=AsyncMock(return_value=[{"id": "llama3", "label": "llama3"}]),
    ):
        result = await reg.refresh()

    assert result["ollama"] == [{"id": "Dark", "label": "Dark"}]
    assert reg.resolve_model_id("ollama", "Dark") == "llama3"
    assert reg.resolve_model_id("openai", "Dark") == "Dark"


# ---- Unconfigured providers ----


async def test_openai_not_configured_returns_empty(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=False, anthropic=True)
    with _live():
        result = await reg.refresh()

    assert result["openai"] == []
    assert result["anthropic"] == _TIERS


async def test_anthropic_not_configured_returns_empty(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=True, anthropic=False)
    with _live():
        result = await reg.refresh()

    assert result["anthropic"] == []
    assert result["openai"] == _TIERS


async def test_both_providers_not_configured_returns_empty(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=False, anthropic=False)
    result = await reg.refresh()

    assert result["openai"] == []
    assert result["anthropic"] == []


# ---- tiers are the only cloud models a chat can be on ----


async def test_create_chat_rejects_a_real_model_id(client):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "gpt-4o"})
    assert r.status_code == 422


async def test_switch_chat_rejects_a_real_model_id(client):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
    chat_id = r.json()["id"]

    r = await client.patch(f"/api/chats/{chat_id}", json={"provider": "anthropic", "model": "claude-opus-5-5"})
    assert r.status_code == 422


async def test_switch_chat_to_thinking_tier(client):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
    chat_id = r.json()["id"]

    r = await client.patch(f"/api/chats/{chat_id}", json={"provider": "anthropic", "model": "thinking"})
    assert r.status_code == 200
    assert r.json()["model"] == "thinking"


async def test_create_chat_defaults_to_chat_tier(client):
    r = await client.post("/api/chats", json={"provider": "anthropic"})
    assert r.status_code == 201
    assert r.json()["model"] == "chat"


# ---- log_available_models ----
# caplog can't capture these: simplechat logger has propagate=False so records
# never reach root. Mock the logger directly instead.


def _logged(mock_info):
    return [
        c.args[0] % c.args[1:] if len(c.args) > 1 else c.args[0]
        for c in mock_info.call_args_list
    ]


async def test_log_shows_real_model_behind_each_tier(monkeypatch):
    import backend.model_registry as reg
    from backend.schemas import tier_model

    with patch.object(reg.logger, "info") as mock_info:
        reg.log_available_models(("anthropic",), [], [], {})

    msgs = _logged(mock_info)
    for tier in ("task", "chat", "thinking"):
        assert any("Anthropic models:" in s and f"{tier}={tier_model('anthropic', tier)}" in s for s in msgs)
    assert not any("OpenAI" in s for s in msgs)


async def test_log_neither_configured(monkeypatch):
    import backend.model_registry as reg

    with patch.object(reg.logger, "info") as mock_info:
        reg.log_available_models((), [], [], {})

    assert _logged(mock_info) == []


async def test_log_shows_real_ollama_ids_not_aliases(monkeypatch):
    """available line uses real model IDs from the alias map, not the public alias."""
    import backend.model_registry as reg

    fetched = [{"id": "llama3"}, {"id": "mistral"}]
    with patch.object(reg.logger, "info") as mock_info:
        reg.log_available_models((), fetched, [{"id": "Fast"}], {"Fast": "llama3"})

    msgs = _logged(mock_info)
    assert any("Ollama models:" in s and "mistral" in s for s in msgs)
    assert any("Ollama available models:" in s and "llama3" in s for s in msgs)
    assert not any("Fast" in s for s in msgs)


# ---- /api/models endpoint ----


async def test_models_endpoint_returns_registry_data(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": _TIERS,
        "anthropic": _TIERS,
        "ollama": [],
        "defaults": {},
    }
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == _TIERS
    assert data["anthropic"] == _TIERS


async def test_models_endpoint_empty_when_both_unconfigured(client):
    import backend.model_registry as reg

    reg._cache = {"openai": [], "anthropic": [], "ollama": [], "defaults": {}}
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == []
    assert data["anthropic"] == []


async def test_models_endpoint_serves_cached_list(client):
    import backend.model_registry as reg

    reg._cache = {
        "openai": _TIERS,
        "anthropic": [],
        "ollama": [],
        "defaults": {},
    }
    reg._cache_time = float("inf")

    r = await client.get("/api/models")
    assert r.status_code == 200
    data = r.json()
    assert data["openai"] == _TIERS


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

    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
    assert r.status_code == 503
    assert "OpenAI" in r.json()["detail"]


async def test_create_chat_503_when_anthropic_not_configured(client, monkeypatch):
    import backend.api.chats as chats_module
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "anthropic_api_key", None)
    monkeypatch.setattr(chats_module.settings, "anthropic_api_key", None)

    r = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "chat"}
    )
    assert r.status_code == 503
    assert "Anthropic" in r.json()["detail"]


async def test_create_chat_succeeds_when_configured(client):
    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
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

    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
    assert r.status_code == 503

    r = await client.post(
        "/api/chats", json={"provider": "anthropic", "model": "chat"}
    )
    assert r.status_code == 503


async def test_no_providers_stream_returns_503(client, monkeypatch):
    import backend.config as cfg

    # create the chat while keys are still available
    r = await client.post("/api/chats", json={"provider": "openai", "model": "chat"})
    assert r.status_code == 201
    chat_id = r.json()["id"]

    # now remove the key — continuing the chat must fail before the stream starts
    monkeypatch.setattr(cfg.settings, "openai_api_key", None)

    r = await client.post(f"/api/chats/{chat_id}/messages", json={"content": "hello"})
    assert r.status_code == 503
    assert "OpenAI" in r.json()["detail"]


# ---- configured models missing from the provider account ----


async def test_warning_when_a_tier_model_is_not_in_the_account(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    _configure(monkeypatch, openai=False, anthropic=True)
    monkeypatch.setattr(cfg.settings, "anthropic_model_thinking", "claude-opus-99")
    with _live(anthropic_ids={"claude-haiku-5-5", "claude-sonnet-5-5"}), patch.object(reg.logger, "warning") as mock_warn:
        await reg.refresh()

    assert "claude-opus-99" in str(mock_warn.call_args_list)


async def test_image_model_warning_when_not_in_model_list(monkeypatch):
    import backend.config as cfg
    import backend.model_registry as reg

    _configure(monkeypatch, openai=True, anthropic=False)
    live = _live_ids("openai")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-99")
    with _live(openai_ids=live), patch.object(reg.logger, "warning") as mock_warn:
        await reg.refresh()

    assert "gpt-image-99" in str(mock_warn.call_args_list)


async def test_no_warning_when_every_configured_model_is_available(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=True, anthropic=True)
    with _live(), patch.object(reg.logger, "warning") as mock_warn:
        await reg.refresh()

    assert not mock_warn.called


async def test_no_warning_when_the_listing_fails(monkeypatch):
    """An unreachable model listing says nothing about what the account has."""
    import backend.model_registry as reg

    _configure(monkeypatch, openai=True, anthropic=True)
    with _live(openai_ids=set(), anthropic_ids=set()), patch.object(reg.logger, "warning") as mock_warn:
        await reg.refresh()

    assert not mock_warn.called


async def test_no_image_model_warning_when_openai_unconfigured(monkeypatch):
    import backend.model_registry as reg

    _configure(monkeypatch, openai=False, anthropic=False)
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
