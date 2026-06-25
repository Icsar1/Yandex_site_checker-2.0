from __future__ import annotations

import asyncio
from pathlib import Path

import arq
import pytest

from app.config import Settings
from app.db.database import get_db
from app.models.task import TaskCreate, TaskStatus
from app.services.direct import CaptchaOrAuthError, DirectTimeoutError
from app.services.tasks import create_task, get_task, update_task_status
from app.worker import pipeline
from app.worker.pipeline import load_artifact, run_task_pipeline, save_artifact


class DummyRetry(Exception):
    def __init__(self, defer: float) -> None:
        super().__init__(defer)
        self.defer = defer


@pytest.fixture(autouse=True)
def patch_redis_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    async def no_progress(
        redis_url: str,
        task_id: str,
        status: str,
        sub_progress: float = 0.0,
        ttl: int = 3600,
        needs_manual: bool = False,
    ) -> None:
        return None

    monkeypatch.setattr(pipeline, "set_progress", no_progress)


@pytest.fixture
def pipeline_settings(settings: Settings, tmp_db: Path) -> Settings:
    return settings.model_copy(
        update={
            "DATABASE_PATH": str(tmp_db),
            "PDF_OUTPUT_DIR": str(tmp_db.parent / "pdf"),
            "MOCK_YANDEX": True,
        }
    )


async def _artifact_row(db_path: Path, task_id: str, kind: str) -> dict | None:
    async with get_db(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT kind, payload, path FROM artifacts WHERE task_id = ? AND kind = ?",
            (task_id, kind),
        )
        row = await cursor.fetchone()
    return dict(row) if row is not None else None


async def _artifact_kinds(db_path: Path, task_id: str) -> set[str]:
    async with get_db(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT kind FROM artifacts WHERE task_id = ?",
            (task_id,),
        )
        rows = await cursor.fetchall()
    return {str(row["kind"]) for row in rows}


def _sample_keywords() -> list[dict]:
    return [{"phrase": "dentistry price", "freq": 100, "score": 1.0}]


def _sample_forecast() -> list[dict]:
    return [
        {
            "phrase": "dentistry price",
            "impressions": 1000,
            "clicks": 50,
            "spending": 2500,
            "ctr": 5.0,
            "avg_cpc": 50,
            "avg_cpm": 2500,
            "avg_bid": 55,
        }
    ]


@pytest.mark.asyncio
async def test_pipeline_happy_path_mock(
    tmp_db: Path,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))

    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.done.value
    assert task["download_token"]

    keywords = await load_artifact(str(tmp_db), task_id, "keywords")
    forecast = await load_artifact(str(tmp_db), task_id, "forecast")
    report = await load_artifact(str(tmp_db), task_id, "report_json")
    pdf_row = await _artifact_row(tmp_db, task_id, "pdf")

    assert isinstance(keywords, list) and keywords
    assert isinstance(forecast, list) and forecast
    assert isinstance(report, dict) and report
    assert pdf_row is not None
    assert pdf_row["path"]
    assert Path(pdf_row["path"]).exists()
    assert await _artifact_kinds(tmp_db, task_id) == {
        "keywords",
        "forecast",
        "report_json",
        "pdf",
    }


@pytest.mark.asyncio
async def test_pipeline_idempotent_skips_existing_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db: Path,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    await save_artifact(str(tmp_db), task_id, "keywords", _sample_keywords())
    await save_artifact(str(tmp_db), task_id, "forecast", _sample_forecast())

    async def fail_wordstat(self: object, query: str, region_ids: list[int] | None = None) -> list[dict]:
        raise AssertionError("wordstat should not be called")

    async def fail_direct(
        self: object,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: object | None = None,
    ) -> list[dict]:
        raise AssertionError("direct should not be called")

    monkeypatch.setattr(pipeline.MockWordstatClient, "top_requests", fail_wordstat)
    monkeypatch.setattr(pipeline.MockDirectForecastClient, "forecast_keywords", fail_direct)

    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.done.value
    assert await load_artifact(str(tmp_db), task_id, "report_json")


@pytest.mark.asyncio
async def test_pipeline_permanent_error_sets_failed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db: Path,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    monkeypatch.setattr(pipeline, "select_keywords", lambda *args, **kwargs: [])

    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.failed.value
    assert task["error_class"] == "permanent"


@pytest.mark.asyncio
async def test_pipeline_transient_error_raises_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_db: Path,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    await save_artifact(str(tmp_db), task_id, "keywords", _sample_keywords())
    monkeypatch.setattr(arq, "Retry", DummyRetry)

    async def raise_timeout(
        self: object,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: object | None = None,
    ) -> list[dict]:
        raise DirectTimeoutError("timeout")

    monkeypatch.setattr(pipeline.MockDirectForecastClient, "forecast_keywords", raise_timeout)

    with pytest.raises(DummyRetry):
        await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.failed.value
    assert task["error_class"] == "transient"


@pytest.mark.asyncio
async def test_pipeline_needs_manual_sets_awaiting(
    tmp_db: Path,
    monkeypatch: pytest.MonkeyPatch,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    await save_artifact(str(tmp_db), task_id, "keywords", _sample_keywords())

    async def raise_captcha(
        self: object,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: object | None = None,
    ) -> list[dict]:
        raise CaptchaOrAuthError("captcha")

    monkeypatch.setattr(pipeline.MockDirectForecastClient, "forecast_keywords", raise_captcha)

    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.awaiting_manual.value


@pytest.mark.asyncio
async def test_pipeline_canceled_task_exits_early(
    tmp_db: Path,
    pipeline_settings: Settings,
) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    await update_task_status(str(tmp_db), task_id, TaskStatus.canceled)

    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.canceled.value


@pytest.mark.asyncio
async def test_load_artifact_returns_none_when_missing(tmp_db: Path) -> None:
    assert await load_artifact(str(tmp_db), "missing-task", "keywords") is None


@pytest.mark.asyncio
async def test_save_and_load_artifact_roundtrip(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    data = [{"phrase": "dentistry price", "freq": 100}]

    await save_artifact(str(tmp_db), task_id, "keywords", data)

    assert await load_artifact(str(tmp_db), task_id, "keywords") == data


@pytest.mark.asyncio
async def test_save_artifact_upsert_overwrites(tmp_db: Path) -> None:
    task_id = await create_task(str(tmp_db), TaskCreate(niche="dentistry", region_ids=[213]))
    data1 = [{"phrase": "old", "freq": 1}]
    data2 = [{"phrase": "new", "freq": 2}]

    await save_artifact(str(tmp_db), task_id, "keywords", data1)
    await save_artifact(str(tmp_db), task_id, "keywords", data2)

    assert await load_artifact(str(tmp_db), task_id, "keywords") == data2


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "_direct_semaphore", None)
    semaphore = pipeline.get_direct_semaphore(concurrency=2)
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal active, max_active
        async with semaphore:
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            async with lock:
                active -= 1

    await asyncio.gather(worker(), worker(), worker())

    assert max_active == 2
