from __future__ import annotations

import json

import httpx
import pytest
from jsonschema import Draft7Validator, validate

from app.services import ai as ai_module
from app.services.allocation import AllocationConfig
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


@pytest.mark.asyncio
async def test_generate_search_masks_splits_crammed_quoted_phrases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crammed = (
        '"увеличение губ купить", \n"увеличение губ заказать", '
        '\n"увеличение губ под ключ", \n.ценовые.  \n"аугме'
    )
    _patch_masks_client(monkeypatch, json.dumps({"masks": [crammed]}))

    result = await generate_search_masks(
        "cosmetology",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result
    for mask in result:
        assert '"' not in mask
        assert "\n" not in mask
        assert ":" not in mask
        assert ";" not in mask
    assert "увеличение губ купить" in result
    assert "увеличение губ заказать" in result
    assert "увеличение губ под ключ" in result


@pytest.mark.asyncio
async def test_generate_search_masks_splits_crammed_category_phrases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crammed = (
        "ценовые: пластика интимная цена, стоимость интимной пластики, "
        "интимная пластика смета. синонимы: кор"
    )
    _patch_masks_client(monkeypatch, json.dumps({"masks": [crammed]}))

    result = await generate_search_masks(
        "cosmetology",
        base_url="https://example.test",
        api_key="key",
        folder_id="folder",
    )

    assert result
    assert len(result) > 1
    for mask in result:
        assert "," not in mask
        assert ":" not in mask
    assert "пластика интимная цена" in result
    assert "стоимость интимной пластики" in result


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
    assert result["methodology_version"] == 3
    assert result["total_spending"] == 1000.0
    assert len(result["budget_scenarios"]) == 4
    # clusters and warnings are present
    assert "clusters" in result
    assert "warnings" in result
    # top_keywords contains phrase demand metrics, not phrase budgets
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
    assert result["total_spending"] == 0.0
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


def test_compute_forecast_aggregates_default_forecast_period_and_seasonality() -> None:
    result = compute_forecast_aggregates([], [])

    assert result["forecast_period"]
    assert "сезонность" in result["seasonality_note"].lower()


def test_compute_forecast_aggregates_custom_forecast_period_and_seasonality() -> None:
    result = compute_forecast_aggregates(
        [], [],
        forecast_period="01.06.2026-31.07.2026",
        seasonality_note="учтён летний спад спроса",
    )

    assert result["forecast_period"] == "01.06.2026-31.07.2026"
    assert result["seasonality_note"] == "учтён летний спад спроса"


def test_compute_forecast_aggregates_flags_regulated_niche() -> None:
    result = compute_forecast_aggregates([], [], niche="интимная пластика")

    assert result["regulated_category"] is not None
    assert result["regulated_category"]["id"] == "medicine"
    assert result["regulated_category"]["required_documents"]


def test_compute_forecast_aggregates_no_category_for_neutral_niche() -> None:
    result = compute_forecast_aggregates([], [], niche="кухни на заказ")

    assert result["regulated_category"] is None


def test_compute_forecast_aggregates_estimates_leads_without_cr() -> None:
    result = compute_forecast_aggregates(
        [{"phrase": "купить диван", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0}],
        [{"phrase": "купить диван", "freq": 100, "score": 0.9, "priority": "high"}],
    )

    assert result["cr_is_estimated"] is True
    recommended = next(s for s in result["budget_scenarios"] if s["id"] == "recommended")
    assert recommended["leads_low"] is not None
    assert recommended["cpl_low"] is not None


def test_compute_forecast_aggregates_exact_leads_with_cr() -> None:
    cfg = AllocationConfig(expected_conversion_rate=0.05)
    result = compute_forecast_aggregates(
        [{"phrase": "купить диван", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0}],
        [{"phrase": "купить диван", "freq": 100, "score": 0.9, "priority": "high"}],
        config=cfg,
    )

    assert result["cr_is_estimated"] is False
    recommended = next(s for s in result["budget_scenarios"] if s["id"] == "recommended")
    assert recommended["leads"] == recommended["clicks"] * 0.05


def test_compute_forecast_aggregates_rsya_campaign_type_wires_rsya_forecast() -> None:
    cfg = AllocationConfig(campaign_type="rsya")
    result = compute_forecast_aggregates(
        [{"phrase": "купить диван", "impressions": 1000, "clicks": 100, "spending": 20000, "avg_cpc": 200, "ctr": 10.0}],
        [{"phrase": "купить диван", "freq": 100, "score": 0.9, "priority": "high"}],
        config=cfg,
    )

    assert result["campaign_type"] == "rsya"
    assert result["rsya_forecast"]


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
        "top_keywords": [{"phrase": "купить диван", "clicks": 50, "cpc": 10.0, "priority": "high"}],
        "keyword_clusters": [
            {"title": "Диван", "sample_keywords": ["купить диван", "диван цена"]},
        ],
    }

    prompt = build_user_prompt("мебель", "Москва", aggregates)

    assert "Ниша: мебель" in prompt
    assert "Регион: Москва" in prompt
    assert "v3" in prompt
    assert "2" in prompt
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
