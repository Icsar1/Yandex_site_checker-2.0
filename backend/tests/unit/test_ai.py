from __future__ import annotations

import json

import httpx
import pytest
from jsonschema import Draft7Validator, validate

from app.services import ai as ai_module
from app.services.ai import (
    REPORT_JSON_SCHEMA,
    build_system_prompt,
    build_user_prompt,
    compute_forecast_aggregates,
    generate_search_masks,
)


def _patch_masks_client(
    monkeypatch: pytest.MonkeyPatch,
    content: str | dict | None = None,
    exc: Exception | None = None,
) -> None:
    class StubAsyncClient:
        def __init__(self, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "StubAsyncClient":
            return self

        async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        async def post(
            self,
            url: str,
            headers: dict[str, str],
            json: dict,
        ) -> httpx.Response:
            if exc is not None:
                raise exc
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(ai_module.httpx, "AsyncClient", StubAsyncClient)


def test_compute_forecast_aggregates_correct_sums() -> None:
    keywords = [
        {"phrase": "купить диван", "freq": 100, "score": 0.9},
        {"phrase": "диван цена", "freq": 80, "score": 0.8},
    ]
    forecast = [
        {"phrase": "купить диван", "impressions": 1000, "clicks": 50,
         "spending": 500.0, "avg_cpc": 10.0, "ctr": 5.0},
        {"phrase": "диван цена", "impressions": 500, "clicks": 25,
         "spending": 250.55, "avg_cpc": 10.0, "ctr": 5.0},
    ]

    result = compute_forecast_aggregates(forecast, keywords)

    assert result["n_keywords"] == 2
    # total_spending = fixed budget (120000) regardless of Yandex forecast sum
    assert result["total_spending"] == 120000.0
    # clusters and warnings are present
    assert "clusters" in result
    assert "warnings" in result
    # top_keywords is sorted by allocated_budget desc
    assert isinstance(result["top_keywords"], list)


@pytest.mark.asyncio
async def test_generate_search_masks_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_masks_client(
        monkeypatch,
        json.dumps({"masks": ["проект дома", "коттедж проект"]}),
    )

    result = await generate_search_masks(
        "Архитектурное проектирование частных домов",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result == ["проект дома", "коттедж проект"]


@pytest.mark.asyncio
async def test_generate_search_masks_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "https://example.test/chat/completions")
    _patch_masks_client(monkeypatch, exc=httpx.RequestError("boom", request=request))

    result = await generate_search_masks(
        "dentistry",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result == []


@pytest.mark.asyncio
async def test_generate_search_masks_empty_niche() -> None:
    result = await generate_search_masks(
        "   ",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result == []


@pytest.mark.asyncio
async def test_generate_search_masks_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_masks_client(
        monkeypatch,
        {"masks": [" Проект дома ", "проект дома", "коттедж"]},
    )

    result = await generate_search_masks(
        "architecture",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result == ["проект дома", "коттедж"]


@pytest.mark.asyncio
async def test_generate_search_masks_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_masks_client(
        monkeypatch,
        json.dumps({"masks": [f"mask {index}" for index in range(10)]}),
    )

    result = await generate_search_masks(
        "architecture",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
        max_masks=8,
    )

    assert result == [f"mask {index}" for index in range(8)]


def test_compute_forecast_aggregates_empty_forecast() -> None:
    result = compute_forecast_aggregates([], [])

    assert result["n_keywords"] == 0
    assert result["total_impressions"] == 0
    assert result["total_clicks"] == 0
    # With no keywords, total_spending = fixed budget (always present in config)
    assert result["total_spending"] == 120000.0
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
    assert "750.55 руб." in prompt
    assert "купить диван" in prompt


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
