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
    # real models behind each tier; task runs background work only, chat/thinking are offered to users
    openai_model_task: str = "gpt-6-luna"
    openai_model_chat: str = "gpt-6.1-sol"
    openai_model_thinking: str = "gpt-6-astra"
    anthropic_model_task: str = "claude-haiku-5-5"
    anthropic_model_chat: str = "claude-sonnet-5-5"
    anthropic_model_thinking: str = "claude-opus-5-5"
    # space-separated Ollama model specs; e.g. "Label@llama3 mistral"; empty = show all
    ollama_models: str = ""
    # image generation model (OpenAI)
    image_model: str = "gpt-image-2.5-flare"
    # write user/chatId/content to data/audit.log when enabled
    audit_log: bool = False
    # allow users to switch models on existing chats
    allow_switching_models: bool = True
    # mark chats as deleted instead of removing them from the database
    soft_delete: bool = False
    # profile name that has admin privileges (impersonate); empty = disabled
    admin: str = ""
    # shared secret a trusted remote system presents to /api/remote/*; empty = the whole surface is off
    remote_control_shared_secret: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
