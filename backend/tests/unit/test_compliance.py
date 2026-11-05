from __future__ import annotations

from app.services.compliance import detect_regulated_category, load_regulated_categories


def test_load_regulated_categories_returns_known_categories() -> None:
    categories = load_regulated_categories()
    ids = {c["id"] for c in categories}

    assert {"medicine", "finance", "supplements", "alcohol", "gambling"} <= ids


def test_detect_regulated_category_matches_medicine_niche() -> None:
    category = detect_regulated_category("интимная пластика")

    assert category is not None
    assert category["id"] == "medicine"
    assert category["required_documents"]
    assert category["mandatory_disclaimers"]


def test_detect_regulated_category_matches_via_keywords_not_only_niche() -> None:
    category = detect_regulated_category(
        "услуги для женщин", keywords=["коррекция губ цена", "увеличение груди"]
    )

    assert category is not None
    assert category["id"] == "medicine"


def test_detect_regulated_category_returns_none_for_neutral_niche() -> None:
    assert detect_regulated_category("кухни на заказ") is None


def test_detect_regulated_category_matches_finance_niche() -> None:
    category = detect_regulated_category("оформить кредит наличными")

    assert category is not None
    assert category["id"] == "finance"


def test_detect_regulated_category_matches_gambling_niche() -> None:
    category = detect_regulated_category("ставки на спорт онлайн")

    assert category is not None
    assert category["id"] == "gambling"
