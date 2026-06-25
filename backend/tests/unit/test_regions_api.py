from __future__ import annotations

from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_get_regions_returns_filtered_list(client: AsyncClient) -> None:
    response = await client.get("/api/regions", params={"q": "моск"})

    assert response.status_code == 200
    assert {"id": 213, "name": "Москва"} in response.json()


@pytest.mark.asyncio
async def test_get_regions_empty_query_returns_all(client: AsyncClient) -> None:
    response = await client.get("/api/regions")

    assert response.status_code == 200
    assert response.json()
    assert {"id": 225, "name": "Россия"} in response.json()


@pytest.mark.asyncio
async def test_get_regions_no_match_returns_empty(client: AsyncClient) -> None:
    response = await client.get("/api/regions", params={"q": "xyznonexistent"})

    assert response.status_code == 200
    assert response.json() == []
