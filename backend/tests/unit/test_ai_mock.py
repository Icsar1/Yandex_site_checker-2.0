from __future__ import annotations

import pytest

from app.services.ai_mock import generate_report_mock


@pytest.mark.asyncio
async def test_mock_generate_report_returns_valid_structure() -> None:
    result = await generate_report_mock(
        "мебель",
        "Москва",
        _keywords(),
        _forecast(),
    )

    assert set(result) == {"report", "aggregates"}
    assert isinstance(result["report"], dict)
    assert isinstance(result["aggregates"], dict)


@pytest.mark.asyncio
async def test_mock_report_has_required_fields() -> None:
    result = await generate_report_mock(
        "мебель",
        "Москва",
        _keywords(),
        _forecast(),
    )

    assert set(result["report"]) == {
        "summary",
        "groups",
        "conclusions",
        "recommendations",
        "disclaimer",
    }


@pytest.mark.asyncio
async def test_mock_report_uses_real_aggregates() -> None:
    result = await generate_report_mock(
        "мебель",
        "Москва",
        _keywords(),
        _forecast(),
    )

    assert result["aggregates"]["total_spending"] == 600.0
    assert "600.0 руб." in result["report"]["summary"]


@pytest.mark.asyncio
async def test_mock_report_groups_have_keywords() -> None:
    result = await generate_report_mock(
        "мебель",
        "Москва",
        _keywords(),
        _forecast(),
    )

    for group in result["report"]["groups"]:
        assert group["sample_keywords"]
        assert all(isinstance(keyword, str) for keyword in group["sample_keywords"])


def _keywords() -> list[dict]:
    return [
        {"phrase": "купить диван", "freq": 100, "score": 0.9},
        {"phrase": "диван цена", "freq": 90, "score": 0.8},
        {"phrase": "заказать шкаф", "freq": 80, "score": 0.7},
        {"phrase": "стол обеденный", "freq": 70, "score": 0.6},
    ]


def _forecast() -> list[dict]:
    return [
        {"phrase": "купить диван", "impressions": 1000, "clicks": 50, "spending": 300.0},
        {"phrase": "диван цена", "impressions": 800, "clicks": 40, "spending": 200.0},
        {"phrase": "заказать шкаф", "impressions": 500, "clicks": 20, "spending": 100.0},
    ]
