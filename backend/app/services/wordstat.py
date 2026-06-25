from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


BASE_URL = "https://searchapi.api.cloud.yandex.net/v2/wordstat"
IAM_TOKEN_URL = "https://iam.api.cloud.yandex.net/iam/v1/tokens"


def parse_count(value: str | int) -> int:
    if isinstance(value, int):
        return value

    cleaned = str(value).strip()
    if not cleaned or cleaned == "---":
        return 0

    cleaned = (
        cleaned.replace("\xa0", "")
        .replace("\u202f", "")
        .replace(" ", "")
        .replace(",", ".")
    )
    if not cleaned:
        return 0

    try:
        return int(cleaned)
    except ValueError:
        try:
            return int(float(cleaned))
        except ValueError:
            return 0


class WordstatClient:
    def __init__(self, api_key: str, folder_id: str) -> None:
        self.base_url = BASE_URL
        self.api_key = api_key
        self.folder_id = folder_id
        self.headers = {
            "Accept-Language": "ru",
        }
        self._iam_token: str | None = None
        self._iam_token_expires_at: datetime | None = None

    async def top_requests(
        self,
        query: str,
        region_ids: list[int] | None = None,
        num_phrases: int = 100,
    ) -> list[dict[str, int | str]]:
        payload: dict[str, Any] = {
            "phrase": query,
            "numPhrases": str(num_phrases),
            "folderId": self.folder_id,
        }
        if region_ids is not None:
            payload["regions"] = [str(region_id) for region_id in region_ids]

        data = await self._request("POST", "/topRequests", json=payload)
        raw_items = list(data.get("results") or []) + list(data.get("associations") or [])

        keywords: list[dict[str, int | str]] = []
        for item in raw_items:
            text = str(item.get("phrase") or item.get("text") or "").lower().strip()
            if not text:
                continue
            keywords.append({"phrase": text, "freq": parse_count(item.get("count") or 0)})
        return keywords

    async def get_regions_tree(self) -> list[dict[str, int | str | None]]:
        data = await self._request(
            "POST",
            "/getRegionsTree",
            json={"folderId": self.folder_id},
        )
        if isinstance(data, dict):
            roots = data.get("regions") or data.get("results") or []
        else:
            roots = data

        regions: list[dict[str, int | str | None]] = []
        self._flatten_regions(roots, None, regions)
        return regions

    async def user_info(self) -> dict[str, Any]:
        data = await self._request(
            "POST",
            "/getRegionsTree",
            json={"folderId": self.folder_id},
        )
        regions = data.get("regions") or []
        return {
            "status": "ok",
            "folderId": self.folder_id,
            "regionsRootCount": len(regions),
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        try:
            headers = await self._request_headers()
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            message = exc.response.text.strip()
            raise RuntimeError(
                f"Wordstat API error {exc.response.status_code}: {message}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Wordstat API request failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Wordstat API returned invalid JSON") from exc

    async def _request_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        headers["Authorization"] = await self._authorization_header()
        return headers

    async def _authorization_header(self) -> str:
        if self.api_key.startswith("t1."):
            return f"Bearer {self.api_key}"
        if self._looks_like_oauth_token(self.api_key):
            return f"Bearer {await self._get_iam_token()}"
        return f"Api-Key {self.api_key}"

    @staticmethod
    def _looks_like_oauth_token(token: str) -> bool:
        return len(token) > 2 and token[0] == "y" and token[1].isdigit() and token[2] == "_"

    async def _get_iam_token(self) -> str:
        now = datetime.now(timezone.utc)
        if (
            self._iam_token
            and self._iam_token_expires_at
            and self._iam_token_expires_at - timedelta(minutes=5) > now
        ):
            return self._iam_token

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    IAM_TOKEN_URL,
                    json={"yandexPassportOauthToken": self.api_key},
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            message = exc.response.text.strip()
            raise RuntimeError(
                f"Yandex IAM token exchange error {exc.response.status_code}: {message}"
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Yandex IAM token exchange failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Yandex IAM token exchange returned invalid JSON") from exc

        token = data.get("iamToken")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Yandex IAM token exchange response did not include iamToken")

        expires_at = data.get("expiresAt")
        if isinstance(expires_at, str) and expires_at:
            self._iam_token_expires_at = datetime.fromisoformat(
                expires_at.replace("Z", "+00:00")
            )
        else:
            self._iam_token_expires_at = now + timedelta(hours=1)

        self._iam_token = token
        return token

    def _flatten_regions(
        self,
        nodes: list[dict[str, Any]],
        parent_id: int | None,
        output: list[dict[str, int | str | None]],
    ) -> None:
        for node in nodes:
            try:
                region_id = int(node["id"])
            except (KeyError, TypeError, ValueError):
                continue

            name = str(node.get("label") or node.get("name") or "").strip()
            if name:
                output.append({"id": region_id, "name": name, "parent_id": parent_id})

            children = node.get("children") or []
            self._flatten_regions(children, region_id, output)
