from __future__ import annotations

import hashlib
import inspect
import random
from collections.abc import Awaitable, Callable

from app.services.keywords import batch_keywords


BatchCallback = Callable[[int, int], Awaitable[None] | None]


class MockDirectForecastClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def forecast_batch(self, keywords: list[str], region_id: int) -> list[dict]:
        return [_forecast_for_keyword(keyword) for keyword in keywords]

    async def forecast_keywords(
        self,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: BatchCallback | None = None,
    ) -> list[dict]:
        batches = batch_keywords(keywords, batch_size)
        total_batches = len(batches)
        forecast: list[dict] = []

        for batch_index, batch in enumerate(batches, start=1):
            batch_result = await self.forecast_batch(
                [str(keyword["phrase"]) for keyword in batch],
                region_id,
            )
            forecast.extend(batch_result)
            await _maybe_call_batch_callback(on_batch, batch_index, total_batches)

        return forecast


def _forecast_for_keyword(keyword: str) -> dict:
    rng = random.Random(_keyword_seed(keyword))
    impressions = rng.randint(500, 50000)
    clicks = max(1, int(round(impressions * rng.uniform(0.02, 0.08))))
    ctr = clicks / impressions * 100
    avg_cpc_base = rng.uniform(15, 120)
    spending = clicks * avg_cpc_base

    return {
        "phrase": keyword,
        "impressions": impressions,
        "clicks": clicks,
        "spending": round(spending, 2),
        "ctr": round(ctr, 2),
        "avg_cpc": round(spending / clicks, 2),
        "avg_cpm": round(spending / impressions * 1000, 2),
        "avg_bid": round(rng.uniform(20, 150), 2),
    }


def _keyword_seed(keyword: str) -> int:
    digest = hashlib.sha256(keyword.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


async def _maybe_call_batch_callback(
    on_batch: BatchCallback | None,
    batch_index: int,
    total_batches: int,
) -> None:
    if on_batch is None:
        return
    result = on_batch(batch_index, total_batches)
    if inspect.isawaitable(result):
        await result
