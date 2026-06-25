from __future__ import annotations

import pytest

from app.services import progress as progress_module
from app.services.progress import get_progress, set_progress


class DictRedis:
    def __init__(self, store: dict[str, str]) -> None:
        self.store = store

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def aclose(self) -> None:
        return None


@pytest.fixture
def redis_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    store: dict[str, str] = {}
    monkeypatch.setattr(
        progress_module.Redis,
        "from_url",
        staticmethod(lambda url: DictRedis(store)),
    )
    return store


@pytest.mark.asyncio
async def test_set_progress_and_get_progress_round_trip(
    redis_store: dict[str, str],
) -> None:
    await set_progress(
        "redis://test",
        "task-1",
        "generating_text",
        sub_progress=0.2,
        ttl=60,
    )

    progress = await get_progress("redis://test", "task-1")

    assert progress is not None
    assert progress.stage == "generating_text"
    assert progress.step == 3
    assert progress.percent == 60
    assert progress.terminal is False
    assert redis_store


@pytest.mark.asyncio
async def test_get_progress_returns_none_for_unknown_task(
    redis_store: dict[str, str],
) -> None:
    progress = await get_progress("redis://test", "missing")

    assert progress is None


@pytest.mark.asyncio
async def test_sub_progress_interpolates_percent_correctly(
    redis_store: dict[str, str],
) -> None:
    await set_progress(
        "redis://test",
        "task-2",
        "forecasting",
        sub_progress=0.5,
    )

    progress = await get_progress("redis://test", "task-2")

    assert progress is not None
    assert progress.percent == 40
