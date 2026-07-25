"""Yandex Direct API v4 Live client for budget forecasting."""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.services.direct import BatchCallback, DirectError, _maybe_call_batch_callback
from app.services.keywords import batch_keywords

_API_URL = "https://api.direct.yandex.com/live/v4/json/"
_POLL_INTERVAL_S = 3.0
_POLL_TIMEOUT_S = 120.0


class DirectApiError(DirectError):
    """Error returned by Yandex Direct API v4."""


class DirectApiClient:
    """Forecast client using the official Yandex Direct API v4 Live.

    Drop-in replacement for DirectForecastClient — same forecast_keywords interface.
    Requires an approved OAuth application and a valid Bearer token.

    Auth: token is passed in the JSON request body ("token" field), per v4 spec.
    """

    def __init__(self, api_key: str, login: str = "") -> None:
        self._api_key = api_key
        self._login = login  # Client-Login header for agency accounts

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        }
        if self._login:
            headers["Client-Login"] = self._login
        return headers

    async def _call(self, client: httpx.AsyncClient, method: str, param: Any) -> Any:
        # v4 Live: token goes in the request body, not in Authorization header
        body: dict[str, Any] = {
            "method": method,
            "param": param,
            "locale": "ru",
            "token": self._api_key,
        }
        response = await client.post(_API_URL, json=body, headers=self._headers())
        response.raise_for_status()
        data = response.json()
        if "error_code" in data:
            raise DirectApiError(
                f"Direct API {method} error {data['error_code']}: "
                f"{data.get('error_detail') or data.get('error_str', '')}"
            )
        return data.get("data")

    async def forecast_batch(self, keywords: list[str], region_id: int) -> list[dict]:
        if not keywords:
            return []

        # Phrases must be an array of strings (not objects) per v4 spec.
        # Currency is required even though docs say it's optional.
        create_param: dict[str, Any] = {
            "Phrases": list(keywords),
            "GeoID": [region_id],
            "Currency": "RUB",
        }
        if self._login:
            create_param["Login"] = self._login

        async with httpx.AsyncClient(timeout=60) as client:
            forecast_id = await self._call(client, "CreateNewForecast", create_param)
            if not isinstance(forecast_id, int):
                raise DirectApiError(
                    f"CreateNewForecast returned unexpected type: {type(forecast_id).__name__}"
                )
            await self._wait_for_forecast(client, forecast_id)
            # GetForecast takes the ForecastID as a scalar integer param, not an object
            data = await self._call(client, "GetForecast", forecast_id)

        return _parse_forecast_data(data)

    async def _wait_for_forecast(self, client: httpx.AsyncClient, forecast_id: int) -> None:
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        while time.monotonic() < deadline:
            await asyncio.sleep(_POLL_INTERVAL_S)
            entries = await self._call(client, "GetForecastList", {})
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if entry.get("ForecastID") != forecast_id:
                    continue
                status = entry.get("StatusForecast", "")
                if status == "Done":
                    return
                if status == "Failed":  # API uses "Failed", not "Error"
                    raise DirectApiError(f"Forecast {forecast_id} finished with status Failed")
        raise DirectApiError(
            f"Forecast {forecast_id} did not complete within {_POLL_TIMEOUT_S:.0f}s"
        )

    async def forecast_keywords(
        self,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: BatchCallback | None = None,
    ) -> list[dict]:
        batches = batch_keywords(keywords, batch_size)
        total_batches = len(batches)
        result: list[dict] = []
        for batch_index, batch in enumerate(batches, start=1):
            batch_result = await self.forecast_batch(
                [str(kw["phrase"]) for kw in batch],
                region_id,
            )
            result.extend(batch_result)
            await _maybe_call_batch_callback(on_batch, batch_index, total_batches)
        return result


def _parse_forecast_data(data: Any) -> list[dict]:
    """Parse GetForecast response into pipeline-compatible rows.

    Real API response structure (verified against live v4):
        data.Phrases[]: {Phrase, Shows, Clicks, FirstPlaceClicks, PremiumClicks,
                         Min, Max, PremiumMin, PremiumMax, CTR, FirstPlaceCTR,
                         PremiumCTR, Currency, IsRubric}
    We use FirstPlace position (first position in guarantee block):
        impressions = Shows  (total potential impressions)
        clicks      = FirstPlaceClicks
        cpc         = Max  (max CPC for first-place guarantee, in RUB)
        spending    = clicks × cpc  (matches Common.Max in the API response)
        ctr         = FirstPlaceCTR
    """
    if not isinstance(data, dict):
        return []
    phrase_info = data.get("Phrases") or []
    results: list[dict] = []
    for item in phrase_info:
        phrase = str(item.get("Phrase") or "").strip()
        if not phrase:
            continue
        results.append(_extract_row(phrase, item))
    return results


def _extract_row(phrase: str, item: dict) -> dict:
    shows = _to_int(item.get("Shows"))
    clicks = _to_int(item.get("FirstPlaceClicks"))
    first_place_cpc = _to_float(item.get("Max"))
    spending = round(clicks * first_place_cpc, 2)
    ctr = _to_float(item.get("FirstPlaceCTR"))
    avg_cpc = round(first_place_cpc, 2) if first_place_cpc else None

    return {
        "phrase": phrase,
        "impressions": shows,
        "clicks": clicks,
        "spending": spending,
        "ctr": ctr,
        "avg_cpc": avg_cpc,
        "placement": "first_place_guarantee",
        "first_place_cpc": avg_cpc,
        "guarantee_min_cpc": _to_float(item.get("Min")),
        "premium_min_cpc": _to_float(item.get("PremiumMin")),
        "premium_max_cpc": _to_float(item.get("PremiumMax")),
    }


def _to_int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0
