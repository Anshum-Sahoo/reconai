from functools import lru_cache
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/reconai"

    # Authentication & Security (Backend only - never exposed to frontend)
    demo_access_password: str = "reconai_demo_secret_2026"
    jwt_secret: str = "reconai_demo_jwt_secret_key_32_characters_minimum!"
    session_token_ttl_hours: int = 8

    # AI Configuration (Optional)
    gemini_api_key: Optional[str] = None

    # Storage
    upload_dir: str = "uploads"

    # CORS
    cors_origins: Union[List[str], str] = ["http://localhost:3000"]

    # Environment
    environment: str = "development"
    log_level: str = "INFO"
    app_version: str = "1.2.1"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


@lru_cache()
def get_settings() -> Settings:
    return Settings()
