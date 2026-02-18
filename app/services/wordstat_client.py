from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class WordstatAPIError(Exception):
    """Base Wordstat API exception."""


class WordstatAuthError(WordstatAPIError):
    """Authorization error."""


class WordstatRateLimitError(WordstatAPIError):
    """Rate limit exceeded."""


class WordstatTimeoutError(WordstatAPIError):
    """Timeout while calling API."""


@dataclass(slots=True)
class WordstatKeyword:
    phrase: str
    frequency: int
    match_type: str | None = None


class WordstatClient:
    def __init__(self) -> None:
        self.base_url = str(settings.wordstat_base_url).rstrip("/")
        self.endpoint = settings.wordstat_endpoint
        self.timeout = settings.wordstat_timeout_seconds
        self.api_key = settings.wordstat_api_key

    async def get_keywords(self, niche: str, region: str) -> list[WordstatKeyword]:
        if not self.api_key:
            raise WordstatAuthError("Wordstat API ключ не задан в переменных окружения")

        url = f"{self.base_url}{self.endpoint}"
        payload: dict[str, Any] = {
            "method": "GetKeywords",
            "params": {"query": niche, "region": region},
        }
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        logger.info("Wordstat request: url=%s query=%s region=%s", url, niche, region)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.error("Wordstat timeout: %s", exc)
            raise WordstatTimeoutError("Wordstat API не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            logger.error("Wordstat HTTP error: %s", exc)
            raise WordstatAPIError("Ошибка соединения с Wordstat API") from exc

        logger.info("Wordstat response status=%s", response.status_code)
        if response.status_code in {401, 403}:
            raise WordstatAuthError("Ошибка авторизации в Wordstat API")
        if response.status_code == 429:
            raise WordstatRateLimitError("Превышен лимит запросов Wordstat API")
        if response.status_code >= 500:
            raise WordstatAPIError("Wordstat API временно недоступен")
        if response.status_code >= 400:
            raise WordstatAPIError(f"Wordstat API вернул ошибку: {response.status_code}")

        data = response.json()
        items = self._extract_items(data)
        if not items:
            raise WordstatAPIError("Wordstat API не вернул данных по вашему запросу")

        keywords: list[WordstatKeyword] = []
        for item in items:
            phrase = str(item.get("phrase") or item.get("keyword") or "").strip()
            frequency_raw = item.get("frequency") or item.get("shows") or item.get("impressions")
            if not phrase or frequency_raw is None:
                continue
            try:
                frequency = int(frequency_raw)
            except (TypeError, ValueError):
                continue
            keywords.append(
                WordstatKeyword(
                    phrase=phrase,
                    frequency=frequency,
                    match_type=item.get("match_type") or item.get("matchType"),
                )
            )

        if not keywords:
            raise WordstatAPIError("Wordstat API вернул данные в неожиданном формате")

        return keywords

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("result", "data", "keywords", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = value.get("items") or value.get("keywords") or value.get("result")
                if isinstance(nested, list):
                    return [item for item in nested if isinstance(item, dict)]
        return []
