from __future__ import annotations

import logging
import re
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
        self.token = settings.wordstat_oauth_token
        self._regions_cache: dict[str, int] | None = None

    async def get_keywords(self, niche: str, region: str) -> list[WordstatKeyword]:
        if not self.api_key and not self.token:
            raise WordstatAuthError("Wordstat API ключ или токен не задан в переменных окружения")

        if self.token:
            # New Wordstat API (v1)
            return await self._get_keywords_v1(niche, region)
        
        # Old/Standard direct API
        return await self._get_keywords_direct(niche, region)

    async def _get_keywords_v1(self, niche: str, region: str) -> list[WordstatKeyword]:
        region_id = await self._resolve_region_id(region)
        payload: dict[str, Any] = {
            "phrase": niche,
            "regions": [region_id],
            "devices": ["all"],
            "numPhrases": 200,
        }
        data = await self._post_json("/v1/topRequests", payload)
        
        if isinstance(data, list):
            if not data:
                raise WordstatAPIError("Wordstat API не вернул данных по вашему запросу")
            first = data[0]
            if isinstance(first, dict) and first.get("error"):
                raise WordstatAPIError(f"Wordstat API ошибка фразы: {first['error']}")
            data = first if isinstance(first, dict) else {}
        
        if not isinstance(data, dict):
            raise WordstatAPIError("Wordstat API вернул ответ в неожиданном формате")
            
        top_requests = data.get("topRequests")
        if not isinstance(top_requests, list):
            raise WordstatAPIError("Wordstat API не вернул topRequests")

        keywords: list[WordstatKeyword] = []
        for item in top_requests:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("phrase") or "").strip()
            count_raw = item.get("count")
            if not phrase or count_raw is None:
                continue
            try:
                count = int(count_raw)
            except (TypeError, ValueError):
                continue
            keywords.append(WordstatKeyword(phrase=phrase, frequency=count, match_type="topRequests"))
        
        if not keywords:
            raise WordstatAPIError("Wordstat API не вернул валидных запросов в topRequests")
        return keywords

    async def _get_keywords_direct(self, niche: str, region: str) -> list[WordstatKeyword]:
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
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise WordstatTimeoutError("Wordstat API не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise WordstatAPIError("Ошибка соединения с Wordstat API") from exc

        if response.status_code in {401, 403}:
            raise WordstatAuthError("Ошибка авторизации в Wordstat API")
        if response.status_code == 429:
            raise WordstatRateLimitError(self._build_quota_message(response))
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
        return keywords

    async def _resolve_region_id(self, region_name: str) -> int:
        region_name_clean = region_name.strip().lower()
        if not region_name_clean:
            raise WordstatAPIError("Не указан регион для запроса к Wordstat API")
        if self._regions_cache is None:
            data = await self._post_json("/v1/getRegionsTree", {})
            self._regions_cache = self._flatten_regions_to_map(data)
        
        region_id = self._regions_cache.get(region_name_clean)
        if region_id is None:
            raise WordstatAPIError(
                f"Регион '{region_name}' не найден. Проверьте название (например: Москва)."
            )
        return region_id

    async def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | list[Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise WordstatTimeoutError("Wordstat API не ответил вовремя") from exc
        except httpx.HTTPError as exc:
            raise WordstatAPIError("Ошибка соединения с Wordstat API") from exc

        if response.status_code in {401, 403}:
            raise WordstatAuthError("Ошибка авторизации в Wordstat API")
        if response.status_code == 429:
            raise WordstatRateLimitError(self._build_quota_message(response))
        if response.status_code >= 500:
            raise WordstatAPIError("Wordstat API временно недоступен")
        
        try:
            return response.json()
        except ValueError as exc:
            raise WordstatAPIError("Wordstat API вернул невалидный JSON") from exc

    @staticmethod
    def _build_quota_message(response: httpx.Response) -> str:
        text = response.text or ""
        match = re.search(r"Time to refill:\s*(\d+)\s*seconds", text, flags=re.IGNORECASE)
        if match:
            seconds = match.group(1)
            return f"Превышена персональная квота Wordstat API. Восстановление через {seconds} сек."
        return "Превышена персональная квота Wordstat API (429). Попробуйте позже."

    @staticmethod
    def _flatten_regions_to_map(regions_payload: dict[str, Any] | list[Any]) -> dict[str, int]:
        region_map: dict[str, int] = {}
        def walk(node: Any) -> None:
            if isinstance(node, list):
                for item in node: walk(item)
                return
            if not isinstance(node, dict): return
            rid, name = node.get("regionId"), node.get("name")
            if isinstance(rid, int) and isinstance(name, str):
                region_map[name.strip().lower()] = rid
            for value in node.values():
                if isinstance(value, (list, dict)): walk(value)
        walk(regions_payload)
        return region_map

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        for key in ("result", "data", "keywords", "items"):
            val = payload.get(key)
            if isinstance(val, list): return [i for i in val if isinstance(i, dict)]
            if isinstance(val, dict):
                nest = val.get("items") or val.get("keywords") or val.get("result")
                if isinstance(nest, list): return [i for i in nest if isinstance(i, dict)]
        return []
