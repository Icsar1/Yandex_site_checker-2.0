from __future__ import annotations

import json
import re
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from app.services.allocation import AllocationConfig, METHODOLOGY_VERSION, allocate_budget
from app.services.compliance import detect_regulated_category
from app.services.keywords import _RU_STOPWORDS, normalize_phrase


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
    import re as _re
    # Strip: "1. ", "1) ", ". ", ".category. " or "category: " prefixes from AI output
    _junk = _re.compile(r"^(?:\.[^.]+\.|[\d]*[.):\-–]\s*|[^:]+:\s)")
    # YandexGPT sometimes crams several masks into one array item, separated
    # by commas/semicolons/newlines, wrapped in quotes. Split those apart first.
    _splitter = _re.compile(r"[,;\n]+")
    # Wordstat's phrase syntax rejects quotes, colons, brackets, pipes.
    _invalid_chars = _re.compile(r'["\'`:;\[\]{}()|]+')
    seen: set[str] = set()
    result: list[str] = []
    for raw in raw_masks:
        if len(result) >= max_masks:
            break
        for fragment in _splitter.split(str(raw)):
            m = _junk.sub("", fragment.strip()).strip()
            m = _invalid_chars.sub("", m)
            m = _re.sub(r"\s+", " ", m).strip().lower()
            if not m or len(m.split()) > 4:
                continue
            if m not in seen:
                seen.add(m)
                result.append(m)
            if len(result) >= max_masks:
                break
    return result


def compute_forecast_aggregates(
    forecast: list[dict],
    keywords: list[dict],
    niche: str = "",
    geo_tokens: set[str] | None = None,
    config: AllocationConfig | None = None,
    forecast_period: str = "последние ~60 дней (данные Яндекс Wordstat/Forecast API)",
    seasonality_note: str = "сезонность не учтена в данном прогнозе",
) -> dict:
    cfg = config or AllocationConfig()
    alloc = allocate_budget(keywords, forecast, niche, geo_tokens or set(), cfg)

    top_keywords = alloc["top_phrases"]
    clusters = alloc["clusters"]
    regulated_category = detect_regulated_category(
        niche, [str(kw.get("phrase") or "") for kw in keywords]
    )

    keyword_clusters = [
        {
            "title": c["title"].capitalize(),
            "sample_keywords": [p["phrase"] for p in c["phrases"][:5]],
        }
        for c in clusters
        if c["phrases"]
    ][:6]

    return {
        "methodology_version": METHODOLOGY_VERSION,
        "n_keywords": len(keywords),
        "forecasted_keywords": alloc.get("forecasted_keywords", 0),
        "excluded_keywords": alloc.get("excluded_keywords", 0),
        "total_impressions": int(alloc["total_impressions"]),
        "total_clicks": alloc["total_clicks"],
        "total_spending": alloc["total_budget"],
        "recommended_budget": alloc.get("recommended_budget", alloc["total_budget"]),
        "avg_cpc": alloc["avg_cpc"],
        "avg_ctr": alloc["avg_ctr"],
        "clean_cpc": alloc.get("clean_cpc", {}),
        "full_demand": alloc.get("full_demand", {}),
        "intent_breakdown": alloc.get("intent_breakdown", {}),
        "budget_scenarios": alloc.get("budget_scenarios", []),
        "top_keywords": top_keywords,
        "keyword_clusters": keyword_clusters,
        "clusters": clusters,
        "warnings": alloc["warnings"],
        "forecast_period": forecast_period,
        "seasonality_note": seasonality_note,
        "regulated_category": regulated_category,
        "expected_conversion_rate": cfg.expected_conversion_rate,
        "cr_is_estimated": cfg.expected_conversion_rate is None,
        "cr_benchmark_low": cfg.cr_benchmark_low,
        "cr_benchmark_high": cfg.cr_benchmark_high,
        "campaign_type": alloc.get("campaign_type", cfg.campaign_type),
        "rsya_forecast": alloc.get("rsya_forecast", []),
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
        "results may vary. "
        "6. Treat recommended_budget as the starting budget, not as full market demand.\n"
        "7. NEVER state that a scenario budget covers \"100% of demand\" unless the FACTS "
        "block literally shows that percentage. If a scenario's budget exceeds the full "
        "demand figure, say so explicitly instead of rounding it to 100%.\n"
        "8. The disclaimer must cite the exact forecast error margin percent given in the "
        "FACTS block (e.g. \"фактические результаты могут отличаться на ±X%\"), not a vague "
        "phrase like \"may differ from actual results\".\n"
        "9. If the informational-intent share in the FACTS block is significant, explicitly "
        "mention in summary/conclusions that part of the core consists of symptom/diagnosis "
        "queries, not purchase-ready demand."
    )


def build_user_prompt(niche: str, region: str, aggregates: dict) -> str:
    warnings_block = ""
    if aggregates.get("warnings"):
        warnings_block = "\nПРЕДУПРЕЖДЕНИЯ:\n" + "\n".join(aggregates["warnings"]) + "\n"

    clusters_block = _format_clusters(aggregates.get("clusters", []))
    scenarios_block = _format_scenarios(aggregates.get("budget_scenarios", []))
    full_demand = aggregates.get("full_demand", {}) or {}
    clean_cpc = aggregates.get("clean_cpc", {}) or {}
    margin_pct = round(float(full_demand.get("forecast_error_margin", 0.3)) * 100.0)
    intent_block = _format_intent_breakdown(aggregates.get("intent_breakdown", {}))

    return (
        "=== ФАКТЫ (используй ТОЛЬКО эти числа) ===\n"
        f"Ниша: {niche}\n"
        f"Регион: {region}\n"
        f"Методика: v{aggregates.get('methodology_version', METHODOLOGY_VERSION)}\n"
        f"Собрано ключевых фраз: {aggregates['n_keywords']}\n"
        f"Фраз в прогнозе: {aggregates.get('forecasted_keywords', 0)}\n"
        f"Рекомендуемый стартовый бюджет: {aggregates.get('recommended_budget', aggregates.get('total_spending', 0))} руб.\n"
        f"Полный спрос по очищенным фразам: {full_demand.get('budget_max', 0)} руб.\n"
        f"Clean CPC: {clean_cpc.get('value', 0)} руб. ({clean_cpc.get('method', '')})\n"
        f"Прогнозные показы для старта: {aggregates['total_impressions']}\n"
        f"Прогнозные клики для старта: {aggregates['total_clicks']}\n"
        f"Средний CPC старта: {aggregates['avg_cpc']} руб.\n"
        f"Средний CTR старта: {aggregates['avg_ctr']}%\n"
        f"Погрешность прогноза: ±{margin_pct}% (диапазоны бюджета уже учитывают эту погрешность)\n"
        f"\nКлассификация по интенту (доля от собранного спроса):\n{intent_block}\n"
        f"\nСценарии бюджета:\n{scenarios_block}\n"
        f"{warnings_block}"
        "\n"
        "Топ-10 фраз по прогнозному спросу:\n"
        f"{_format_top_keywords(aggregates.get('top_keywords', []))}\n"
        "\n"
        "Структура кластеров кампании:\n"
        f"{clusters_block}\n"
        "\n"
        "=== ЗАДАЧА ===\n"
        "На основе ТОЛЬКО этих фактов создай JSON-отчёт по схеме. "
        "Не называй полный спрос рекомендуемым бюджетом и не увеличивай бюджет сверх сценариев.\n"
        "- summary: объясни рекомендуемый старт, полный спрос и почему они различаются\n"
        "- groups: 3-6 смысловых групп ключевых слов с описанием и примерами\n"
        "- conclusions: 2-5 выводов\n"
        "- recommendations: 2-5 рекомендаций по запуску рекламы\n"
        f"- disclaimer: дисклеймер о прогнозном характере данных с указанием точной погрешности ±{margin_pct}%"
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
    geo_tokens: set[str] | None = None,
    config: AllocationConfig | None = None,
    forecast_period: str = "последние ~60 дней (данные Яндекс Wordstat/Forecast API)",
    seasonality_note: str = "сезонность не учтена в данном прогнозе",
) -> dict:
    aggregates = compute_forecast_aggregates(
        forecast, keywords, niche, geo_tokens, config, forecast_period, seasonality_note
    )
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
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "report": parsed_report,
        "aggregates": aggregates,
    }


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
        return "\u043d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445"
    lines = []
    for index, item in enumerate(top_keywords, start=1):
        cog = " [\u0426\u0422]" if item.get("is_center_of_gravity") else ""
        priority = item.get("priority") or ""
        ctr_note = (
            f"CTR {item.get('ctr', 0):.1f}%"
            if item.get("ctr_significant")
            else "CTR \u043d\u0435\u0434\u043e\u0441\u0442\u043e\u0432\u0435\u0440\u0435\u043d (<30 \u043a\u043b\u0438\u043a\u043e\u0432)"
        )
        lines.append(
            f"{index}. {item['phrase']}{cog} - "
            f"{item.get('clicks', 0):.0f} \u043a\u043b\u0438\u043a\u043e\u0432, "
            f"CPC {item.get('cpc', 0):.0f} \u0440\u0443\u0431., {ctr_note}, "
            f"\u043f\u0440\u0438\u043e\u0440\u0438\u0442\u0435\u0442 {priority}"
        )
    return "\n".join(lines)


def _format_clusters(clusters: list[dict]) -> str:
    if not clusters:
        return "- нет данных"
    lines = []
    for c in clusters:
        cog = " ★ ЦЕНТР ТЯЖЕСТИ" if c.get("is_center_of_gravity") else ""
        minus = ", ".join(c.get("minus_words", [])[:5])
        minus_str = f"; минус-слова: {minus}" if minus else ""
        review = ", ".join(c.get("minus_words_review", [])[:5])
        review_str = f"; требуют ручной проверки (не применены): {review}" if review else ""
        lines.append(
            f"  [{c['type'].upper()}]{cog} «{c['title']}» — "
            f"{c['n_keys']} фраз, {c['allocated_budget']:.0f} руб. "
            f"({c['allocated_share']:.0%}){minus_str}{review_str}"
        )
    return "\n".join(lines)


def _format_scenarios(scenarios: list[dict]) -> str:
    if not scenarios:
        return "- нет данных"
    lines = []
    for item in scenarios:
        pct = item.get("pct_of_demand")
        if pct is None:
            demand_note = "доля от полного спроса неизвестна"
        elif item.get("exceeds_demand"):
            demand_note = f"бюджет ПРЕВЫШАЕТ полный спрос в {item.get('exceeds_demand_ratio', 0):.1f}x раза"
        else:
            demand_note = f"{pct:.0f}% от полного спроса"
        low = item.get("budget_low")
        high = item.get("budget_high")
        range_note = f", диапазон с учётом погрешности {low:.0f}-{high:.0f} руб." if low is not None and high is not None else ""
        if item.get("cr_is_estimated"):
            leads_note = (
                f", заявки (оценочно по отраслевым бенчмаркам): "
                f"{item.get('leads_low', 0):.0f}-{item.get('leads_high', 0):.0f}, "
                f"CPL {item.get('cpl_low', 0):.0f}-{item.get('cpl_high', 0):.0f} руб."
            )
        else:
            leads_note = (
                f", заявки: {item.get('leads', 0):.0f}, CPL {item.get('cpl', 0):.0f} руб."
            )
        lines.append(
            f"- {item.get('title', item.get('id', 'scenario'))}: "
            f"{item.get('budget', 0):.0f} руб.{range_note}, "
            f"{item.get('clicks', 0):.0f} кликов, "
            f"{demand_note}{leads_note}"
        )
    return "\n".join(lines)


_INTENT_CATEGORY_LABELS = {
    "commercial": "коммерческие (готовность купить)",
    "informational": "информационные (симптомы/диагностика/самолечение)",
    "mixed": "смешанные/неопределённые",
}


def _format_intent_breakdown(breakdown: dict) -> str:
    if not breakdown:
        return "- нет данных"
    lines = []
    for category, label in _INTENT_CATEGORY_LABELS.items():
        item = breakdown.get(category) or {}
        share = float(item.get("share", 0.0)) * 100.0
        lines.append(f"- {label}: {share:.0f}% спроса, {item.get('demand_rub', 0):.0f} руб.")
    return "\n".join(lines)


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
