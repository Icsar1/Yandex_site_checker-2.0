from __future__ import annotations

import json
import logging
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel
from starlette.datastructures import UploadFile

from app.config import Settings, get_settings
from app.db.database import get_db
from app.models.task import TERMINAL_STATUSES, TaskStatus
from app.services.direct_xls import parse_forecast_xls
from app.services.tasks import get_task, row_to_task, update_task_status

SESSION_COOKIE_NAME = "admin_session"

access_router = APIRouter(prefix="/access")
router = APIRouter(prefix="/api/admin")
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


class LoginRequest(BaseModel):
    password: str


def _get_request_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SESSION_SECRET.get_secret_value())


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_login_rate_limit(request: Request, settings: Settings) -> None:
    now = time.time()
    attempts = _login_attempts[_client_ip(request)]
    while attempts and now - attempts[0] > 60:
        attempts.popleft()
    if len(attempts) >= settings.LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts",
        )
    attempts.append(now)


async def require_admin_session(request: Request) -> Settings:
    settings = _get_request_settings(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        payload = _serializer(settings).loads(
            token,
            max_age=settings.SESSION_TTL_SECONDS,
        )
    except (BadSignature, SignatureExpired):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        ) from None

    if payload != {"scope": "admin"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    return settings


@access_router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
) -> dict[str, str]:
    settings = _get_request_settings(request)
    _check_login_rate_limit(request, settings)

    expected_password = settings.ADMIN_PASSWORD.get_secret_value()
    if not secrets.compare_digest(payload.password, expected_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    _login_attempts.pop(_client_ip(request), None)
    signed_token = _serializer(settings).dumps({"scope": "admin"})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        signed_token,
        httponly=True,
        samesite="lax",
        max_age=settings.SESSION_TTL_SECONDS,
    )
    return {"status": "ok"}


@access_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/tasks")
async def list_admin_tasks(
    settings: Settings = Depends(require_admin_session),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    where_clause = ""
    params: list[Any] = []
    if task_status is not None:
        where_clause = "WHERE status = ?"
        params.append(task_status.value)

    async with get_db(settings.DATABASE_PATH) as db:
        total_cursor = await db.execute(
            f"SELECT COUNT(*) AS total FROM tasks {where_clause}",
            tuple(params),
        )
        total_row = await total_cursor.fetchone()
        cursor = await db.execute(
            f"""
            SELECT * FROM tasks
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params + [limit, offset]),
        )
        rows = await cursor.fetchall()

    return {
        "items": [row_to_task(row) for row in rows],
        "total": int(total_row["total"] if total_row else 0),
    }


@router.get("/tasks/{task_id}")
async def get_admin_task(
    task_id: str,
    settings: Settings = Depends(require_admin_session),
) -> dict[str, Any]:
    task = await get_task(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    async with get_db(settings.DATABASE_PATH) as db:
        cursor = await db.execute(
            """
            SELECT id, ts, level, event, stage, message, meta
            FROM task_events
            WHERE task_id = ?
            ORDER BY ts DESC, id DESC
            LIMIT 20
            """,
            (task_id,),
        )
        rows = await cursor.fetchall()

    return {"task": task, "events": [dict(row) for row in rows]}


@router.post("/tasks/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_admin_task(
    task_id: str,
    settings: Settings = Depends(require_admin_session),
) -> dict[str, str]:
    task = await get_task(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task["status"] != TaskStatus.failed.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is not failed")

    await update_task_status(settings.DATABASE_PATH, task_id, TaskStatus.queued)
    async with get_db(settings.DATABASE_PATH) as db:
        await db.execute(
            "UPDATE tasks SET attempts = attempts + 1 WHERE id = ?",
            (task_id,),
        )
        await db.commit()

    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
        pool = await create_pool(redis_settings)
        try:
            await pool.enqueue_job("run_pipeline", task_id)
        finally:
            await pool.aclose()
    except Exception as exc:
        logging.getLogger(__name__).error("Failed to re-enqueue task %s: %s", task_id, exc)

    return {"task_id": task_id, "status": TaskStatus.queued.value}


@router.post("/tasks/{task_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_admin_task(
    task_id: str,
    settings: Settings = Depends(require_admin_session),
) -> dict[str, str]:
    task = await get_task(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if TaskStatus(task["status"]) in TERMINAL_STATUSES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task is terminal")

    await update_task_status(settings.DATABASE_PATH, task_id, TaskStatus.canceled)
    return {"task_id": task_id, "status": TaskStatus.canceled.value}


@router.post("/tasks/{task_id}/upload-xls", status_code=status.HTTP_202_ACCEPTED)
async def upload_xls_admin_task(
    task_id: str,
    request: Request,
    settings: Settings = Depends(require_admin_session),
) -> dict[str, Any]:
    task = await get_task(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task["status"] != TaskStatus.awaiting_manual.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Task is not awaiting manual upload",
        )

    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is required")

    content = await upload.read()
    if len(content) > settings.UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)

    upload_dir = Path(settings.PDF_OUTPUT_DIR).parent / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    output_path = upload_dir / f"{task_id}.xls"
    output_path.write_bytes(content)

    try:
        forecast_rows = parse_forecast_xls(output_path)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="xls_parse_error",
        ) from exc

    async with get_db(settings.DATABASE_PATH) as db:
        await db.execute(
            """
            INSERT INTO artifacts (task_id, kind, path)
            VALUES (?, 'xls_upload', ?)
            ON CONFLICT(task_id, kind) DO UPDATE SET
                path = excluded.path,
                payload = NULL
            """,
            (task_id, str(output_path)),
        )
        await db.execute(
            """
            INSERT INTO artifacts (task_id, kind, payload)
            VALUES (?, 'forecast', ?)
            ON CONFLICT(task_id, kind) DO UPDATE SET
                path = NULL,
                payload = excluded.payload
            """,
            (
                task_id,
                json.dumps(forecast_rows, ensure_ascii=False),
            ),
        )
        await db.execute(
            "UPDATE tasks SET source = 'manual_xls' WHERE id = ?",
            (task_id,),
        )
        await db.commit()

    await update_task_status(settings.DATABASE_PATH, task_id, TaskStatus.generating_text)

    # Enqueue pipeline to resume from generating_text stage.
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
        pool = await create_pool(redis_settings)
        try:
            await pool.enqueue_job("run_pipeline", task_id)
        finally:
            await pool.aclose()
    except Exception:
        pass

    return {
        "task_id": task_id,
        "status": TaskStatus.generating_text.value,
        "parsed_rows": len(forecast_rows),
    }


@router.get("/stats")
async def get_admin_stats(
    settings: Settings = Depends(require_admin_session),
) -> dict[str, Any]:
    async with get_db(settings.DATABASE_PATH) as db:
        status_cursor = await db.execute(
            "SELECT status, COUNT(*) AS count FROM tasks GROUP BY status"
        )
        status_rows = await status_cursor.fetchall()
        total_cursor = await db.execute("SELECT COUNT(*) AS total FROM tasks")
        total_row = await total_cursor.fetchone()
        duration_cursor = await db.execute(
            """
            SELECT
                CAST((julianday(finished_at) - julianday(created_at)) * 86400 AS INTEGER)
                AS seconds
            FROM tasks
            WHERE status = 'done' AND finished_at IS NOT NULL
            ORDER BY seconds
            """
        )
        duration_rows = await duration_cursor.fetchall()

    by_status = {row["status"]: int(row["count"]) for row in status_rows}
    total = int(total_row["total"] if total_row else 0)
    done = by_status.get(TaskStatus.done.value, 0)
    failed = by_status.get(TaskStatus.failed.value, 0)
    durations = [int(row["seconds"]) for row in duration_rows if row["seconds"] is not None]
    median_seconds = durations[len(durations) // 2] if durations else 0
    if durations:
        p95_index = min(len(durations) - 1, int(round((len(durations) - 1) * 0.95)))
        p95_seconds = durations[p95_index]
    else:
        p95_seconds = 0

    return {
        "total": total,
        "done": done,
        "failed": failed,
        "awaiting_manual": by_status.get(TaskStatus.awaiting_manual.value, 0),
        "median_seconds": median_seconds,
        "p95_seconds": p95_seconds,
        "success_rate_pct": round(done / total * 100, 2) if total else 0.0,
        "by_status": by_status,
    }
