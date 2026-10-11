from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _anthropic_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    return resp


def _openai_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


@pytest.fixture
def cloud_keys(monkeypatch):
    import backend.config as cfg

    monkeypatch.setattr(cfg.settings, "stub_providers", False)
    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "anthropic-key")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "openai-key")
    monkeypatch.setattr(cfg.settings, "ollama_api_url", "http://ollama.local:11434")


async def test_anthropic_chats_are_titled_by_task_model(cloud_keys):
    from backend.api.stream import _generate_chat_title
    from backend.schemas import tier_model

    fake_create = AsyncMock(return_value=_anthropic_response("Bread Baking Basics"))
    with patch("anthropic.AsyncAnthropic") as mock_cls, patch("openai.AsyncOpenAI") as mock_openai:
        mock_cls.return_value.messages.create = fake_create
        title = await _generate_chat_title("How do I bake bread?", "Mix flour...", "anthropic", "thinking")

    assert title == "Bread Baking Basics"
    assert fake_create.call_args.kwargs["model"] == tier_model("anthropic", "task")
    mock_openai.assert_not_called()


async def test_openai_chats_are_titled_by_openai_task_model_without_anthropic_key(cloud_keys, monkeypatch):
    import backend.config as cfg
    from backend.api.stream import _generate_chat_title
    from backend.schemas import tier_model

    monkeypatch.setattr(cfg.settings, "anthropic_api_key", "")
    fake_create = AsyncMock(return_value=_openai_response("Bread Baking Basics"))
    with patch("anthropic.AsyncAnthropic") as mock_anthropic, patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = fake_create
        title = await _generate_chat_title("How do I bake bread?", "Mix flour...", "openai", "thinking")

    assert title == "Bread Baking Basics"
    assert fake_create.call_args.kwargs["model"] == tier_model("openai", "task")
    mock_anthropic.assert_not_called()


async def test_ollama_chats_are_titled_locally_by_selected_model(cloud_keys):
    from backend.api.stream import _generate_chat_title

    fake_create = AsyncMock(return_value=_openai_response("Local Title"))
    with patch("anthropic.AsyncAnthropic") as mock_anthropic, patch("openai.AsyncOpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create = fake_create
        title = await _generate_chat_title("hi", "hello", "ollama", "llama3")

    assert title == "Local Title"
    assert fake_create.call_args.kwargs["model"] == "llama3"
    assert mock_cls.call_args.kwargs["base_url"] == "http://ollama.local:11434/v1"
    mock_anthropic.assert_not_called()


async def test_ollama_chats_never_fall_back_to_cloud_when_ollama_unset(cloud_keys, monkeypatch):
    import backend.config as cfg
    from backend.api.stream import _generate_chat_title

    monkeypatch.setattr(cfg.settings, "ollama_api_url", "")
    with patch("anthropic.AsyncAnthropic") as mock_anthropic, patch("openai.AsyncOpenAI") as mock_openai:
        title = await _generate_chat_title("Tell me a joke", "...", "ollama", "llama3")

    assert title == "Tell me a joke"
    mock_anthropic.assert_not_called()
    mock_openai.assert_not_called()
