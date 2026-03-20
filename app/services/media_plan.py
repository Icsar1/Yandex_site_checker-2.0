from __future__ import annotations

from datetime import datetime

from app.schemas import KeywordStat, MediaPlanRequest, MediaPlanResult, SummaryMetrics
from app.services.wordstat_client import WordstatKeyword


class MediaPlanService:
    def build_plan(self, req: MediaPlanRequest, keywords: list[WordstatKeyword]) -> MediaPlanResult:
        keyword_stats = [
            KeywordStat(
                phrase=item.phrase,
                frequency=item.frequency,
                match_type=item.match_type,
                priority=self._priority(item.frequency),
            )
            for item in sorted(keywords, key=lambda x: x.frequency, reverse=True)
        ]

        total_keywords = len(keyword_stats)
        total_frequency = sum(k.frequency for k in keyword_stats)
        avg_frequency = round(total_frequency / total_keywords, 2) if total_keywords else 0.0

        budget_distribution = None
        if req.monthly_budget is not None:
            budget_distribution = self._budget_distribution(req.monthly_budget, keyword_stats)

        summary = SummaryMetrics(
            total_keywords=total_keywords,
            total_frequency=total_frequency,
            avg_frequency=avg_frequency,
            budget_distribution=budget_distribution,
        )

        return MediaPlanResult(
            input_data=req,
            created_at=datetime.now(),
            keywords=keyword_stats,
            summary=summary,
        )

    @staticmethod
    def _priority(frequency: int) -> str:
        if frequency >= 10_000:
            return "high"
        if frequency >= 1_000:
            return "medium"
        return "low"

    @staticmethod
    def _budget_distribution(monthly_budget: float, keywords: list[KeywordStat]) -> dict[str, float]:
        groups = {"high": 0, "medium": 0, "low": 0}
        for key in keywords:
            groups[key.priority] += key.frequency

        total = sum(groups.values())
        if total == 0:
            return {"high": 0.0, "medium": 0.0, "low": 0.0}

        return {
            tier: round((freq / total) * monthly_budget, 2)
            for tier, freq in groups.items()
        }
