import secrets
from typing import Literal

from pydantic_settings import BaseSettings

# random default — replaced by the lifespan with a persistent key in production;
# ensures tests work without a lifespan without shipping a known insecure default
_DEFAULT_JWT_SECRET = secrets.token_hex(32)


class Settings(BaseSettings):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    ollama_api_url: str | None = None
    database_url: str = "sqlite+aiosqlite:///./data/simplechat.db"
    uploads_dir: str = "./uploads"
    generated_dir: str = "./generated"
    stub_providers: bool = False
    allow_reset: bool = False
    reset_secret: str | None = None
    jwt_secret: str = _DEFAULT_JWT_SECRET
    show_docs: bool = False
    # profile creation policy: "local" (RFC-1918 + loopback), "any", or "none"
    create: Literal["local", "any", "none"] = "local"
    # trust X-Forwarded-For / X-Forwarded-Proto from a local reverse proxy
    incoming_http_proxy: bool = False
    # minimum password length; 0 disables all password complexity requirements
    password_min_length: int = 8
    # system prompt injected at the start of every Ollama request; useful for overriding guard templates
    ollama_system_prompt: str = ""
    # space-separated model specs per provider; e.g. "Label@gpt-5.5 gpt-4o"; empty = show all
    openai_models: str = ""
    anthropic_models: str = ""
    ollama_models: str = ""
    # image generation model (OpenAI)
    image_model: str = "gpt-image-2"
    # write user/chatId/content to data/audit.log when enabled
    audit_log: bool = False
    # allow users to switch models on existing chats
    allow_switching_models: bool = True
    # mark chats as deleted instead of removing them from the database
    soft_delete: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
