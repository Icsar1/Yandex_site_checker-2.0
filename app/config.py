from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Wordstat Media Planner"
    debug: bool = False

    wordstat_oauth_token: str = Field(default="")
    wordstat_api_key: str = Field(default="", min_length=0)  # legacy fallback name
    wordstat_base_url: AnyHttpUrl = "https://api.wordstat.yandex.net"
    wordstat_endpoint: str = "/json/v5/wordstat"
    wordstat_timeout_seconds: float = 10.0

    request_log_level: str = "INFO"

    direct_login: str = Field(default="")
    direct_password: str = Field(default="")
    direct_cookies_path: str = ".direct/cookies.json"
    direct_default_region: str = "Москва"
    direct_headless: bool = True
    direct_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
