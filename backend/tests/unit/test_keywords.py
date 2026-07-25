from __future__ import annotations

from app.services.keywords import (
    batch_keywords,
    is_garbage,
    normalize_phrase,
    parse_count_safe,
    score_keyword,
    select_keywords,
    select_forecast_keywords,
    classify_keyword_intent,
)


def test_parse_count_safe_int() -> None:
    assert parse_count_safe(1234) == 1234


def test_parse_count_safe_str_with_spaces() -> None:
    assert parse_count_safe("1 234") == 1234


def test_parse_count_safe_dash() -> None:
    assert parse_count_safe("---") == 0


def test_normalize_phrase() -> None:
    assert normalize_phrase("  Натяжные  Потолки  ") == "натяжные потолки"


def test_normalize_phrase_yo() -> None:
    assert normalize_phrase("ёлка") == "елка"


def test_is_garbage_stop_word() -> None:
    assert is_garbage("натяжные потолки своими руками") is True


def test_is_garbage_clean() -> None:
    assert is_garbage("натяжные потолки цена") is False


def test_score_commercial_higher_than_info() -> None:
    commercial_score = score_keyword("купить потолки", freq=100, max_freq=100)
    info_score = score_keyword("потолки виды", freq=100, max_freq=100)

    assert commercial_score > info_score


def test_select_keywords_filters_garbage() -> None:
    selected = select_keywords(
        [
            {"phrase": "натяжные потолки цена", "freq": 100},
            {"phrase": "натяжные потолки своими руками", "freq": 100},
        ],
    )

    assert [keyword["phrase"] for keyword in selected] == ["натяжные потолки цена"]


def test_select_keywords_filters_low_freq() -> None:
    selected = select_keywords(
        [
            {"phrase": "натяжные потолки цена", "freq": 5},
            {"phrase": "купить натяжные потолки", "freq": 100},
        ],
        min_freq=30,
    )

    assert [keyword["phrase"] for keyword in selected] == ["купить натяжные потолки"]


def test_select_keywords_dedup() -> None:
    selected = select_keywords(
        [
            {"phrase": "Натяжные потолки цена", "freq": 100},
            {"phrase": "натяжные  потолки цена", "freq": 250},
        ],
    )

    assert len(selected) == 1
    assert selected[0]["freq"] == 250


def test_select_keywords_limits_to_max() -> None:
    raw_keywords = [
        {"phrase": f"купить потолки {index}", "freq": index + 30}
        for index in range(500)
    ]

    assert len(select_keywords(raw_keywords, max_keywords=200)) == 200


def test_select_keywords_sorts_by_score() -> None:
    selected = select_keywords(
        [
            {"phrase": "потолки виды", "freq": 5000},
            {"phrase": "купить потолки", "freq": 1000},
            {"phrase": "потолки цена", "freq": 800},
        ],
    )

    scores = [keyword["score"] for keyword in selected]
    assert scores == sorted(scores, reverse=True)


def test_batch_keywords() -> None:
    batches = batch_keywords([{"phrase": str(index)} for index in range(200)])

    assert len(batches) == 2
    assert [len(batch) for batch in batches] == [100, 100]


def test_batch_keywords_uneven() -> None:
    batches = batch_keywords([{"phrase": str(index)} for index in range(150)])

    assert len(batches) == 2
    assert [len(batch) for batch in batches] == [100, 50]


def test_select_keywords_filters_conflicting_real_estate_purchase() -> None:
    selected = select_keywords(
        [
            {"phrase": "купить квартиру без ремонта", "freq": 500},
            {"phrase": "ремонт квартиры под ключ цена", "freq": 120},
        ],
        niche="ремонт квартир под ключ",
    )

    phrases = [keyword["phrase"] for keyword in selected]
    assert "купить квартиру без ремонта" not in phrases
    assert "ремонт квартиры под ключ цена" in phrases


def test_classify_keyword_intent_marks_conflicting_purchase_object() -> None:
    intent = classify_keyword_intent(
        "купить квартиру в москве без ремонта",
        niche="ремонт квартир под ключ",
    )

    assert intent["intent"] == "irrelevant"
    assert intent["priority"] == "excluded"


def test_select_forecast_keywords_keeps_priority_and_family_diversity() -> None:
    keywords: list[dict] = []
    for index in range(120):
        keywords.append(
            {
                "phrase": f"ремонт квартир общий вариант {index}",
                "freq": 1000 - index,
                "score": 1.0 - index / 1000,
                "priority": "high",
            }
        )
    for index in range(30):
        keywords.append(
            {
                "phrase": f"ремонт ванной комнаты хвост {index}",
                "freq": 300 - index,
                "score": 0.5 - index / 1000,
                "priority": "medium",
            }
        )
    for index in range(20):
        keywords.append(
            {
                "phrase": f"ремонт кухни хвост {index}",
                "freq": 200 - index,
                "score": 0.3 - index / 1000,
                "priority": "low",
            }
        )

    selected = select_forecast_keywords(keywords, limit=100)
    phrases = [str(item["phrase"]) for item in selected]

    assert len(selected) == 100
    assert any("ванной" in phrase for phrase in phrases)
    assert any("кухни" in phrase for phrase in phrases)
    assert sum(1 for item in selected if item["priority"] == "high") >= 60
