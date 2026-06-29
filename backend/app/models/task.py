from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    queued = "queued"
    collecting_keys = "collecting_keys"
    forecasting = "forecasting"
    awaiting_manual = "awaiting_manual"
    generating_text = "generating_text"
    rendering_pdf = "rendering_pdf"
    done = "done"
    failed = "failed"
    canceled = "canceled"


TERMINAL_STATUSES = {
    TaskStatus.done,
    TaskStatus.failed,
    TaskStatus.canceled,
}


class TaskSource(str, Enum):
    auto = "auto"
    manual_xls = "manual_xls"


class MaskRequest(BaseModel):
    niche: str = Field(min_length=1, max_length=300)


class MaskResponse(BaseModel):
    masks: list[str]


class TaskCreate(BaseModel):
    niche: str = Field(min_length=1)
    region_ids: list[int] = Field(min_length=1)
    contact: str | None = None
    masks: list[str] | None = None

    @field_validator("masks", mode="before")
    @classmethod
    def clean_masks(cls, v):
        if v is None:
            return None
        cleaned: dict = {}
        for m in v:
            m = str(m).strip()[:100]
            if m:
                cleaned[m] = None
        result = list(cleaned.keys())[:20]
        return result or None


class TaskResponse(BaseModel):
    id: str
    niche: str
    region_ids: list[int]
    region_label: str
    contact: str | None
    status: TaskStatus
    stage: str | None
    progress_pct: int
    error_class: str | None
    error_message: str | None
    suggested_niche: str | None = None
    search_masks: list[str] | None = None
    download_url: str | None
    source: TaskSource
    created_at: str
    updated_at: str


class ProgressResponse(BaseModel):
    stage: str | None
    step: int
    total_steps: int = 5
    percent: int
    label: str
    terminal: bool
    needs_manual: bool = False
