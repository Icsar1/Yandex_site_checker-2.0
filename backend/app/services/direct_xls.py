from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


REQUIRED_FIELDS = {"phrase", "impressions", "clicks", "spending"}
NUMERIC_FIELDS = (
    "impressions",
    "clicks",
    "spending",
    "ctr",
    "avg_cpc",
    "avg_cpm",
    "avg_bid",
)

HEADER_ALIASES = {
    "phrase": (
        "фраза",
        "ключевая фраза",
    ),
    "impressions": (
        "показы",
        "прогноз показов",
    ),
    "clicks": (
        "клики",
        "прогноз кликов",
    ),
    "spending": (
        "расход",
        "прогноз расхода",
        "бюджет",
    ),
    "ctr": (
        "ctr",
    ),
    "avg_cpc": (
        "ср цена клика",
        "средняя цена клика",
        "цена клика",
        "cpc",
    ),
    "avg_cpm": (
        "cpm",
        "ср цена тысячи показов",
    ),
    "avg_bid": (
        "ср ставка",
        "средняя ставка",
        "ставка",
    ),
}


def parse_forecast_xls(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    try:
        workbook = load_workbook(
            BytesIO(path.read_bytes()),
            data_only=True,
            read_only=True,
        )
    except Exception as exc:
        raise ValueError("Invalid XLS/XLSX file") from exc

    try:
        sheet = workbook.active
        header_row_index, header_mapping = _find_header_row(sheet)
        missing = REQUIRED_FIELDS - set(header_mapping)
        if missing:
            missing_columns = ", ".join(sorted(missing))
            raise ValueError(f"Required XLS columns not found: {missing_columns}")

        rows: list[dict] = []
        for row in sheet.iter_rows(min_row=header_row_index + 1, values_only=True):
            if _is_empty_row(row):
                continue
            item = _parse_data_row(row, header_mapping)
            if item is not None:
                rows.append(item)
        return rows
    finally:
        workbook.close()


def _find_header_row(sheet: Any) -> tuple[int, dict[str, int]]:
    best_row_index = 0
    best_mapping: dict[str, int] = {}

    for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
        mapping = _map_headers(row)
        if not mapping:
            continue
        if len(mapping) > len(best_mapping):
            best_row_index = row_index
            best_mapping = mapping
        if REQUIRED_FIELDS.issubset(mapping):
            return row_index, mapping

    if not best_mapping:
        raise ValueError("XLS header row was not found")
    return best_row_index, best_mapping


def _map_headers(values: tuple[Any, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, value in enumerate(values):
        field = _field_for_header(value)
        if field is not None and field not in mapping:
            mapping[field] = index
    return mapping


def _field_for_header(value: Any) -> str | None:
    normalized = _normalize_header(value)
    if not normalized:
        return None

    for field, aliases in HEADER_ALIASES.items():
        if normalized in aliases:
            return field
    for field, aliases in HEADER_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return field
    return None


def _parse_data_row(row: tuple[Any, ...], mapping: dict[str, int]) -> dict | None:
    phrase_index = mapping["phrase"]
    phrase_value = row[phrase_index] if phrase_index < len(row) else None
    phrase = str(phrase_value or "").strip()
    if not phrase:
        return None

    item: dict[str, Any] = {"phrase": phrase}
    for field in NUMERIC_FIELDS:
        index = mapping.get(field)
        item[field] = _parse_number(row[index]) if index is not None and index < len(row) else None
    return item


def _is_empty_row(row: tuple[Any, ...]) -> bool:
    return all(value is None or str(value).strip() == "" for value in row)


def _normalize_header(value: Any) -> str:
    text = str(value or "").casefold().replace("ё", "е")
    cleaned = "".join(char if char.isalnum() else " " for char in text)
    return " ".join(cleaned.split())


def _parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value

    text = str(value).strip()
    if not text or text in {"-", "---"}:
        return None
    text = (
        text.replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace("%", "")
        .replace("₽", "")
    )
    text = "".join(char for char in text if char.isdigit() or char in ",.-+")
    if not text or text in {"-", "+", ".", ","}:
        return None

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number
