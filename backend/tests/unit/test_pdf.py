from __future__ import annotations

from pathlib import Path

import pytest

from app.services.pdf import TEMPLATE_NAME, get_template_environment
from app.services.pdf_mock import render_pdf_mock


@pytest.mark.asyncio
async def test_render_pdf_mock_creates_file(tmp_path: Path) -> None:
    output_path = tmp_path / "report.pdf"

    await render_pdf_mock(
        "мебель",
        "Москва",
        _sample_report(),
        _sample_aggregates(),
        str(output_path),
    )

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert output_path.read_bytes().startswith(b"%PDF")


@pytest.mark.asyncio
async def test_render_pdf_mock_returns_path(tmp_path: Path) -> None:
    output_path = tmp_path / "report.pdf"

    result = await render_pdf_mock(
        "мебель",
        "Москва",
        _sample_report(),
        _sample_aggregates(),
        str(output_path),
    )

    assert result == str(output_path)


def test_jinja2_template_renders_html() -> None:
    html = _render_template(
        niche="мебель",
        region="Москва",
        report=_sample_report(),
        aggregates=_sample_aggregates(),
    )

    assert "<html" in html
    assert "charset" in html
    assert "utf-8" in html
    assert "мебель" in html
    assert "Москва" in html
    assert "12 345" in html
    assert "report" in html
    assert "stats" in html
    assert "scenario-grid" in html
    assert "Ограничения прогноза" in html


def test_jinja2_template_renders_all_12_blocks() -> None:
    html = _render_template(
        niche="мебель",
        region="Москва",
        report=_sample_report(),
        aggregates=_sample_aggregates(),
    )

    for marker in (
        "running-header",
        "running-footer",
        "ms-h6",
        "scenario-grid",
        "table",
        "cards",
        "card-kicker",
        "tag-neutral",
        "budget-layout",
        "donut",
        "Ограничения прогноза",
    ):
        assert marker in html
    assert "@page" in html


def test_jinja2_template_numbers_from_aggregates() -> None:
    aggregates = _sample_aggregates() | {"total_spending": 150000}

    html = _render_template(
        niche="мебель",
        region="Москва",
        report=_sample_report(),
        aggregates=aggregates,
    )

    assert "150" in html


def test_jinja2_template_cyrillic() -> None:
    niche = "ремонт квартир"

    html = _render_template(
        niche=niche,
        region="Санкт-Петербург",
        report=_sample_report(),
        aggregates=_sample_aggregates(),
    )

    assert niche in html


def _render_template(
    niche: str,
    region: str,
    report: dict,
    aggregates: dict,
) -> str:
    template = get_template_environment().get_template(TEMPLATE_NAME)
    return template.render(
        niche=niche,
        region=region,
        report=report,
        aggregates=aggregates,
        generated_at="2026-06-25T10:00:00",
    )


def _sample_report() -> dict:
    return {
        "summary": (
            "Спрос устойчивый, основной объем приходится на коммерческие запросы.\n\n"
            "Прогноз подходит для стартового медиаплана."
        ),
        "groups": [
            {
                "title": "Диваны",
                "description": "Запросы по покупке диванов и сравнению моделей.",
                "sample_keywords": ["купить диван", "диван цена"],
            },
            {
                "title": "Шкафы",
                "description": "Запросы с выраженным товарным интересом.",
                "sample_keywords": ["заказать шкаф", "шкаф купе"],
            },
        ],
        "conclusions": [
            "Есть выраженный спрос в регионе.",
            "Бюджет концентрируется в верхних коммерческих кластерах.",
        ],
        "recommendations": [
            "Разделить кампании по группам фраз.",
            "Начать с кластеров высокого приоритета.",
        ],
        "disclaimer": (
            "Все числа являются прогнозом, фактические результаты рекламной "
            "кампании могут отличаться."
        ),
    }


def _sample_aggregates() -> dict:
    return {
        "n_keywords": 4,
        "total_impressions": 12345,
        "total_clicks": 678,
        "total_spending": 150000,
        "avg_cpc": 221.24,
        "avg_ctr": 5.49,
        "top_keywords": [
            {
                "phrase": "купить диван",
                "impressions": 6000,
                "clicks": 300,
                "ctr": 5.0,
                "cpc": 300,
            },
            {
                "phrase": "диван цена",
                "impressions": 4500,
                "clicks": 250,
                "ctr": 5.56,
                "cpc": 240,
            },
        ],
        "keyword_clusters": [],
    }
