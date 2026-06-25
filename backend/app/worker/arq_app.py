from __future__ import annotations

import logging
from urllib.parse import urlparse

from arq.connections import RedisSettings

from app.config import get_settings
from app.worker.pipeline import run_task_pipeline

logger = logging.getLogger(__name__)
settings = get_settings()


async def run_pipeline(ctx: dict, task_id: str) -> None:
    settings = get_settings()
    await run_task_pipeline(task_id, settings)


async def startup(ctx: dict) -> None:
    """Re-enqueue orphaned tasks that are still in queued/processing states."""
    s = get_settings()
    try:
        from app.db.database import get_db

        async with get_db(s.DATABASE_PATH) as db:
            cursor = await db.execute(
                "SELECT id FROM tasks WHERE status IN ('queued', 'collecting_keys', 'forecasting', 'generating_text', 'rendering_pdf') AND started_at IS NULL"
            )
            rows = await cursor.fetchall()

        if rows:
            pool = ctx.get("redis")
            if pool is None:
                from arq import create_pool
                pool = await create_pool(_redis_settings_from_url(s.REDIS_URL))
            for row in rows:
                task_id = row["id"]
                logger.info("Re-enqueuing orphaned task %s", task_id)
                await pool.enqueue_job("run_pipeline", task_id)
    except Exception as exc:
        logger.error("Startup sweep failed: %s", exc)


def _redis_settings_from_url(redis_url: str) -> RedisSettings:
    parsed = urlparse(redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        database=int((parsed.path or "/0").strip("/") or "0"),
        password=parsed.password,
        ssl=parsed.scheme == "rediss",
    )


class WorkerSettings:
    functions = [run_pipeline]
    on_startup = startup
    redis_settings = _redis_settings_from_url(settings.REDIS_URL)
    max_jobs = settings.ARQ_MAX_JOBS
