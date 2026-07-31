from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str
    openai_research_model: str = "gpt-4o"
    openai_extraction_model: str = "gpt-4o"

    database_url: str = (
        "postgresql+psycopg://halo:halo@localhost:5432/halo_leads"
    )

    app_env: str = "development"
    max_research_sources: int = 20
    research_search_context_size: str = "large"
    max_research_deep_dives: int = 3
    
    smtp_host: str = "smtp.office365.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    sender_name: str = "Munish Kanwar"
    sender_email: str = ""
    calendar_link: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
