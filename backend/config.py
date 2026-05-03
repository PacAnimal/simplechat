
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    database_url: str = "sqlite+aiosqlite:///./data/simplechat.db"
    uploads_dir: str = "./uploads"
    generated_dir: str = "./generated"
    stub_providers: bool = False
    allow_reset: bool = False
    reset_secret: str | None = None
    jwt_secret: str = "simplechat-dev-secret-change-in-production"
    # profile creation policy: "local" (RFC-1918 + loopback), "any", or "none"
    create: Literal["local", "any", "none"] = "local"
    # trust X-Forwarded-For / X-Forwarded-Proto from a local reverse proxy
    incoming_http_proxy: bool = False

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
