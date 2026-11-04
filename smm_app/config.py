from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_extraction_model: str = "gpt-4o-mini"

    database_url: str = "sqlite:///./seemymind_leads.db"

    app_env: str = "development"
    port: int = 8001
    
    sender_name: str = "See My Mind Partnerships"
    sender_email: str = "hello@seemymind.co.uk"
    demo_link: str = "https://seemymind.co.uk/book-a-demo"
    video_link: str = "https://seemymind.co.uk/product.html"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
