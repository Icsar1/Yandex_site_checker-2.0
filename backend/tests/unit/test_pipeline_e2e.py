from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient
import pytest

from app.config import Settings
from app.db.database import get_db
from app.models.task import TaskStatus
from app.services.tasks import get_task
from app.worker import pipeline
from app.worker.pipeline import run_task_pipeline, save_artifact


@pytest.fixture(autouse=True)
def disable_arq_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    import arq.connections

    async def fail_create_pool(redis_settings: object) -> object:
        raise ConnectionError("redis unavailable in tests")

    monkeypatch.setattr(arq.connections, "create_pool", fail_create_pool)


@pytest.fixture
def recorded_progress(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    async def record_progress(
        redis_url: str,
        task_id: str,
        status: str,
        sub_progress: float = 0.0,
        ttl: int = 3600,
        needs_manual: bool = False,
    ) -> None:
        calls.append(
            {
                "task_id": task_id,
                "status": status,
                "sub_progress": sub_progress,
                "needs_manual": needs_manual,
            }
        )

    monkeypatch.setattr(pipeline, "set_progress", record_progress)
    return calls


def _pipeline_settings(settings: Settings, tmp_db: Path) -> Settings:
    return settings.model_copy(
        update={
            "DATABASE_PATH": str(tmp_db),
            "PDF_OUTPUT_DIR": str(tmp_db.parent / "pdf"),
            "MOCK_YANDEX": True,
        }
    )


async def _artifact_kinds(db_path: Path, task_id: str) -> set[str]:
    async with get_db(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT kind FROM artifacts WHERE task_id = ?",
            (task_id,),
        )
        rows = await cursor.fetchall()
    return {str(row["kind"]) for row in rows}


async def _pdf_path(db_path: Path, task_id: str) -> Path:
    async with get_db(str(db_path)) as db:
        cursor = await db.execute(
            "SELECT path FROM artifacts WHERE task_id = ? AND kind = 'pdf'",
            (task_id,),
        )
        row = await cursor.fetchone()
    assert row is not None
    return Path(str(row["path"]))


def _sample_keywords() -> list[dict]:
    return [{"phrase": "ceilings price", "freq": 100, "score": 1.0}]


def _sample_forecast() -> list[dict]:
    return [
        {
            "phrase": "ceilings price",
            "impressions": 1200,
            "clicks": 60,
            "spending": 3000,
            "ctr": 5.0,
            "avg_cpc": 50,
            "avg_cpm": 2500,
            "avg_bid": 60,
        }
    ]


@pytest.mark.asyncio
async def test_e2e_happy_path_creates_pdf_with_correct_data(
    client: AsyncClient,
    tmp_db: Path,
    settings: Settings,
    recorded_progress: list[dict],
) -> None:
    response = await client.post(
        "/api/tasks",
        json={
            "niche": "\u043d\u0430\u0442\u044f\u0436\u043d\u044b\u0435 \u043f\u043e\u0442\u043e\u043b\u043a\u0438",
            "region_ids": [213],
        },
    )
    assert response.status_code == 201
    task_id = response.json()["task_id"]

    await run_task_pipeline(task_id, _pipeline_settings(settings, tmp_db))

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.done.value
    assert task["download_token"]
    assert task["finished_at"]

    pdf_path = await _pdf_path(tmp_db, task_id)
    assert pdf_path.exists()
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert await _artifact_kinds(tmp_db, task_id) == {
        "keywords",
        "forecast",
        "report_json",
        "pdf",
    }

    progress_stages = {call["status"] for call in recorded_progress}
    assert {
        "collecting_keys",
        "forecasting",
        "generating_text",
        "rendering_pdf",
        "done",
    }.issubset(progress_stages)


@pytest.mark.asyncio
async def test_e2e_idempotent_retry_no_duplicate_calls(
    client: AsyncClient,
    tmp_db: Path,
    settings: Settings,
    recorded_progress: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = await client.post(
        "/api/tasks",
        json={"niche": "ceilings", "region_ids": [213]},
    )
    assert response.status_code == 201
    task_id = response.json()["task_id"]
    await save_artifact(str(tmp_db), task_id, "keywords", _sample_keywords())
    await save_artifact(str(tmp_db), task_id, "forecast", _sample_forecast())

    original_generate_report_mock = pipeline.generate_report_mock
    report_calls = 0

    async def counted_generate_report_mock(
        niche: str,
        region: str,
        keywords: list[dict],
        forecast: list[dict],
    ) -> dict:
        nonlocal report_calls
        report_calls += 1
        return await original_generate_report_mock(niche, region, keywords, forecast)

    async def fail_direct(
        self: object,
        keywords: list[dict],
        region_id: int,
        batch_size: int = 100,
        on_batch: object | None = None,
    ) -> list[dict]:
        raise AssertionError("direct should not be called when forecast exists")

    monkeypatch.setattr(pipeline, "generate_report_mock", counted_generate_report_mock)
    monkeypatch.setattr(pipeline.MockDirectForecastClient, "forecast_keywords", fail_direct)

    pipeline_settings = _pipeline_settings(settings, tmp_db)
    await run_task_pipeline(task_id, pipeline_settings)
    await run_task_pipeline(task_id, pipeline_settings)

    task = await get_task(str(tmp_db), task_id)
    assert task is not None
    assert task["status"] == TaskStatus.done.value
    assert report_calls == 1
