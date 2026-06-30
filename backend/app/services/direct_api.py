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
_COST_DIVISOR = 1_000_000  # API returns cost in microrubls


class DirectApiError(DirectError):
    """Error returned by Yandex Direct API v4."""


class DirectApiClient:
    """Forecast client using the official Yandex Direct API v4 Live.

    Drop-in replacement for DirectForecastClient — same forecast_keywords interface.
    Requires an approved OAuth application and a valid Bearer token.
    """

    def __init__(self, api_key: str, login: str = "") -> None:
        self._api_key = api_key
        self._login = login  # Client-Login header for agency accounts

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept-Language": "ru",
        }
        if self._login:
            headers["Client-Login"] = self._login
        return headers

    async def _call(self, client: httpx.AsyncClient, method: str, param: Any) -> Any:
        body: dict[str, Any] = {"method": method, "param": param, "locale": "ru"}
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

        phrases = [{"Phrase": kw, "MinusWords": []} for kw in keywords]
        create_param: dict[str, Any] = {
            "Phrases": phrases,
            "GeoID": [region_id],
            "Currency": "RUB",
            "Period": "MONTH",
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
            data = await self._call(client, "GetForecast", {"ForecastID": forecast_id})

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
                if status == "Error":
                    raise DirectApiError(f"Forecast {forecast_id} finished with status Error")
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
    if not isinstance(data, dict):
        return []
    phrase_info = data.get("PhraseInfo") or []
    results: list[dict] = []
    for item in phrase_info:
        phrase = str(item.get("Phrase") or "").strip()
        if not phrase:
            continue
        results.append(_extract_row(phrase, item))
    return results


def _extract_row(phrase: str, item: dict) -> dict:
    positions = item.get("Positions") or {}
    # Prefer P1 (100% traffic volume); fall back to first available position
    pos_data = (
        positions.get("P1")
        or positions.get("1")
        or (next(iter(positions.values())) if positions else None)
    )
    vals: dict = pos_data.get("Max") or pos_data.get("Min") or pos_data if pos_data else item

    shows = _to_int(vals.get("Shows"))
    clicks = _to_int(vals.get("Clicks"))
    spending = round(_to_float(vals.get("Cost")) / _COST_DIVISOR, 2)
    ctr = _to_float(vals.get("Ctr"))
    avg_cpc = round(spending / clicks, 2) if clicks > 0 else None

    return {
        "phrase": phrase,
        "impressions": shows,
        "clicks": clicks,
        "spending": spending,
        "ctr": ctr,
        "avg_cpc": avg_cpc,
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
