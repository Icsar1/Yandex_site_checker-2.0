from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Wordstat Media Planner"
    debug: bool = False

    wordstat_oauth_token: str = Field(default="")
    wordstat_api_key: str = Field(default="")  # legacy fallback name
    wordstat_base_url: AnyHttpUrl = "https://api.wordstat.yandex.net"
    wordstat_timeout_seconds: float = 10.0

    request_log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
