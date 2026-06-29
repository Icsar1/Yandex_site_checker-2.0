from __future__ import annotations

import json
import re
from typing import Any

import httpx
from jsonschema import ValidationError, validate


REPORT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 paragraph executive summary",
        },
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "sample_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 5,
                    },
                },
                "required": ["title", "description", "sample_keywords"],
                "additionalProperties": False,
            },
            "minItems": 1,
            "maxItems": 6,
        },
        "conclusions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
        "recommendations": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 5,
        },
        "disclaimer": {"type": "string"},
    },
    "required": [
        "summary",
        "groups",
        "conclusions",
        "recommendations",
        "disclaimer",
    ],
    "additionalProperties": False,
}

MASKS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "masks": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 10,
        }
    },
    "required": ["masks"],
    "additionalProperties": False,
}

_SIGNIFICANT_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "а",
    "без",
    "в",
    "во",
    "для",
    "до",
    "за",
    "и",
    "из",
    "или",
    "к",
    "как",
    "ко",
    "на",
    "не",
    "о",
    "об",
    "от",
    "по",
    "под",
    "при",
    "с",
    "со",
    "у",
}


async def generate_search_masks(
    niche: str,
    base_url: str,
    api_key: str,
    folder_id: str,
    model: str | None = None,
    temperature: float = 0.4,
    timeout: int = 30,
    max_masks: int = 8,
) -> list[str]:
    if not niche or not niche.strip():
        return []
    selected_model = model or f"gpt://{folder_id}/yandexgpt/latest"
    system_prompt = (
        "Ты специалист по контекстной рекламе Яндекс Директ. "
        "Задача: придумать поисковые МАСКИ для сбора семантического ядра. "
        "Маска — короткое ключевое словосочетание (1-3 слова), которое затем "
        "будет расширено через Яндекс Wordstat до полного списка ключевых фраз. "
        "\n\n"
        "Собери маски РАЗНЫХ типов:\n"
        "1. Горячие — синоним ниши + купить/заказать/под ключ (если уместно)\n"
        "2. Ценовые — синоним + цена/стоимость/смета/расчёт\n"
        "3. Синонимы — все альтернативные названия услуги или товара\n"
        "4. Типы объектов — конкретные подвиды и разновидности\n"
        "5. Смежные формулировки — как аудитория описывает проблему/потребность\n"
        "\n"
        "Требования:\n"
        "- 1-3 слова каждая маска\n"
        "- строчными буквами, на русском языке\n"
        "- НЕ повторять дословно исходную фразу пользователя\n"
        "- маски должны быть достаточно широкими для Wordstat (не слишком узкими)\n"
        "- верни ТОЛЬКО JSON согласно схеме, без пояснений"
    )
    user_prompt = f"Ниша: {niche.strip()}"
    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "search_masks",
                "strict": True,
                "schema": MASKS_JSON_SCHEMA,
            },
        },
    }
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
        content = _extract_message_content(response.json())
        parsed = content if isinstance(content, dict) else json.loads(content)
        raw_masks = parsed.get("masks", [])
    except Exception:
        return []
    seen: set[str] = set()
    result: list[str] = []
    for m in raw_masks:
        m = str(m).strip().lower()
        if m and m not in seen:
            seen.add(m)
            result.append(m)
        if len(result) >= max_masks:
            break
    return result


def compute_forecast_aggregates(forecast: list[dict], keywords: list[dict]) -> dict:
    total_impressions = sum(_to_int(item.get("impressions")) for item in forecast)
    total_clicks = sum(_to_int(item.get("clicks")) for item in forecast)
    total_spending = round(
        sum(_to_float(item.get("spending")) for item in forecast),
        2,
    )
    avg_cpc = round(total_spending / total_clicks, 2) if total_clicks > 0 else 0
    avg_ctr = (
        round(total_clicks / total_impressions * 100, 2)
        if total_impressions > 0
        else 0
    )

    return {
        "n_keywords": len(keywords),
        "total_impressions": total_impressions,
        "total_clicks": total_clicks,
        "total_spending": total_spending,
        "avg_cpc": avg_cpc,
        "avg_ctr": avg_ctr,
        "top_keywords": _top_keywords_by_spending(forecast),
        "keyword_clusters": _cluster_keywords(keywords),
    }


def build_system_prompt() -> str:
    return (
        "You are an expert marketing analyst creating a media plan report in Russian.\n"
        "CRITICAL RULES:\n"
        "1. Use ONLY the numbers from the FACTS block below. Do NOT invent, "
        "calculate, or modify any numbers.\n"
        "2. Do NOT perform arithmetic. All sums, averages, and percentages are "
        "pre-calculated.\n"
        "3. Return ONLY valid JSON matching the provided schema.\n"
        "4. Write all text in Russian.\n"
        "5. The disclaimer field must state that numbers are forecasts and actual "
        "results may vary."
    )


def build_user_prompt(niche: str, region: str, aggregates: dict) -> str:
    return (
        "=== ФАКТЫ (используй ТОЛЬКО эти числа) ===\n"
        f"Ниша: {niche}\n"
        f"Регион: {region}\n"
        f"Количество ключевых фраз: {aggregates['n_keywords']}\n"
        f"Суммарные показы: {aggregates['total_impressions']}\n"
        f"Суммарные клики: {aggregates['total_clicks']}\n"
        f"Суммарный бюджет: {aggregates['total_spending']} руб.\n"
        f"Средний CPC: {aggregates['avg_cpc']} руб.\n"
        f"Средний CTR: {aggregates['avg_ctr']}%\n"
        "\n"
        "Топ-10 ключей по бюджету:\n"
        f"{_format_top_keywords(aggregates.get('top_keywords', []))}\n"
        "\n"
        "Кластеры ключей:\n"
        f"{_format_keyword_clusters(aggregates.get('keyword_clusters', []))}\n"
        "\n"
        "=== ЗАДАЧА ===\n"
        "На основе ТОЛЬКО этих фактов создай JSON-отчёт по схеме:\n"
        "- summary: обзор ниши, объём спроса, бюджет\n"
        "- groups: 3-6 смысловых групп ключевых слов с описанием и примерами\n"
        "- conclusions: 2-5 выводов\n"
        "- recommendations: 2-5 рекомендаций по запуску рекламы\n"
        "- disclaimer: стандартный дисклеймер о прогнозном характере данных"
    )


async def generate_report(
    niche: str,
    region: str,
    keywords: list[dict],
    forecast: list[dict],
    base_url: str,
    api_key: str,
    folder_id: str,
    model: str | None = None,
    temperature: float = 0.3,
    timeout: int = 60,
) -> dict:
    aggregates = compute_forecast_aggregates(forecast, keywords)
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(niche, region, aggregates)
    selected_model = model or f"gpt://{folder_id}/yandexgpt/latest"

    payload = {
        "model": selected_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "mediaplan_report",
                "strict": True,
                "schema": REPORT_JSON_SCHEMA,
            },
        },
    }

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            "YandexGPT API request failed with status "
            f"{exc.response.status_code}: {exc.response.text}"
        ) from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"YandexGPT API request failed: {exc}") from exc

    content = _extract_message_content(response.json())
    parsed_report = _parse_report_content(content)
    _validate_report(parsed_report)
    return {"report": parsed_report, "aggregates": aggregates}


def _top_keywords_by_spending(forecast: list[dict]) -> list[dict]:
    top_items = sorted(
        forecast,
        key=lambda item: _to_float(item.get("spending")),
        reverse=True,
    )[:10]
    return [
        {
            "phrase": str(item.get("phrase") or ""),
            "spending": round(_to_float(item.get("spending")), 2),
        }
        for item in top_items
    ]


def _cluster_keywords(keywords: list[dict]) -> list[dict]:
    buckets: dict[str, list[str]] = {}

    for keyword in keywords:
        phrase = str(keyword.get("phrase") or "").strip()
        if not phrase:
            continue
        title = _first_significant_word(phrase)
        buckets.setdefault(title, [])
        if len(buckets[title]) < 5:
            buckets[title].append(phrase)

    sorted_clusters = sorted(
        buckets.items(),
        key=lambda item: (-len(item[1]), item[0]),
    )[:6]
    return [
        {
            "title": title.capitalize(),
            "sample_keywords": samples,
        }
        for title, samples in sorted_clusters
    ]


def _first_significant_word(phrase: str) -> str:
    words = re.findall(r"[0-9A-Za-zА-Яа-яЁё]+", phrase.lower().replace("ё", "е"))
    if not words:
        return "другое"
    for word in words:
        if word not in _SIGNIFICANT_STOP_WORDS and len(word) > 1:
            return word
    return words[0]


def _format_top_keywords(top_keywords: list[dict]) -> str:
    if not top_keywords:
        return "- нет данных"
    return "\n".join(
        f"{index}. {item['phrase']} - {item['spending']} руб."
        for index, item in enumerate(top_keywords, start=1)
    )


def _format_keyword_clusters(keyword_clusters: list[dict]) -> str:
    if not keyword_clusters:
        return "- нет данных"
    return "\n".join(
        f"- {cluster['title']}: {', '.join(cluster['sample_keywords'])}"
        for cluster in keyword_clusters
    )


def _extract_message_content(response_data: dict) -> str | dict:
    try:
        return response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            "YandexGPT API response does not contain choices[0].message.content"
        ) from exc


def _parse_report_content(content: str | dict) -> dict:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise RuntimeError("YandexGPT API returned unsupported report content type")

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("YandexGPT API returned invalid JSON report") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("YandexGPT API returned JSON report that is not an object")
    return parsed


def _validate_report(report: dict) -> None:
    try:
        validate(instance=report, schema=REPORT_JSON_SCHEMA)
    except ValidationError as exc:
        raise RuntimeError(
            "YandexGPT API returned report that does not match schema: "
            f"{exc.message}"
        ) from exc


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
