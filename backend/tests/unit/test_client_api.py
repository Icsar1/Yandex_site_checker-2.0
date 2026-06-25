from __future__ import annotations

from httpx import AsyncClient
import pytest

from app.api import client as client_module
from app.models.task import TaskCreate
from app.services.tasks import create_task


@pytest.fixture(autouse=True)
def disable_redis_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_progress(redis_url: str, task_id: str):
        return None

    monkeypatch.setattr(client_module, "get_progress", no_progress)


@pytest.mark.asyncio
async def test_post_api_tasks_with_valid_data_returns_201(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/tasks",
        json={"niche": "dentistry", "region_ids": [213], "contact": None},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "queued"
    assert response.json()["task_id"]


@pytest.mark.asyncio
async def test_post_api_tasks_with_empty_niche_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/tasks",
        json={"niche": "", "region_ids": [213]},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_api_task_returns_task(
    client: AsyncClient,
    tmp_db,
) -> None:
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="dentistry", region_ids=[213]),
    )

    response = await client.get(f"/api/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["id"] == task_id
    assert response.json()["region_ids"] == [213]


@pytest.mark.asyncio
async def test_get_api_task_not_found_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/tasks/missing")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_api_task_progress_returns_progress(
    client: AsyncClient,
    tmp_db,
) -> None:
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="dentistry", region_ids=[213]),
    )

    response = await client.get(f"/api/tasks/{task_id}/progress")

    assert response.status_code == 200
    assert response.json()["stage"] == "queued"
    assert response.json()["percent"] == 0


@pytest.mark.asyncio
async def test_get_pdf_token_not_found_returns_404(client: AsyncClient) -> None:
    response = await client.get("/api/pdf/missing")

    assert response.status_code == 404
