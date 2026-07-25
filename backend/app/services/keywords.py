from __future__ import annotations

import math
import re
from typing import Literal


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

KeywordIntent = Literal["target", "adjacent", "informational", "irrelevant", "review"]

_SERVICE_ACTION_STEMS = {
    "ремонт",
    "отдел",
    "стро",
    "монтаж",
    "установ",
    "дизайн",
    "проект",
    "смет",
}

_REAL_ESTATE_OBJECT_STEMS = {
    "кварт",
    "комнат",
    "студ",
    "дом",
    "новост",
    "вторич",
}

_REAL_ESTATE_BUY_STEMS = {
    "куп",
    "покуп",
    "прод",
    "снять",
    "сдам",
    "аренд",
    "ипот",
}

_REVIEW_MARKERS = {
    "отзыв",
    "обзор",
    "рейтинг",
    "форум",
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


def classify_keyword_intent(
    phrase: str,
    niche: str | None = None,
    geo_tokens: set[str] | None = None,
) -> dict[str, object]:
    normalized = normalize_phrase(phrase)
    tokens = normalized.split()
    token_set = set(tokens)
    niche_stems = extract_niche_stems(niche or "")
    reasons: list[str] = []

    if not normalized:
        return {"intent": "irrelevant", "priority": "excluded", "reasons": ["empty"]}
    if is_garbage(normalized):
        return {"intent": "informational", "priority": "excluded", "reasons": ["info_stop"]}
    if _has_conflicting_real_estate_intent(tokens, niche_stems):
        return {
            "intent": "irrelevant",
            "priority": "excluded",
            "reasons": ["conflicting_purchase_object"],
        }
    if niche_stems and not is_niche_relevant(normalized, niche_stems):
        return {"intent": "review", "priority": "excluded", "reasons": ["weak_niche_match"]}
    if any(_token_has_stem(token, _REVIEW_MARKERS) for token in tokens):
        return {"intent": "review", "priority": "low", "reasons": ["review_marker"]}

    commercial_hits = [
        marker
        for marker in COMMERCIAL_MARKERS
        if _marker_matches(normalized, token_set, marker)
    ]
    normalized_geo_tokens = {
        normalize_phrase(token)
        for token in (geo_tokens or set())
        if normalize_phrase(token)
    }
    has_geo = bool(normalized_geo_tokens and (token_set & normalized_geo_tokens))
    if commercial_hits or has_geo:
        if commercial_hits:
            reasons.append("commercial")
        if has_geo:
            reasons.append("geo")
        return {"intent": "target", "priority": "high", "reasons": reasons}
    return {"intent": "adjacent", "priority": "medium", "reasons": reasons}


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


def _has_conflicting_real_estate_intent(tokens: list[str], niche_stems: set[str]) -> bool:
    if not any(_token_has_stem(stem, _SERVICE_ACTION_STEMS) for stem in niche_stems):
        return False
    has_buy_action = any(_token_has_stem(token, _REAL_ESTATE_BUY_STEMS) for token in tokens)
    has_real_estate_object = any(
        _token_has_stem(token, _REAL_ESTATE_OBJECT_STEMS) for token in tokens
    )
    return has_buy_action and has_real_estate_object


def _token_has_stem(token: str, stems: set[str]) -> bool:
    return any(token.startswith(stem) or stem.startswith(token) for stem in stems)


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
    meta_by_phrase: dict[str, dict[str, object]] = {}

    for raw_keyword in raw_keywords:
        phrase = normalize_phrase(str(raw_keyword.get("phrase") or ""))
        freq = parse_count_safe(raw_keyword.get("freq") or 0)
        if not phrase or freq < min_freq or is_garbage(phrase, stop_list):
            continue
        intent_meta = classify_keyword_intent(phrase, niche, geo_tokens)
        if intent_meta.get("priority") == "excluded":
            continue
        if niche_stems and not is_niche_relevant(phrase, niche_stems):
            continue
        deduped[phrase] = max(freq, deduped.get(phrase, 0))
        meta_by_phrase[phrase] = intent_meta

    if not deduped:
        return []

    max_freq = max(deduped.values())
    scored = [
        {
            "phrase": phrase,
            "freq": freq,
            "score": score_keyword(phrase, freq, max_freq, geo_tokens),
            "intent": str(meta_by_phrase.get(phrase, {}).get("intent") or "adjacent"),
            "priority": str(meta_by_phrase.get(phrase, {}).get("priority") or "medium"),
        }
        for phrase, freq in deduped.items()
    ]
    scored.sort(key=lambda item: (-float(item["score"]), -int(item["freq"]), str(item["phrase"])))
    return scored[:max_keywords]


def select_forecast_keywords(keywords: list[dict], limit: int = 100) -> list[dict]:
    if limit <= 0:
        return []
    if len(keywords) <= limit:
        return list(keywords)

    ordered = sorted(
        enumerate(keywords),
        key=lambda item: (
            _priority_rank(str(item[1].get("priority") or "medium")),
            -float(item[1].get("score") or 0.0),
            -int(item[1].get("freq") or 0),
            item[0],
        ),
    )
    remaining = [item for _, item in ordered]
    selected: list[dict] = []
    seen_phrases: set[str] = set()

    priority_quotas = _priority_quotas(limit)
    for priority, quota in priority_quotas:
        bucket = [kw for kw in remaining if str(kw.get("priority") or "medium") == priority]
        for kw in _round_robin_by_family(bucket, quota):
            phrase = normalize_phrase(str(kw.get("phrase") or ""))
            if phrase and phrase not in seen_phrases:
                selected.append(kw)
                seen_phrases.add(phrase)
        if len(selected) >= limit:
            return selected[:limit]

    for kw in _round_robin_by_family(remaining, limit - len(selected)):
        phrase = normalize_phrase(str(kw.get("phrase") or ""))
        if phrase and phrase not in seen_phrases:
            selected.append(kw)
            seen_phrases.add(phrase)
        if len(selected) >= limit:
            break
    return selected


def _priority_quotas(limit: int) -> list[tuple[str, int]]:
    high = max(1, round(limit * 0.60))
    medium = max(1, round(limit * 0.30))
    low = max(0, limit - high - medium)
    return [("high", high), ("medium", medium), ("low", low)]


def _priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2}.get(priority, 1)


def _round_robin_by_family(keywords: list[dict], limit: int) -> list[dict]:
    if limit <= 0 or not keywords:
        return []
    families: dict[str, list[dict]] = {}
    for kw in keywords:
        families.setdefault(_forecast_family(str(kw.get("phrase") or "")), []).append(kw)

    result: list[dict] = []
    family_names = sorted(
        families,
        key=lambda name: (
            -max(float(kw.get("score") or 0.0) for kw in families[name]),
            name,
        ),
    )
    while len(result) < limit and family_names:
        next_names: list[str] = []
        for name in family_names:
            bucket = families[name]
            if bucket:
                result.append(bucket.pop(0))
                if len(result) >= limit:
                    break
            if bucket:
                next_names.append(name)
        family_names = next_names
    return result


def _forecast_family(phrase: str) -> str:
    tokens = [
        token
        for token in normalize_phrase(phrase).split()
        if token not in _RU_STOPWORDS and len(token) >= 3
    ]
    if not tokens:
        return "__other"
    if len(tokens) == 1:
        return tokens[0][:5]
    return " ".join(token[:5] for token in tokens[:2])


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
