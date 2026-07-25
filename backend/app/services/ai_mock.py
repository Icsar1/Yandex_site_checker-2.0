from __future__ import annotations

from app.services.ai import compute_forecast_aggregates
from app.services.allocation import AllocationConfig, METHODOLOGY_VERSION


async def generate_search_masks_mock(niche: str, max_masks: int = 8) -> list[str]:
    if not niche or not niche.strip():
        return []
    words = [w.lower() for w in niche.strip().split() if len(w) > 2]
    masks: list[str] = []
    if words:
        masks.append(" ".join(words[:2]))
    if len(words) > 2:
        masks.append(" ".join(words[1:3]))
    if len(words) > 3:
        masks.append(" ".join(words[2:4]))
    masks.append(words[0] if words else niche.lower())
    seen: set[str] = set()
    result: list[str] = []
    for m in masks:
        if m and m not in seen:
            seen.add(m)
            result.append(m)
        if len(result) >= max_masks:
            break
    return result or [niche.lower()]


async def generate_report_mock(
    niche: str,
    region: str,
    keywords: list[dict],
    forecast: list[dict],
    geo_tokens: set[str] | None = None,
    config: AllocationConfig | None = None,
) -> dict:
    aggregates = compute_forecast_aggregates(forecast, keywords, niche, geo_tokens, config)
    report = {
        "summary": (
            f"Для ниши «{niche}» в регионе «{region}» подобрано "
            f"{aggregates['n_keywords']} ключевых фраз. Стартовый бюджет "
            f"составляет {aggregates['total_spending']:.0f} руб. при ожидаемом "
            f"объёме {aggregates['total_impressions']} показов.\n\n"
            "Бюджет распределён по кластерам: центр тяжести (самые узкие кластеры) "
            "получает приоритет; голый базис ограничен до 10% бюджета."
        ),
        "groups": _build_mock_groups(niche, aggregates),
        "conclusions": [
            (
                f"Медиаплан охватывает {aggregates['n_keywords']} ключевых фраз "
                f"в регионе «{region}»."
            ),
            (
                f"Стартовый бюджет: {aggregates['total_spending']:.0f} руб."
            ),
            (
                f"Ожидаемые клики: {aggregates['total_clicks']:.0f}, средний CPC: "
                f"{aggregates['avg_cpc']} руб., средний CTR: "
                f"{aggregates['avg_ctr']}%."
            ),
            *([w for w in aggregates.get("warnings", [])]),
        ],
        "recommendations": [
            "Запускать кампанию с разделением ключевых фраз по смысловым группам.",
            "Начать с кластеров высокого приоритета и отдельно контролировать ставки.",
            "После старта сравнить фактические CTR и CPC с прогнозом и скорректировать бюджет.",
        ],
        "disclaimer": (
            "Все числа являются прогнозом, фактические результаты рекламной кампании "
            "могут отличаться."
        ),
    }
    return {"methodology_version": METHODOLOGY_VERSION, "report": report, "aggregates": aggregates}


def _build_mock_groups(niche: str, aggregates: dict) -> list[dict]:
    clusters = aggregates.get("keyword_clusters") or []
    groups = [
        {
            "title": str(cluster["title"]),
            "description": (
                f"Группа объединяет запросы по направлению «{cluster['title']}» "
                "и подходит для отдельной рекламной группы."
            ),
            "sample_keywords": list(cluster["sample_keywords"])[:5],
        }
        for cluster in clusters[:3]
        if cluster.get("sample_keywords")
    ]

    fallback_keyword = _fallback_keyword(niche, aggregates)
    while len(groups) < 3:
        group_number = len(groups) + 1
        groups.append(
            {
                "title": f"Группа {group_number}",
                "description": (
                    "Резервная смысловая группа для расширения структуры кампании."
                ),
                "sample_keywords": [fallback_keyword],
            }
        )
    return groups


def _fallback_keyword(niche: str, aggregates: dict) -> str:
    top_keywords = aggregates.get("top_keywords") or []
    if top_keywords:
        return str(top_keywords[0]["phrase"])
    return niche or "ключевые фразы"
