from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient
import pytest

from app.db.database import get_db
from app.models.task import TaskCreate, TaskStatus
from app.services.tasks import create_task, update_task_status


async def _login(client: AsyncClient) -> None:
    response = await client.post(
        "/access/login",
        json={"password": "test-admin-password"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_post_access_login_with_correct_password_sets_cookie(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/access/login",
        json={"password": "test-admin-password"},
    )

    assert response.status_code == 200
    assert "admin_session" in response.cookies


@pytest.mark.asyncio
async def test_post_access_login_with_wrong_password_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post("/access/login", json={"password": "wrong"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_admin_tasks_without_session_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/admin/tasks")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_admin_tasks_with_session_returns_200(
    client: AsyncClient,
) -> None:
    await _login(client)

    response = await client.get("/api/admin/tasks")

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == 0


@pytest.mark.asyncio
async def test_retry_failed_task_returns_202(
    client: AsyncClient,
    tmp_db: Path,
) -> None:
    await _login(client)
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="dentistry", region_ids=[213]),
    )
    await update_task_status(str(tmp_db), task_id, TaskStatus.failed)

    response = await client.post(f"/api/admin/tasks/{task_id}/retry")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


@pytest.mark.asyncio
async def test_retry_done_task_returns_409(
    client: AsyncClient,
    tmp_db: Path,
) -> None:
    await _login(client)
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="dentistry", region_ids=[213]),
    )
    async with get_db(str(tmp_db)) as db:
        await db.execute(
            "UPDATE tasks SET status = 'done', finished_at = created_at WHERE id = ?",
            (task_id,),
        )
        await db.commit()

    response = await client.post(f"/api/admin/tasks/{task_id}/retry")

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_admin_stats_returns_expected_fields(
    client: AsyncClient,
) -> None:
    await _login(client)

    response = await client.get("/api/admin/stats")

    assert response.status_code == 200
    body = response.json()
    assert {
        "total",
        "done",
        "failed",
        "awaiting_manual",
        "median_seconds",
        "p95_seconds",
        "success_rate_pct",
        "by_status",
    }.issubset(body)
