from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    app_base_url: str = os.getenv("APP_BASE_URL", "https://example.com")
    report_ttl_hours: int = int(os.getenv("REPORT_TTL_HOURS", "72"))
    db_path: str = os.getenv("DB_PATH", "seo_reports.db")
    yandex_webmaster_token: str = os.getenv("YANDEX_WEBMASTER_TOKEN", "")
    yandex_direct_token: str = os.getenv("YANDEX_DIRECT_TOKEN", "")
    yandex_metrica_token: str = os.getenv("YANDEX_METRICA_TOKEN", "")
    seo_data_provider: str = os.getenv("SEO_DATA_PROVIDER", "mock")
    topvisor_api_key: str = os.getenv("TOPVISOR_API_KEY", "")


settings = Settings()
