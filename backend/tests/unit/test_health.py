from __future__ import annotations

import pytest
from httpx import AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api import health as health_module


class PassingRedis:
    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class FailingRedis:
    async def ping(self) -> bool:
        raise RedisConnectionError("redis unavailable")

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_healthz_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_ok_when_db_and_redis_are_available(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module.Redis,
        "from_url",
        staticmethod(lambda url: PassingRedis()),
    )

    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["checks"] == {"db": "ok", "redis": "ok"}


@pytest.mark.asyncio
async def test_readyz_returns_503_when_redis_is_unreachable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        health_module.Redis,
        "from_url",
        staticmethod(lambda url: FailingRedis()),
    )

    response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"]["checks"]["redis"] == "error"
