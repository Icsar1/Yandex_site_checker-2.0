from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.services.keywords import normalize_phrase

_REGULATED_CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "regulated_categories.json"


@lru_cache(maxsize=1)
def load_regulated_categories() -> list[dict]:
    with _REGULATED_CATEGORIES_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def detect_regulated_category(
    niche: str, keywords: list[str] | None = None
) -> dict | None:
    """Матчит нишу (и опционально собранные ключевые фразы) по стем-словам
    справочника regulated_categories.json. Возвращает первую подошедшую
    категорию или None, если тематика не регулируется."""
    haystack = normalize_phrase(niche)
    if keywords:
        haystack += " " + " ".join(normalize_phrase(kw) for kw in keywords)

    for category in load_regulated_categories():
        for trigger in category["trigger_keywords"]:
            if normalize_phrase(trigger) in haystack:
                return category
    return None
