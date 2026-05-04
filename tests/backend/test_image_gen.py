from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _make_fake_response(b64: str = "aGVsbG8=") -> MagicMock:
    img = MagicMock()
    img.b64_json = b64
    resp = MagicMock()
    resp.data = [img]
    return resp


async def test_gpt_image_model_omits_response_format(tmp_path, monkeypatch):
    """gpt-image-* models must not receive response_format — they always return b64."""
    import backend.config as cfg
    from backend.tools.image_gen import generate_image

    monkeypatch.setattr(cfg.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-2")
    monkeypatch.setattr(cfg.settings, "generated_dir", str(tmp_path))

    fake_generate = AsyncMock(return_value=_make_fake_response())
    with patch("backend.tools.image_gen.AsyncOpenAI") as mock_client_cls:
        mock_client_cls.return_value.images.generate = fake_generate
        await generate_image("a cow")

    call_kwargs = fake_generate.call_args.kwargs
    assert "response_format" not in call_kwargs
    assert call_kwargs["model"] == "gpt-image-2"


async def test_dalle_model_includes_response_format(tmp_path, monkeypatch):
    """dall-e-* models require response_format=b64_json."""
    import backend.config as cfg
    from backend.tools.image_gen import generate_image

    monkeypatch.setattr(cfg.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.settings, "image_model", "dall-e-3")
    monkeypatch.setattr(cfg.settings, "generated_dir", str(tmp_path))

    fake_generate = AsyncMock(return_value=_make_fake_response())
    with patch("backend.tools.image_gen.AsyncOpenAI") as mock_client_cls:
        mock_client_cls.return_value.images.generate = fake_generate
        await generate_image("a cow")

    call_kwargs = fake_generate.call_args.kwargs
    assert call_kwargs.get("response_format") == "b64_json"
    assert call_kwargs["model"] == "dall-e-3"


async def test_image_gen_ignores_allowed_models(tmp_path, monkeypatch):
    """IMAGE_MODEL must be used for generation even when ALLOWED_MODELS excludes it."""
    import backend.config as cfg
    from backend.tools.image_gen import generate_image

    # allowed_models excludes the image model entirely
    monkeypatch.setattr(cfg.settings, "allowed_models", "gpt-4o,gpt-4o-mini")
    monkeypatch.setattr(cfg.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.settings, "image_model", "gpt-image-2")
    monkeypatch.setattr(cfg.settings, "generated_dir", str(tmp_path))

    fake_generate = AsyncMock(return_value=_make_fake_response())
    with patch("backend.tools.image_gen.AsyncOpenAI") as mock_client_cls:
        mock_client_cls.return_value.images.generate = fake_generate
        result = await generate_image("a man in a pink suit")

    assert fake_generate.called
    assert fake_generate.call_args.kwargs["model"] == "gpt-image-2"
    assert fake_generate.call_args.kwargs["prompt"] == "a man in a pink suit"
    assert result["url"].startswith("/api/generated/")


async def test_image_gen_no_api_key_raises(monkeypatch):
    import backend.config as cfg
    from backend.tools.image_gen import generate_image

    monkeypatch.setattr(cfg.settings, "openai_api_key", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        await generate_image("a cow")
