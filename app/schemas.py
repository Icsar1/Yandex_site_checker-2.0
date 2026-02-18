from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class MediaPlanRequest(BaseModel):
    niche: str = Field(min_length=2, max_length=200)
    region: str = Field(min_length=2, max_length=200)
    monthly_budget: float | None = Field(default=None, gt=0)
    campaign_goal: str | None = Field(default=None, max_length=500)

    @field_validator("niche", "region")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Поле обязательно для заполнения")
        return cleaned

    @field_validator("campaign_goal")
    @classmethod
    def validate_optional_goal(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class KeywordStat(BaseModel):
    phrase: str
    frequency: int = Field(ge=0)
    match_type: str | None = None
    priority: Literal["high", "medium", "low"]


class SummaryMetrics(BaseModel):
    total_keywords: int
    total_frequency: int
    avg_frequency: float
    budget_distribution: dict[str, float] | None = None


class MediaPlanResult(BaseModel):
    input_data: MediaPlanRequest
    created_at: datetime
    keywords: list[KeywordStat]
    summary: SummaryMetrics
