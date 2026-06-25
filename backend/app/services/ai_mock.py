from __future__ import annotations

from app.services.ai import compute_forecast_aggregates


async def generate_report_mock(
    niche: str,
    region: str,
    keywords: list[dict],
    forecast: list[dict],
) -> dict:
    aggregates = compute_forecast_aggregates(forecast, keywords)
    report = {
        "summary": (
            f"Для ниши «{niche}» в регионе «{region}» подобрано "
            f"{aggregates['n_keywords']} ключевых фраз. Прогнозный бюджет "
            f"составляет {aggregates['total_spending']} руб. при ожидаемом "
            f"объёме {aggregates['total_impressions']} показов.\n\n"
            "Отчёт сформирован на основе рассчитанных прогнозных данных: "
            "числа не пересчитываются AI-модулем и используются только в готовом виде."
        ),
        "groups": _build_mock_groups(niche, aggregates),
        "conclusions": [
            (
                f"Прогноз охватывает {aggregates['n_keywords']} ключевых фраз "
                f"в регионе «{region}»."
            ),
            (
                f"Суммарный прогнозный бюджет составляет "
                f"{aggregates['total_spending']} руб."
            ),
            (
                f"Ожидаемые клики: {aggregates['total_clicks']}, средний CPC: "
                f"{aggregates['avg_cpc']} руб., средний CTR: "
                f"{aggregates['avg_ctr']}%."
            ),
        ],
        "recommendations": [
            "Запускать кампанию с разделением ключевых фраз по смысловым группам.",
            "Начать с ключей с наибольшим прогнозным бюджетом и отдельно контролировать ставки.",
            "После старта сравнить фактические CTR и CPC с прогнозом и скорректировать бюджет.",
        ],
        "disclaimer": (
            "Все числа являются прогнозом, фактические результаты рекламной кампании "
            "могут отличаться."
        ),
    }
    return {"report": report, "aggregates": aggregates}


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
