from __future__ import annotations

import pytest

from app.services.direct_mock import MockDirectForecastClient


EXPECTED_KEYS = {
    "phrase",
    "impressions",
    "clicks",
    "spending",
    "ctr",
    "avg_cpc",
    "avg_cpm",
    "avg_bid",
}


@pytest.mark.asyncio
async def test_mock_forecast_batch_returns_data() -> None:
    client = MockDirectForecastClient()

    result = await client.forecast_batch(["натяжные потолки"], region_id=213)

    assert len(result) == 1
    assert EXPECTED_KEYS == set(result[0])
    assert result[0]["phrase"] == "натяжные потолки"
    assert 500 <= result[0]["impressions"] <= 50000
    assert result[0]["clicks"] > 0


@pytest.mark.asyncio
async def test_mock_forecast_deterministic() -> None:
    client = MockDirectForecastClient()

    first = await client.forecast_batch(["натяжные потолки"], region_id=213)
    second = await client.forecast_batch(["натяжные потолки"], region_id=213)

    assert first == second


@pytest.mark.asyncio
async def test_mock_forecast_keywords_calls_callback() -> None:
    client = MockDirectForecastClient()
    calls: list[tuple[int, int]] = []

    async def on_batch(batch_index: int, total_batches: int) -> None:
        calls.append((batch_index, total_batches))

    keywords = [{"phrase": f"keyword {index}"} for index in range(150)]

    await client.forecast_keywords(
        keywords,
        region_id=213,
        batch_size=100,
        on_batch=on_batch,
    )

    assert calls == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_mock_forecast_keywords_merges_batches() -> None:
    client = MockDirectForecastClient()
    keywords = [{"phrase": f"keyword {index}"} for index in range(150)]

    result = await client.forecast_keywords(
        keywords,
        region_id=213,
        batch_size=100,
    )

    assert len(result) == 150
    assert [item["phrase"] for item in result] == [
        f"keyword {index}" for index in range(150)
    ]
