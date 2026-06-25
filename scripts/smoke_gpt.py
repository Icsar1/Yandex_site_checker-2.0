"""Smoke test for YandexGPT API with real credentials."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings
from app.services.ai import generate_report, REPORT_JSON_SCHEMA


FIXTURE_KEYWORDS = [
    {"phrase": "купить диван", "freq": 5000},
    {"phrase": "диван цена", "freq": 3000},
    {"phrase": "заказать шкаф", "freq": 2000},
]

FIXTURE_FORECAST = [
    {"phrase": "купить диван", "impressions": 6000, "clicks": 300, "spending": 90000, "ctr": 5.0, "avg_cpc": 300},
    {"phrase": "диван цена", "impressions": 4500, "clicks": 250, "spending": 60000, "ctr": 5.56, "avg_cpc": 240},
    {"phrase": "заказать шкаф", "impressions": 2000, "clicks": 100, "spending": 30000, "ctr": 5.0, "avg_cpc": 300},
]


async def main():
    settings = get_settings()
    api_key = settings.YANDEX_GPT_API_KEY.get_secret_value()
    folder_id = settings.YANDEX_GPT_FOLDER_ID
    base_url = settings.YANDEX_GPT_BASE_URL
    model = settings.YANDEX_GPT_MODEL or None
    
    if not api_key:
        print("ERROR: YANDEX_GPT_API_KEY is empty in .env")
        sys.exit(1)
    
    print(f"Base URL: {base_url}")
    print(f"Folder ID: {folder_id}")
    print(f"Model: {model or f'gpt://{folder_id}/yandexgpt/latest'}")
    print(f"API Key (first 8 chars): {api_key[:8]}...")
    
    print("\n--- generate_report('мебель', 'Москва') ---")
    try:
        result = await generate_report(
            niche="мебель",
            region="Москва",
            keywords=FIXTURE_KEYWORDS,
            forecast=FIXTURE_FORECAST,
            base_url=base_url,
            api_key=api_key,
            folder_id=folder_id,
            model=model,
            temperature=settings.YANDEX_GPT_TEMPERATURE,
            timeout=settings.YANDEX_GPT_TIMEOUT_S,
        )
        print("OK: report generated successfully")
        report = result.get("report", {})
        print(f"  Summary length: {len(report.get('summary', ''))} chars")
        print(f"  Groups: {len(report.get('groups', []))}")
        print(f"  Conclusions: {len(report.get('conclusions', []))}")
        print(f"  Recommendations: {len(report.get('recommendations', []))}")
        print(f"  Disclaimer: {'yes' if report.get('disclaimer') else 'no'}")
        aggregates = result.get("aggregates", {})
        print(f"  Aggregates: n_keywords={aggregates.get('n_keywords')}, "
              f"total_spending={aggregates.get('total_spending')}")
    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
