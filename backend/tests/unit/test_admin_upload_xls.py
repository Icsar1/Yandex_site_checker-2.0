from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from httpx import AsyncClient
from openpyxl import Workbook
import pytest

from app.db.database import get_db
from app.models.task import TaskCreate, TaskStatus
from app.services.tasks import create_task, get_task, update_task_status


async def _login(client: AsyncClient) -> None:
    response = await client.post(
        "/access/login",
        json={"password": "test-admin-password"},
    )
    assert response.status_code == 200


async def _move_to_awaiting_manual(db_path: Path, task_id: str) -> None:
    await update_task_status(str(db_path), task_id, TaskStatus.collecting_keys)
    await update_task_status(str(db_path), task_id, TaskStatus.forecasting)
    await update_task_status(str(db_path), task_id, TaskStatus.awaiting_manual)


def _xlsx_bytes(rows: list[list[object | None]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _valid_xlsx_bytes() -> bytes:
    return _xlsx_bytes(
        [
            ["Фраза", "Показы", "Клики", "Расход"],
            ["натяжные потолки", 1000, 50, 2500],
        ]
    )


@pytest.mark.asyncio
async def test_upload_xls_in_awaiting_manual_returns_202(
    client: AsyncClient,
    tmp_db: Path,
) -> None:
    await _login(client)
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="ceilings", region_ids=[213]),
    )
    await _move_to_awaiting_manual(tmp_db, task_id)

    response = await client.post(
        f"/api/admin/tasks/{task_id}/upload-xls",
        files={
            "file": (
                "forecast.xlsx",
                _valid_xlsx_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 202
    assert response.json()["status"] == TaskStatus.generating_text.value
    assert response.json()["parsed_rows"] == 1

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.generating_text.value
    assert task["source"] == "manual_xls"

    async with get_db(str(tmp_db)) as db:
        cursor = await db.execute(
            "SELECT payload FROM artifacts WHERE task_id = ? AND kind = 'forecast'",
            (task_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    forecast = json.loads(row["payload"])
    assert forecast[0]["phrase"] == "натяжные потолки"


@pytest.mark.asyncio
async def test_upload_xls_wrong_status_returns_409(
    client: AsyncClient,
    tmp_db: Path,
) -> None:
    await _login(client)
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="ceilings", region_ids=[213]),
    )

    response = await client.post(
        f"/api/admin/tasks/{task_id}/upload-xls",
        files={"file": ("forecast.xlsx", _valid_xlsx_bytes())},
    )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_upload_xls_invalid_format_returns_400(
    client: AsyncClient,
    tmp_db: Path,
) -> None:
    await _login(client)
    task_id = await create_task(
        str(tmp_db),
        TaskCreate(niche="ceilings", region_ids=[213]),
    )
    await _move_to_awaiting_manual(tmp_db, task_id)

    response = await client.post(
        f"/api/admin/tasks/{task_id}/upload-xls",
        files={
            "file": (
                "forecast.xlsx",
                _xlsx_bytes([["Показы", "Клики", "Расход"], [1000, 50, 2500]]),
            )
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "xls_parse_error"
