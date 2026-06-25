from __future__ import annotations

import pytest

from app.services.wordstat import parse_count
from app.services.wordstat_mock import MockWordstatClient


@pytest.mark.asyncio
async def test_mock_client_top_requests_returns_keywords() -> None:
    keywords = await MockWordstatClient().top_requests("test")

    assert keywords
    assert {"phrase", "freq"}.issubset(keywords[0])


@pytest.mark.asyncio
async def test_mock_client_regions_tree_returns_regions() -> None:
    regions = await MockWordstatClient().get_regions_tree()

    assert regions
    assert {"id", "name"}.issubset(regions[0])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1234, 1234),
        ("1 234", 1234),
        ("1\xa0234", 1234),
        ("1\u202f234", 1234),
        ("42,0", 42),
        ("---", 0),
        ("", 0),
        ("not-a-number", 0),
    ],
)
def test_parse_count_various_formats(value: str | int, expected: int) -> None:
    assert parse_count(value) == expected
