from __future__ import annotations

import json

from redis.asyncio import Redis

from app.models.task import ProgressResponse

STAGE_MAP = {
    "queued": {
        "step": 1,
        "percent_range": (0, 10),
        "label": "Ожидание в очереди...",
    },
    "collecting_keys": {
        "step": 1,
        "percent_range": (10, 25),
        "label": "Собираем коммерческие запросы по нише...",
    },
    "forecasting": {
        "step": 2,
        "percent_range": (25, 55),
        "label": "Считаем прогноз бюджета в Директе...",
    },
    "awaiting_manual": {
        "step": 2,
        "percent_range": (25, 25),
        "label": "Готовим прогноз вручную...",
    },
    "generating_text": {
        "step": 3,
        "percent_range": (55, 80),
        "label": "AI формирует медиаплан...",
    },
    "rendering_pdf": {
        "step": 4,
        "percent_range": (80, 95),
        "label": "Верстаем брендированный отчёт...",
    },
    "done": {
        "step": 5,
        "percent_range": (100, 100),
        "label": "Готово! Скачайте медиаплан",
    },
    "failed": {
        "step": 0,
        "percent_range": (0, 0),
        "label": "Не удалось завершить...",
    },
    "canceled": {
        "step": 0,
        "percent_range": (0, 0),
        "label": "Отменено",
    },
}


def build_progress_response(
    status: str,
    sub_progress: float = 0.0,
    needs_manual: bool = False,
) -> ProgressResponse:
    stage = STAGE_MAP.get(status, STAGE_MAP["queued"])
    start, end = stage["percent_range"]
    bounded_progress = min(1.0, max(0.0, sub_progress))
    percent = int(round(start + (end - start) * bounded_progress))

    return ProgressResponse(
        stage=status,
        step=stage["step"],
        percent=percent,
        label=stage["label"],
        terminal=status in {"done", "failed", "canceled"},
        needs_manual=needs_manual or status == "awaiting_manual",
    )


async def set_progress(
    redis_url: str,
    task_id: str,
    status: str,
    sub_progress: float = 0.0,
    ttl: int = 3600,
    needs_manual: bool = False,
) -> None:
    progress = build_progress_response(status, sub_progress, needs_manual)
    redis_client = Redis.from_url(redis_url)
    try:
        await redis_client.set(
            f"task:{task_id}:progress",
            progress.model_dump_json(),
            ex=ttl,
        )
    finally:
        await redis_client.aclose()


async def get_progress(redis_url: str, task_id: str) -> ProgressResponse | None:
    redis_client = Redis.from_url(redis_url)
    try:
        raw_value = await redis_client.get(f"task:{task_id}:progress")
    finally:
        await redis_client.aclose()

    if raw_value is None:
        return None

    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")

    return ProgressResponse.model_validate(json.loads(raw_value))
