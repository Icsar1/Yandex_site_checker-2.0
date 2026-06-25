from __future__ import annotations

import math
import re


COMMERCIAL_MARKERS = {
    "купить",
    "заказать",
    "цена",
    "стоимость",
    "недорого",
    "прайс",
    "расчет",
    "рассчитать",
    "калькулятор",
    "смета",
    "монтаж",
    "установка",
    "под ключ",
    "с доставкой",
    "оптом",
    "нанять",
    "подобрать",
}

_GENERIC_STEMS = {
    "купи", "заказ", "цен", "стоимост", "недорог", "прайс",
    "доставк", "оптом", "монтаж", "установ", "расчет", "рассчит",
    "калькулят", "смет", "наня", "подобра",
}

_RU_STOPWORDS = {
    "и", "в", "на", "с", "по", "для", "от", "из", "за", "к", "не",
    "или", "а", "но", "что", "как", "у", "до", "о", "при", "это",
    "то", "все", "так", "уже", "бы", "под", "без", "над", "про",
}

INFO_STOP_LIST = {
    "скачать",
    "бесплатно",
    "своими руками",
    "что такое",
    "отзывы",
    "видео",
    "фото",
    "работа",
    "вакансии",
    "реферат",
    "курсовая",
    "дипломная",
    "wikipedia",
    "wiki",
}


def parse_count_safe(value: str | int) -> int:
    if isinstance(value, int):
        return value

    cleaned = str(value).strip()
    if not cleaned or cleaned == "---":
        return 0

    cleaned = (
        cleaned.replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    if not cleaned:
        return 0

    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return 0


def normalize_phrase(phrase: str) -> str:
    normalized = phrase.lower().strip().replace("ё", "е")
    normalized = re.sub(r"[^\w\s-]|_", " ", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def is_garbage(phrase: str, stop_list: set[str] | None = None) -> bool:
    normalized = normalize_phrase(phrase)
    tokens = set(normalized.split())
    markers = INFO_STOP_LIST if stop_list is None else stop_list

    for marker in markers:
        normalized_marker = normalize_phrase(marker)
        if not normalized_marker:
            continue
        if " " in normalized_marker and normalized_marker in normalized:
            return True
        if " " not in normalized_marker and normalized_marker in tokens:
            return True
    return False


def score_keyword(
    phrase: str,
    freq: int,
    max_freq: int,
    geo_tokens: set[str] | None = None,
) -> float:
    normalized = normalize_phrase(phrase)
    tokens = set(normalized.split())
    freq_norm = math.log1p(freq) / math.log1p(max_freq) if max_freq > 0 else 0
    comm_hits = sum(
        1
        for marker in COMMERCIAL_MARKERS
        if _marker_matches(normalized, tokens, marker)
    )
    comm_score = min(comm_hits, 3) / 3

    normalized_geo_tokens = {
        normalize_phrase(token)
        for token in (geo_tokens or set())
        if normalize_phrase(token)
    }
    geo_bonus = 0.05 if normalized_geo_tokens and (tokens & normalized_geo_tokens) else 0
    return 0.60 * freq_norm + 0.35 * comm_score + geo_bonus


def extract_niche_stems(niche: str) -> set[str]:
    tokens = normalize_phrase(niche).split()
    stems: set[str] = set()
    for token in tokens:
        if token in _RU_STOPWORDS:
            continue
        if any(token.startswith(s) for s in _GENERIC_STEMS):
            continue
        if len(token) < 3:
            continue
        stem = token[:min(5, max(3, len(token) - 2))]
        stems.add(stem)
    return stems


def is_niche_relevant(phrase: str, niche_stems: set[str]) -> bool:
    if not niche_stems:
        return True
    tokens = normalize_phrase(phrase).split()
    matched = {stem for token in tokens for stem in niche_stems if token.startswith(stem)}
    required = min(2, len(niche_stems)) if len(niche_stems) >= 2 else 1
    return len(matched) >= required


def select_keywords(
    raw_keywords: list[dict],
    min_freq: int = 30,
    max_keywords: int = 200,
    stop_list: set[str] | None = None,
    geo_tokens: set[str] | None = None,
    niche: str | None = None,
) -> list[dict[str, float | int | str]]:
    niche_stems = extract_niche_stems(niche) if niche else set()
    deduped: dict[str, int] = {}

    for raw_keyword in raw_keywords:
        phrase = normalize_phrase(str(raw_keyword.get("phrase") or ""))
        freq = parse_count_safe(raw_keyword.get("freq") or 0)
        if not phrase or freq < min_freq or is_garbage(phrase, stop_list):
            continue
        if niche_stems and not is_niche_relevant(phrase, niche_stems):
            continue
        deduped[phrase] = max(freq, deduped.get(phrase, 0))

    if not deduped:
        return []

    max_freq = max(deduped.values())
    scored = [
        {
            "phrase": phrase,
            "freq": freq,
            "score": score_keyword(phrase, freq, max_freq, geo_tokens),
        }
        for phrase, freq in deduped.items()
    ]
    scored.sort(key=lambda item: (-float(item["score"]), -int(item["freq"]), str(item["phrase"])))
    return scored[:max_keywords]


def batch_keywords(keywords: list[dict], batch_size: int = 100) -> list[list[dict]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than 0")
    return [keywords[index : index + batch_size] for index in range(0, len(keywords), batch_size)]


def _marker_matches(phrase: str, tokens: set[str], marker: str) -> bool:
    normalized_marker = normalize_phrase(marker)
    if not normalized_marker:
        return False
    if " " in normalized_marker:
        return normalized_marker in phrase
    return normalized_marker in tokens
