from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://delno:delno@localhost:5433/delno"
    default_tenant_slug: str = "delno-demo"
    api_key: str | None = None

    knowledge_base_url: str = "http://127.0.0.1:8017"
    messenger_base_url: str = "http://127.0.0.1:8011"

    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()
