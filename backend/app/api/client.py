from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.db.database import get_db
from app.models.task import (
    MaskRequest,
    MaskResponse,
    ProgressResponse,
    TaskCreate,
    TaskResponse,
    TaskStatus,
)
from app.services.ai import generate_search_masks
from app.services.ai_mock import generate_search_masks_mock
from app.services.progress import build_progress_response, get_progress
from app.services.tasks import (
    add_task_event,
    create_task,
    generate_download_token,
    row_to_task,
)
from app.services.wordstat import WordstatClient
from app.services.wordstat_mock import MockWordstatClient
from app.worker.arq_app import _redis_settings_from_url

router = APIRouter(prefix="/api")


def _get_request_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _get_task_by_id(db_path: str, task_id: str) -> dict[str, Any] | None:
    async with get_db(db_path) as db:
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
    return row_to_task(row)


async def _get_task_by_token_raw(
    db_path: str,
    token: str,
) -> tuple[dict[str, Any] | None, bool]:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE download_token = ?",
            (token,),
        )
        row = await cursor.fetchone()

    task = row_to_task(row)
    if task is None:
        return None, False

    expires_at = task.get("token_expires_at")
    if not expires_at or _parse_utc(expires_at) <= datetime.now(UTC):
        return task, True

    return task, False


async def _get_pdf_path(db_path: str, task_id: str, output_dir: str) -> Path:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT path FROM artifacts WHERE task_id = ? AND kind = 'pdf'",
            (task_id,),
        )
        row = await cursor.fetchone()

    output = Path(output_dir)
    if row is not None and row["path"]:
        p = Path(row["path"])
        if p.is_absolute():
            return p
        # Legacy: relative paths were stored when worker ran from backend/ dir.
        # output_dir is now absolute (project_root/data/pdf), so project_root = output.parents[1].
        project_root = output.parents[1]
        backend_candidate = project_root / "backend" / p
        if backend_candidate.exists():
            return backend_candidate
        return project_root / p
    return output / f"{task_id}.pdf"


async def _resolve_region_label(settings: Settings, region_ids: list[int]) -> str | None:
    if not region_ids:
        return None
    try:
        client = _build_wordstat_client(settings)
        regions = await client.get_regions_tree()
    except Exception:
        return None
    names_by_id = {int(region["id"]): str(region["name"]) for region in regions}
    labels = [names_by_id.get(int(region_id), str(region_id)) for region_id in region_ids]
    label = ", ".join(label for label in labels if label)
    return label or None


def _is_raw_region_id_label(label: str | None, region_ids: list[int]) -> bool:
    expected = ", ".join(str(region_id) for region_id in region_ids)
    return not label or label == expected


async def _build_task_response(
    request: Request,
    settings: Settings,
    task: dict[str, Any],
) -> TaskResponse:
    if _is_raw_region_id_label(task.get("region_label"), task.get("region_ids") or []):
        resolved_region = await _resolve_region_label(settings, task.get("region_ids") or [])
        if resolved_region:
            task["region_label"] = resolved_region

    download_url: str | None = None
    if task["status"] == TaskStatus.done.value:
        token = task.get("download_token")
        if not token:
            token = await generate_download_token(
                settings.DATABASE_PATH,
                task["id"],
                settings.PDF_TOKEN_TTL_SECONDS,
            )
            task["download_token"] = token
        download_url = str(request.url_for("download_pdf", token=token))

    return TaskResponse(**task, download_url=download_url)


@router.get("/regions")
async def get_regions(request: Request, q: str | None = None) -> list[dict[str, int | str]]:
    settings = _get_request_settings(request)
    client = _build_wordstat_client(settings)

    try:
        regions = await client.get_regions_tree()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

    query = (q or "").casefold().strip()
    filtered = [
        {"id": int(region["id"]), "name": str(region["name"])}
        for region in regions
        if not query or query in str(region.get("name") or "").casefold()
    ]
    return filtered[:20]


@router.post("/masks", response_model=MaskResponse)
async def generate_masks(payload: MaskRequest, request: Request) -> MaskResponse:
    settings = _get_request_settings(request)
    if settings.MOCK_YANDEX:
        masks = await generate_search_masks_mock(
            payload.niche,
            max_masks=settings.NICHE_MASKS_MAX,
        )
    else:
        masks = await generate_search_masks(
            niche=payload.niche,
            base_url=settings.YANDEX_GPT_BASE_URL,
            api_key=settings.YANDEX_GPT_API_KEY.get_secret_value(),
            folder_id=settings.YANDEX_GPT_FOLDER_ID,
            model=settings.YANDEX_GPT_MODEL or None,
            temperature=settings.YANDEX_GPT_TEMPERATURE,
            timeout=settings.YANDEX_GPT_TIMEOUT_S,
            max_masks=settings.NICHE_MASKS_MAX,
        )
    if not masks:
        masks = [payload.niche.strip().lower()]
    # Strip AI category prefixes like ".горячие. " regardless of what generate_* returned
    _pfx = __import__("re").compile(r"^\.[^.]+\.\s*")
    masks = [_pfx.sub("", m).strip().lower() for m in masks]
    masks = [m for m in masks if m] or [payload.niche.strip().lower()]
    return MaskResponse(masks=masks)


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_public_task(
    payload: TaskCreate,
    request: Request,
) -> dict[str, str]:
    settings = _get_request_settings(request)
    if _is_raw_region_id_label(payload.region_label, payload.region_ids):
        resolved_region = await _resolve_region_label(settings, payload.region_ids)
        if resolved_region:
            payload = payload.model_copy(update={"region_label": resolved_region})
    task_id = await create_task(settings.DATABASE_PATH, payload)
    await add_task_event(
        settings.DATABASE_PATH,
        task_id,
        event="task_created",
        stage=TaskStatus.queued.value,
    )
    try:
        from arq.connections import create_pool

        redis_settings = _redis_settings_from_url(settings.REDIS_URL)
        pool = await create_pool(redis_settings)
        try:
            await pool.enqueue_job("run_pipeline", task_id)
        finally:
            await pool.aclose()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Failed to enqueue task %s: %s", task_id, exc)
    return {"task_id": task_id, "status": TaskStatus.queued.value}


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_public_task(task_id: str, request: Request) -> TaskResponse:
    settings = _get_request_settings(request)
    task = await _get_task_by_id(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return await _build_task_response(request, settings, task)


@router.get("/tasks/{task_id}/progress", response_model=ProgressResponse)
async def get_public_task_progress(
    task_id: str,
    request: Request,
) -> ProgressResponse:
    settings = _get_request_settings(request)
    task = await _get_task_by_id(settings.DATABASE_PATH, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    try:
        progress = await get_progress(settings.REDIS_URL, task_id)
    except Exception:
        progress = None
    if progress is not None:
        return progress

    return build_progress_response(
        task["status"],
        needs_manual=task["status"] == TaskStatus.awaiting_manual.value,
    )


@router.get("/pdf/{token}", name="download_pdf")
async def download_pdf(token: str, request: Request) -> FileResponse:
    settings = _get_request_settings(request)
    task, expired = await _get_task_by_token_raw(settings.DATABASE_PATH, token)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    if expired:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token expired")

    pdf_path = await _get_pdf_path(settings.DATABASE_PATH, task["id"], settings.PDF_OUTPUT_DIR)
    if not pdf_path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PDF not found")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"mediaplan-{task['id']}.pdf",
    )


def _build_wordstat_client(settings: Settings) -> WordstatClient | MockWordstatClient:
    if settings.MOCK_YANDEX:
        return MockWordstatClient()
    return WordstatClient(
        api_key=settings.WORDSTAT_API_KEY.get_secret_value(),
        folder_id=settings.WORDSTAT_FOLDER_ID,
    )
