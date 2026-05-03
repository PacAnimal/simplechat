
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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
