from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import aiosqlite

from app.db.database import get_db
from app.models.task import TERMINAL_STATUSES, TaskCreate, TaskStatus

VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.queued: {TaskStatus.collecting_keys},
    TaskStatus.collecting_keys: {TaskStatus.forecasting},
    TaskStatus.forecasting: {
        TaskStatus.generating_text,
        TaskStatus.awaiting_manual,
        TaskStatus.queued,
    },
    TaskStatus.awaiting_manual: {TaskStatus.generating_text},
    TaskStatus.generating_text: {TaskStatus.rendering_pdf},
    TaskStatus.rendering_pdf: {TaskStatus.done},
    TaskStatus.failed: {TaskStatus.queued},
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def row_to_task(row: aiosqlite.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None

    task = dict(row)
    try:
        task["region_ids"] = json.loads(task.get("region_ids") or "[]")
    except json.JSONDecodeError:
        task["region_ids"] = []
    try:
        raw = task.get("search_masks")
        task["search_masks"] = json.loads(raw) if raw else None
    except (json.JSONDecodeError, TypeError):
        task["search_masks"] = None
    task["progress_pct"] = int(task.get("progress_pct") or 0)
    return task


def can_transition(current_status: TaskStatus, new_status: TaskStatus) -> bool:
    allowed = set(VALID_TRANSITIONS.get(current_status, set()))
    if current_status not in TERMINAL_STATUSES:
        allowed.update({TaskStatus.failed, TaskStatus.canceled})
    return new_status in allowed


async def create_task(db_path: str, data: TaskCreate) -> str:
    task_id = str(uuid4())
    region_label = (data.region_label or "").strip() or ", ".join(str(r) for r in data.region_ids)
    search_masks_json = json.dumps(data.masks, ensure_ascii=False) if data.masks else None

    async with get_db(db_path) as db:
        await db.execute(
            """
            INSERT INTO tasks (id, niche, region_ids, region_label, contact, search_masks)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                data.niche,
                json.dumps(data.region_ids),
                region_label,
                data.contact,
                search_masks_json,
            ),
        )
        await db.commit()

    return task_id


async def get_task(db_path: str, task_id: str) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    return row_to_task(row)


async def update_task_status(
    db_path: str,
    task_id: str,
    new_status: TaskStatus,
    error_class: str | None = None,
    error_message: str | None = None,
) -> bool:
    new_status = TaskStatus(new_status)
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        if row is None:
            return False

        current_status = TaskStatus(row["status"])
        if not can_transition(current_status, new_status):
            raise ValueError(
                f"Invalid task status transition: {current_status.value} -> {new_status.value}"
            )

        now = _utc_now()
        update_parts = [
            "status = ?",
            "stage = ?",
            "updated_at = ?",
            "error_class = ?",
            "error_message = ?",
        ]
        params: list[Any] = [
            new_status.value,
            new_status.value,
            now,
            error_class if new_status == TaskStatus.failed else None,
            error_message if new_status == TaskStatus.failed else None,
        ]

        if new_status == TaskStatus.collecting_keys:
            update_parts.append("started_at = COALESCE(started_at, ?)")
            params.append(now)
        if new_status in TERMINAL_STATUSES:
            update_parts.append("finished_at = ?")
            params.append(now)
        if new_status == TaskStatus.queued:
            update_parts.extend(["started_at = NULL", "finished_at = NULL"])

        params.append(task_id)
        cursor = await db.execute(
            f"UPDATE tasks SET {', '.join(update_parts)} WHERE id = ?",
            tuple(params),
        )
        await db.commit()
        return cursor.rowcount > 0


async def generate_download_token(db_path: str, task_id: str, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    ).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    async with get_db(db_path) as db:
        cursor = await db.execute(
            """
            UPDATE tasks
            SET download_token = ?, token_expires_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (token, expires_at, _utc_now(), task_id),
        )
        await db.commit()

    if cursor.rowcount == 0:
        raise ValueError(f"Task not found: {task_id}")

    return token


async def get_task_by_token(db_path: str, token: str) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE download_token = ?",
            (token,),
        )
        row = await cursor.fetchone()

    task = row_to_task(row)
    if task is None or not task.get("token_expires_at"):
        return None

    if _parse_utc(task["token_expires_at"]) <= datetime.now(UTC):
        return None

    return task


async def add_task_event(
    db_path: str,
    task_id: str,
    event: str,
    stage: str | None = None,
    message: str | None = None,
    level: str = "info",
    meta: dict[str, Any] | None = None,
) -> None:
    async with get_db(db_path) as db:
        await db.execute(
            """
            INSERT INTO task_events (task_id, level, event, stage, message, meta)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                level,
                event,
                stage,
                message,
                json.dumps(meta or {}, ensure_ascii=False),
            ),
        )
        await db.commit()


async def set_suggested_niche(db_path: str, task_id: str, suggested: str) -> None:
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE tasks SET suggested_niche = ?, updated_at = ? WHERE id = ?",
            (suggested, _utc_now(), task_id),
        )
        await db.commit()
