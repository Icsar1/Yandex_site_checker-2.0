from __future__ import annotations

from jsonschema import Draft7Validator, validate

from app.services.ai import (
    REPORT_JSON_SCHEMA,
    build_system_prompt,
    build_user_prompt,
    compute_forecast_aggregates,
)


def test_compute_forecast_aggregates_correct_sums() -> None:
    keywords = [
        {"phrase": "купить диван", "freq": 100, "score": 0.9},
        {"phrase": "диван цена", "freq": 80, "score": 0.8},
    ]
    forecast = [
        {"phrase": "купить диван", "impressions": 1000, "clicks": 50, "spending": 500.0},
        {"phrase": "диван цена", "impressions": 500, "clicks": 25, "spending": 250.55},
    ]

    result = compute_forecast_aggregates(forecast, keywords)

    assert result["n_keywords"] == 2
    assert result["total_impressions"] == 1500
    assert result["total_clicks"] == 75
    assert result["total_spending"] == 750.55
    assert result["avg_cpc"] == 10.01
    assert result["avg_ctr"] == 5.0
    assert result["top_keywords"][0] == {"phrase": "купить диван", "spending": 500.0}


def test_compute_forecast_aggregates_empty_forecast() -> None:
    result = compute_forecast_aggregates([], [])

    assert result["n_keywords"] == 0
    assert result["total_impressions"] == 0
    assert result["total_clicks"] == 0
    assert result["total_spending"] == 0
    assert result["avg_cpc"] == 0
    assert result["avg_ctr"] == 0
    assert result["top_keywords"] == []
    assert result["keyword_clusters"] == []


def test_compute_forecast_aggregates_zero_clicks() -> None:
    result = compute_forecast_aggregates(
        [{"phrase": "купить диван", "impressions": 1000, "clicks": 0, "spending": 100}],
        [{"phrase": "купить диван", "freq": 100, "score": 0.9}],
    )

    assert result["avg_cpc"] == 0
    assert result["avg_ctr"] == 0.0


def test_build_system_prompt_contains_rules() -> None:
    prompt = build_system_prompt()

    assert "ONLY" in prompt
    assert "FACTS" in prompt
    assert "JSON" in prompt


def test_build_user_prompt_contains_facts() -> None:
    aggregates = {
        "n_keywords": 2,
        "total_impressions": 1500,
        "total_clicks": 75,
        "total_spending": 750.55,
        "avg_cpc": 10.01,
        "avg_ctr": 5.0,
        "top_keywords": [{"phrase": "купить диван", "spending": 500.0}],
        "keyword_clusters": [
            {"title": "Диван", "sample_keywords": ["купить диван", "диван цена"]},
        ],
    }

    prompt = build_user_prompt("мебель", "Москва", aggregates)

    assert "Ниша: мебель" in prompt
    assert "Регион: Москва" in prompt
    assert "Количество ключевых фраз: 2" in prompt
    assert "Суммарный бюджет: 750.55 руб." in prompt
    assert "1. купить диван - 500.0 руб." in prompt


def test_report_json_schema_valid() -> None:
    Draft7Validator.check_schema(REPORT_JSON_SCHEMA)
    sample_report = {
        "summary": "Краткий отчёт по прогнозу.",
        "groups": [
            {
                "title": "Диваны",
                "description": "Коммерческие запросы по диванам.",
                "sample_keywords": ["купить диван"],
            },
        ],
        "conclusions": ["Есть спрос.", "Нужен контроль ставок."],
        "recommendations": ["Разделить группы.", "Проверить ставки."],
        "disclaimer": "Числа являются прогнозом, фактические результаты могут отличаться.",
    }

    validate(instance=sample_report, schema=REPORT_JSON_SCHEMA)
