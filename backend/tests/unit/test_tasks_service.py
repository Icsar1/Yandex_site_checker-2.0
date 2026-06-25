from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from app.models.task import TaskCreate, TaskStatus
from app.services.tasks import (
    create_task,
    generate_download_token,
    get_task,
    get_task_by_token,
    update_task_status,
)


def _payload(niche: str = "dentistry") -> TaskCreate:
    return TaskCreate(niche=niche, region_ids=[213], contact="lead@example.test")


@pytest.mark.asyncio
async def test_create_task_returns_valid_uuid(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())

    assert str(UUID(task_id)) == task_id


@pytest.mark.asyncio
async def test_get_task_returns_created_task(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())

    task = await get_task(str(tmp_db), task_id)

    assert task is not None
    assert task["id"] == task_id
    assert task["niche"] == "dentistry"
    assert task["region_ids"] == [213]
    assert task["status"] == TaskStatus.queued.value


@pytest.mark.asyncio
async def test_valid_state_transition_succeeds(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())

    updated = await update_task_status(
        str(tmp_db),
        task_id,
        TaskStatus.collecting_keys,
    )

    task = await get_task(str(tmp_db), task_id)
    assert updated is True
    assert task is not None
    assert task["status"] == TaskStatus.collecting_keys.value


@pytest.mark.asyncio
async def test_invalid_state_transition_raises(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())

    with pytest.raises(ValueError):
        await update_task_status(str(tmp_db), task_id, TaskStatus.done)


@pytest.mark.asyncio
async def test_terminal_done_status_cannot_transition(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())
    transitions = [
        TaskStatus.collecting_keys,
        TaskStatus.forecasting,
        TaskStatus.generating_text,
        TaskStatus.rendering_pdf,
        TaskStatus.done,
    ]
    for next_status in transitions:
        await update_task_status(str(tmp_db), task_id, next_status)

    with pytest.raises(ValueError):
        await update_task_status(str(tmp_db), task_id, TaskStatus.failed)


@pytest.mark.asyncio
async def test_failed_to_queued_retry_succeeds(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())
    await update_task_status(str(tmp_db), task_id, TaskStatus.failed)

    updated = await update_task_status(str(tmp_db), task_id, TaskStatus.queued)

    task = await get_task(str(tmp_db), task_id)
    assert updated is True
    assert task is not None
    assert task["status"] == TaskStatus.queued.value


@pytest.mark.asyncio
async def test_generate_download_token_returns_token_and_lookup_finds_task(
    tmp_db: Path,
) -> None:
    task_id = await create_task(str(tmp_db), _payload())

    token = await generate_download_token(str(tmp_db), task_id, ttl_seconds=60)
    task = await get_task_by_token(str(tmp_db), token)

    assert token
    assert task is not None
    assert task["id"] == task_id


@pytest.mark.asyncio
async def test_expired_token_returns_none(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), _payload())
    token = await generate_download_token(str(tmp_db), task_id, ttl_seconds=-1)

    task = await get_task_by_token(str(tmp_db), token)

    assert task is None
