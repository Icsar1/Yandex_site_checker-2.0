from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.db.database import get_db
from app.models.task import TERMINAL_STATUSES, TaskStatus
from app.services.ai import generate_report
from app.services.ai_mock import generate_report_mock
from app.services.direct import (
    CaptchaOrAuthError,
    DirectError,
    DirectForecastClient,
    DirectTimeoutError,
)
from app.services.direct_api import DirectApiClient, DirectApiError
from app.services.direct_mock import MockDirectForecastClient
from app.services.keywords import select_keywords
from app.services.pdf import render_pdf
from app.services.pdf_mock import render_pdf_mock
from app.services.progress import set_progress
from app.services.spellcheck import suggest_correction
from app.services.tasks import (
    add_task_event,
    can_transition,
    generate_download_token,
    get_task,
    set_suggested_niche,
    update_task_status,
)
from app.services.wordstat import WordstatClient
from app.services.wordstat_mock import MockWordstatClient


class PipelineError(Exception):
    """Base pipeline error."""


class TransientError(PipelineError):
    """Auto-retryable: timeouts, 429, 5xx."""


class PermanentError(PipelineError):
    """No retry: 401, 0 phrases, schema errors."""


class NeedsManualError(PipelineError):
    """Captcha/auth -> awaiting_manual."""


_direct_semaphore: asyncio.Semaphore | None = None


def get_direct_semaphore(concurrency: int = 3) -> asyncio.Semaphore:
    global _direct_semaphore
    if _direct_semaphore is None:
        _direct_semaphore = asyncio.Semaphore(concurrency)
    return _direct_semaphore


async def load_artifact(db_path: str, task_id: str, kind: str) -> dict | list | None:
    """Load artifact payload from DB. Returns parsed JSON or None."""
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT payload FROM artifacts WHERE task_id = ? AND kind = ?",
            (task_id, kind),
        )
        row = await cursor.fetchone()
    if row is None or not row["payload"]:
        return None
    return json.loads(row["payload"])


async def save_artifact(
    db_path: str,
    task_id: str,
    kind: str,
    payload: Any,
    path: str | None = None,
) -> None:
    """Save artifact with UPSERT for idempotency."""
    payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
    async with get_db(db_path) as db:
        await db.execute(
            """
            INSERT INTO artifacts (task_id, kind, payload, path)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(task_id, kind) DO UPDATE SET
                payload = excluded.payload,
                path = excluded.path
            """,
            (task_id, kind, payload_json, path),
        )
        await db.commit()


async def run_task_pipeline(task_id: str, settings: Settings) -> None:
    attempts = 0
    try:
        task = await _prepare_task_for_run(settings.DATABASE_PATH, task_id, settings)
        if task is None:
            return

        attempts = await _increment_attempts(settings.DATABASE_PATH, task_id)
        await _run_task_pipeline_steps(task_id, settings)
    except TransientError as exc:
        await _handle_transient_error(task_id, settings, attempts, exc)
    except PermanentError as exc:
        await _set_failed(task_id, settings, "permanent", str(exc))
    except NeedsManualError as exc:
        if await _transition_if_allowed(
            settings.DATABASE_PATH,
            task_id,
            TaskStatus.awaiting_manual,
        ):
            await add_task_event(
                settings.DATABASE_PATH,
                task_id,
                event="pipeline_needs_manual",
                stage=TaskStatus.awaiting_manual.value,
                message=str(exc),
                level="warning",
            )
            await set_progress(
                settings.REDIS_URL,
                task_id,
                TaskStatus.awaiting_manual.value,
                0.0,
                settings.PROGRESS_TTL_SECONDS,
                needs_manual=True,
            )
    except Exception as exc:
        await _set_failed(task_id, settings, "unknown", str(exc))


async def _run_task_pipeline_steps(task_id: str, settings: Settings) -> None:
    task = await _active_task(settings.DATABASE_PATH, task_id)
    if task is None:
        return

    niche = str(task["niche"])
    region_ids = list(task.get("region_ids") or [])
    search_masks = [m for m in (task.get("search_masks") or []) if m and m.strip()]
    if not region_ids:
        raise PermanentError("Task has no region_ids")
    region_id = int(region_ids[0])
    region = str(task.get("region_label") or region_id)

    keywords = await _collect_keywords(
        task_id,
        settings,
        niche,
        region_ids,
        search_masks=search_masks,
    )
    if keywords is None:
        return

    forecast = await _build_forecast(task_id, settings, keywords, region_id)
    if forecast is None:
        return

    report_result = await _build_report(task_id, settings, niche, region, keywords, forecast)
    if report_result is None:
        return

    if not await _render_report_pdf(task_id, settings, niche, region, report_result):
        return

    await generate_download_token(
        settings.DATABASE_PATH,
        task_id,
        settings.PDF_TOKEN_TTL_SECONDS,
    )
    if not await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.done,
    ):
        return
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.done.value,
        1.0,
        settings.PROGRESS_TTL_SECONDS,
    )
    await add_task_event(
        settings.DATABASE_PATH,
        task_id,
        event="pipeline_completed",
        stage=TaskStatus.done.value,
    )


async def _collect_keywords(
    task_id: str,
    settings: Settings,
    niche: str,
    region_ids: list[int],
    search_masks: list[str] | None = None,
) -> list[dict] | None:
    keywords = await load_artifact(settings.DATABASE_PATH, task_id, "keywords")
    if keywords is not None:
        await _mark_stage_reached(settings, task_id, TaskStatus.collecting_keys)
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.collecting_keys.value,
            1.0,
            settings.PROGRESS_TTL_SECONDS,
        )
        return list(keywords)

    if not await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.collecting_keys,
    ):
        return None
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.collecting_keys.value,
        0.0,
        settings.PROGRESS_TTL_SECONDS,
    )

    client = (
        MockWordstatClient()
        if settings.MOCK_YANDEX
        else WordstatClient(
            api_key=settings.WORDSTAT_API_KEY.get_secret_value(),
            folder_id=settings.WORDSTAT_FOLDER_ID,
        )
    )
    masks = [m for m in (search_masks or []) if m and m.strip()] or [niche]
    raw_keywords: list[dict[str, int | str]] = []
    first_error: PipelineError | None = None
    for mask in masks:
        try:
            chunk = await client.top_requests(mask, region_ids)
            raw_keywords.extend(chunk)
        except httpx.HTTPStatusError as exc:
            err = _classify_http_status_error(exc)
            if first_error is None:
                first_error = err
        except httpx.RequestError as exc:
            if first_error is None:
                first_error = TransientError(str(exc))
        except RuntimeError as exc:
            classified = _classify_runtime_error(exc)
            if classified is not None and first_error is None:
                first_error = classified
            elif classified is None:
                raise
    if not raw_keywords and first_error is not None:
        raise first_error
    niche_context = " ".join(masks)
    selected = select_keywords(
        raw_keywords,
        min_freq=settings.WORDSTAT_MIN_FREQ,
        max_keywords=settings.MAX_KEYWORDS,
        niche=niche_context,
    )
    if not selected:
        suggestion = await suggest_correction(niche)
        if suggestion:
            await set_suggested_niche(settings.DATABASE_PATH, task_id, suggestion)
        raise PermanentError(
            f"Не найдено ключевых слов для ниши «{niche}». "
            "Проверьте правильность написания."
        )

    await save_artifact(settings.DATABASE_PATH, task_id, "keywords", selected)
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.collecting_keys.value,
        1.0,
        settings.PROGRESS_TTL_SECONDS,
    )
    return selected


async def _build_forecast(
    task_id: str,
    settings: Settings,
    keywords: list[dict],
    region_id: int,
) -> list[dict] | None:
    forecast = await load_artifact(settings.DATABASE_PATH, task_id, "forecast")
    if forecast is not None:
        await _mark_stage_reached(settings, task_id, TaskStatus.forecasting)
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.forecasting.value,
            1.0,
            settings.PROGRESS_TTL_SECONDS,
        )
        return list(forecast)

    if not await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.forecasting,
    ):
        return None
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.forecasting.value,
        0.0,
        settings.PROGRESS_TTL_SECONDS,
    )

    if settings.MOCK_YANDEX:
        client: Any = MockDirectForecastClient()
    elif settings.YANDEX_DIRECT_API_KEY.get_secret_value():
        client = DirectApiClient(
            api_key=settings.YANDEX_DIRECT_API_KEY.get_secret_value(),
            login=settings.YANDEX_DIRECT_LOGIN.get_secret_value() or "",
        )
    else:
        client = DirectForecastClient(
            storage_state_path=settings.DIRECT_STORAGE_STATE,
            forecast_url=settings.DIRECT_FORECAST_URL,
            headless=settings.PLAYWRIGHT_HEADLESS,
            timeout_ms=settings.DIRECT_TIMEOUT_MS,
        )

    async def on_batch(batch_index: int, total_batches: int) -> None:
        sub_progress = batch_index / total_batches if total_batches else 1.0
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.forecasting.value,
            sub_progress,
            settings.PROGRESS_TTL_SECONDS,
        )

    sem = get_direct_semaphore(settings.CONCURRENCY)
    try:
        async with sem:
            forecast_result = await client.forecast_keywords(
                keywords,
                region_id,
                batch_size=settings.DIRECT_BATCH_SIZE,
                on_batch=on_batch,
            )
    except CaptchaOrAuthError as exc:
        raise NeedsManualError(str(exc)) from exc
    except DirectApiError as exc:
        raise TransientError(str(exc)) from exc
    except DirectTimeoutError as exc:
        raise TransientError(str(exc)) from exc
    except DirectError as exc:
        raise NeedsManualError(str(exc)) from exc

    await save_artifact(settings.DATABASE_PATH, task_id, "forecast", forecast_result)
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.forecasting.value,
        1.0,
        settings.PROGRESS_TTL_SECONDS,
    )
    return forecast_result


async def _build_report(
    task_id: str,
    settings: Settings,
    niche: str,
    region: str,
    keywords: list[dict],
    forecast: list[dict],
) -> dict | None:
    report_result = await load_artifact(settings.DATABASE_PATH, task_id, "report_json")
    if report_result is not None:
        await _mark_stage_reached(settings, task_id, TaskStatus.generating_text)
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.generating_text.value,
            1.0,
            settings.PROGRESS_TTL_SECONDS,
        )
        return dict(report_result)

    if not await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.generating_text,
    ):
        return None
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.generating_text.value,
        0.0,
        settings.PROGRESS_TTL_SECONDS,
    )

    try:
        result = (
            await generate_report_mock(niche, region, keywords, forecast)
            if settings.MOCK_YANDEX
            else await generate_report(
                niche,
                region,
                keywords,
                forecast,
                base_url=settings.YANDEX_GPT_BASE_URL,
                api_key=settings.YANDEX_GPT_API_KEY.get_secret_value(),
                folder_id=settings.YANDEX_GPT_FOLDER_ID,
                model=settings.YANDEX_GPT_MODEL,
                temperature=settings.YANDEX_GPT_TEMPERATURE,
                timeout=settings.YANDEX_GPT_TIMEOUT_S,
            )
        )
    except httpx.HTTPStatusError as exc:
        raise _classify_http_status_error(exc) from exc
    except httpx.RequestError as exc:
        raise TransientError(str(exc)) from exc
    except RuntimeError as exc:
        classified = _classify_runtime_error(exc)
        if classified is not None:
            raise classified from exc
        raise

    await save_artifact(settings.DATABASE_PATH, task_id, "report_json", result)
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.generating_text.value,
        1.0,
        settings.PROGRESS_TTL_SECONDS,
    )
    return result


async def _render_report_pdf(
    task_id: str,
    settings: Settings,
    niche: str,
    region: str,
    report_result: dict,
) -> bool:
    pdf_path = await _load_pdf_path(settings.DATABASE_PATH, task_id)
    if pdf_path and Path(pdf_path).exists():
        await _mark_stage_reached(settings, task_id, TaskStatus.rendering_pdf)
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.rendering_pdf.value,
            1.0,
            settings.PROGRESS_TTL_SECONDS,
        )
        return True

    if not await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.rendering_pdf,
    ):
        return False
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.rendering_pdf.value,
        0.0,
        settings.PROGRESS_TTL_SECONDS,
    )

    output_path = str(Path(settings.PDF_OUTPUT_DIR) / f"{task_id}.pdf")
    report = dict(report_result.get("report") or {})
    aggregates = dict(report_result.get("aggregates") or {})

    rendered_path = (
        await render_pdf_mock(niche, region, report, aggregates, output_path)
        if settings.MOCK_YANDEX
        else await render_pdf(
            niche,
            region,
            report,
            aggregates,
            output_path,
            headless=settings.PLAYWRIGHT_HEADLESS,
        )
    )
    await save_artifact(settings.DATABASE_PATH, task_id, "pdf", None, path=rendered_path)
    await set_progress(
        settings.REDIS_URL,
        task_id,
        TaskStatus.rendering_pdf.value,
        1.0,
        settings.PROGRESS_TTL_SECONDS,
    )
    return True


async def _prepare_task_for_run(
    db_path: str,
    task_id: str,
    settings: Settings,
) -> dict[str, Any] | None:
    task = await get_task(db_path, task_id)
    if task is None:
        return None

    status = TaskStatus(task["status"])
    if status == TaskStatus.failed and task.get("error_class") == "transient":
        if int(task.get("attempts") or 0) < settings.MAX_ATTEMPTS:
            if can_transition(status, TaskStatus.queued):
                await update_task_status(db_path, task_id, TaskStatus.queued)
                task = await get_task(db_path, task_id)
                return task
        return None

    if status in TERMINAL_STATUSES:
        return None

    valid_statuses = {
        TaskStatus.queued,
        TaskStatus.collecting_keys,
        TaskStatus.forecasting,
        TaskStatus.awaiting_manual,
        TaskStatus.generating_text,
        TaskStatus.rendering_pdf,
    }
    if status not in valid_statuses:
        return None
    return task


async def _increment_attempts(db_path: str, task_id: str) -> int:
    async with get_db(db_path) as db:
        await db.execute(
            "UPDATE tasks SET attempts = attempts + 1 WHERE id = ?",
            (task_id,),
        )
        cursor = await db.execute(
            "SELECT attempts FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = await cursor.fetchone()
        await db.commit()
    return int(row["attempts"] if row is not None else 0)


async def _active_task(db_path: str, task_id: str) -> dict[str, Any] | None:
    task = await get_task(db_path, task_id)
    if task is None:
        return None
    status = TaskStatus(task["status"])
    if status in TERMINAL_STATUSES:
        return None
    return task


async def _transition_if_allowed(
    db_path: str,
    task_id: str,
    new_status: TaskStatus,
    error_class: str | None = None,
    error_message: str | None = None,
) -> bool:
    task = await get_task(db_path, task_id)
    if task is None:
        return False

    current_status = TaskStatus(task["status"])
    if current_status == new_status:
        return True
    if current_status in TERMINAL_STATUSES:
        return False
    if not can_transition(current_status, new_status):
        return False

    return await update_task_status(
        db_path,
        task_id,
        new_status,
        error_class=error_class,
        error_message=error_message,
    )


async def _mark_stage_reached(
    settings: Settings,
    task_id: str,
    stage: TaskStatus,
) -> bool:
    task = await get_task(settings.DATABASE_PATH, task_id)
    if task is None:
        return False

    current_status = TaskStatus(task["status"])
    if current_status in TERMINAL_STATUSES:
        return False
    if current_status == stage:
        return True
    if _stage_rank(current_status) >= _stage_rank(stage):
        return True
    return await _transition_if_allowed(settings.DATABASE_PATH, task_id, stage)


def _stage_rank(status: TaskStatus) -> int:
    ranks = {
        TaskStatus.queued: 0,
        TaskStatus.collecting_keys: 1,
        TaskStatus.forecasting: 2,
        TaskStatus.awaiting_manual: 2,
        TaskStatus.generating_text: 3,
        TaskStatus.rendering_pdf: 4,
        TaskStatus.done: 5,
    }
    return ranks.get(status, -1)


async def _load_pdf_path(db_path: str, task_id: str) -> str | None:
    async with get_db(db_path) as db:
        cursor = await db.execute(
            "SELECT path FROM artifacts WHERE task_id = ? AND kind = 'pdf'",
            (task_id,),
        )
        row = await cursor.fetchone()
    if row is None or not row["path"]:
        return None
    return str(row["path"])


async def _set_failed(
    task_id: str,
    settings: Settings,
    error_class: str,
    message: str,
) -> None:
    if await _transition_if_allowed(
        settings.DATABASE_PATH,
        task_id,
        TaskStatus.failed,
        error_class=error_class,
        error_message=message,
    ):
        await add_task_event(
            settings.DATABASE_PATH,
            task_id,
            event="pipeline_failed",
            stage=TaskStatus.failed.value,
            message=message,
            level="error",
            meta={"error_class": error_class},
        )
        await set_progress(
            settings.REDIS_URL,
            task_id,
            TaskStatus.failed.value,
            0.0,
            settings.PROGRESS_TTL_SECONDS,
        )


async def _handle_transient_error(
    task_id: str,
    settings: Settings,
    attempts: int,
    exc: TransientError,
) -> None:
    await _set_failed(task_id, settings, "transient", str(exc))
    if attempts < settings.MAX_ATTEMPTS:
        from arq import Retry

        attempt_number = max(1, attempts)
        delay = min(settings.RETRY_BASE_SECONDS * (2 ** (attempt_number - 1)), 60)
        jitter = random.uniform(-2, 2)
        raise Retry(defer=max(1, delay + jitter)) from exc


def _classify_http_status_error(exc: httpx.HTTPStatusError) -> PipelineError:
    status_code = exc.response.status_code
    if status_code == 429 or status_code >= 500:
        return TransientError(str(exc))
    return PermanentError(str(exc))


def _classify_runtime_error(exc: RuntimeError) -> PipelineError | None:
    message = str(exc)
    status_code = _extract_status_code(message)
    if status_code is not None:
        if status_code == 429 or status_code >= 500:
            return TransientError(message)
        if 400 <= status_code < 500:
            return PermanentError(message)

    lowered = message.casefold()
    if "request failed" in lowered or "timed out" in lowered or "timeout" in lowered:
        return TransientError(message)
    if (
        "invalid json" in lowered
        or "schema" in lowered
        or "does not contain" in lowered
        or "unsupported report content type" in lowered
    ):
        return PermanentError(message)
    return None


def _extract_status_code(message: str) -> int | None:
    match = re.search(r"(?:status\s+|error\s+)(\d{3})", message, flags=re.IGNORECASE)
    if match is None:
        return None
    return int(match.group(1))
