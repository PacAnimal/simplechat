from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    database_url: str = "sqlite+aiosqlite:///./data/simplechat.db"
    uploads_dir: str = "./uploads"
    generated_dir: str = "./generated"
    stub_providers: bool = False
    allow_reset: bool = False
    reset_secret: Optional[str] = None

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
