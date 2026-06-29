from __future__ import annotations

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT_ENV = str(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "dev"
    DOMAIN: str = "localhost"
    MOCK_YANDEX: bool = True
    LOG_LEVEL: str = "INFO"
    DATABASE_PATH: str = "data/tasks.db"
    REDIS_URL: str = "redis://redis:6379/0"
    CONCURRENCY: int = 3
    ARQ_MAX_JOBS: int = 10
    MAX_ATTEMPTS: int = 3
    RETRY_BASE_SECONDS: int = 10
    WORDSTAT_API_KEY: SecretStr = SecretStr("")
    WORDSTAT_FOLDER_ID: str = ""
    WORDSTAT_MIN_FREQ: int = 30
    MAX_KEYWORDS: int = 200
    DIRECT_FORECAST_URL: str = (
        "https://direct.yandex.ru/registered/main.pl?cmd=advancedForecast"
    )
    DIRECT_STORAGE_STATE: str = "data/storage_state.json"
    DIRECT_BATCH_SIZE: int = 100
    DIRECT_TIMEOUT_MS: int = 45000
    YANDEX_DIRECT_LOGIN: SecretStr = SecretStr("")
    YANDEX_DIRECT_PASSWORD: SecretStr = SecretStr("")
    PLAYWRIGHT_HEADLESS: bool = True
    YANDEX_GPT_BASE_URL: str = "https://llm.api.cloud.yandex.net/v1"
    YANDEX_GPT_API_KEY: SecretStr = SecretStr("")
    YANDEX_GPT_FOLDER_ID: str = ""
    YANDEX_GPT_MODEL: str = ""
    YANDEX_GPT_TEMPERATURE: float = 0.3
    YANDEX_GPT_TIMEOUT_S: int = 60
    ADMIN_PASSWORD: SecretStr = SecretStr("")
    SESSION_SECRET: SecretStr = SecretStr("")
    SESSION_TTL_SECONDS: int = 86400
    LOGIN_RATE_LIMIT: int = 5
    PUBLIC_RATE_LIMIT: int = 10
    PDF_TOKEN_TTL_SECONDS: int = 604800
    PDF_OUTPUT_DIR: str = "data/pdf"
    UPLOAD_MAX_BYTES: int = 5242880
    PROGRESS_TTL_SECONDS: int = 3600
    KPI_MEDIAN_SECONDS: int = 180


def get_settings() -> Settings:
    return Settings()
