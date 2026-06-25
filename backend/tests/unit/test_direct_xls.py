from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.direct_xls import parse_forecast_xls


def _write_xlsx(path: Path, rows: list[list[object | None]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()


def test_parse_valid_xls(tmp_path: Path) -> None:
    path = tmp_path / "forecast.xlsx"
    _write_xlsx(
        path,
        [
            ["Advanced forecast"],
            [
                "Ключевая фраза",
                "Прогноз показов",
                "Прогноз кликов",
                "Прогноз расхода",
                "CTR",
                "Ср. цена клика",
                "CPM",
                "Ср. ставка",
            ],
            ["натяжные потолки", 1000, 50, 2500.5, 5, 50.01, 2500.5, 70],
        ],
    )

    result = parse_forecast_xls(path)

    assert result == [
        {
            "phrase": "натяжные потолки",
            "impressions": 1000,
            "clicks": 50,
            "spending": 2500.5,
            "ctr": 5,
            "avg_cpc": 50.01,
            "avg_cpm": 2500.5,
            "avg_bid": 70,
        }
    ]


def test_parse_xls_missing_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "forecast.xlsx"
    _write_xlsx(
        path,
        [
            ["Показы", "Клики", "Расход"],
            [1000, 50, 2500],
        ],
    )

    with pytest.raises(ValueError):
        parse_forecast_xls(path)


def test_parse_xls_numeric_strings(tmp_path: Path) -> None:
    path = tmp_path / "forecast.xlsx"
    _write_xlsx(
        path,
        [
            ["Фраза", "Показы", "Клики", "Расход", "CTR"],
            ["натяжные потолки", "1 234", "56", "1 234,56", "4,54%"],
        ],
    )

    result = parse_forecast_xls(path)

    assert result[0]["impressions"] == 1234
    assert result[0]["clicks"] == 56
    assert result[0]["spending"] == 1234.56
    assert result[0]["ctr"] == 4.54


def test_parse_xls_empty_rows_skipped(tmp_path: Path) -> None:
    path = tmp_path / "forecast.xlsx"
    _write_xlsx(
        path,
        [
            ["Фраза", "Показы", "Клики", "Расход"],
            [None, None, None, None],
            ["натяжные потолки", 1000, 50, 2500],
            ["", "", "", ""],
        ],
    )

    result = parse_forecast_xls(path)

    assert len(result) == 1
    assert result[0]["phrase"] == "натяжные потолки"
