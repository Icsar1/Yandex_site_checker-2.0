from datetime import datetime, timedelta, timezone
import uuid

from app.config import settings
from app.models import SeoLead, SeoReport
from app.providers import build_provider


class SeoAnalyzer:
    """
    SEO analyzer:
    - Работает через выбранный data-provider.
    - По умолчанию mock (легко и быстро).
    - Для прода: SEO_DATA_PROVIDER=yandex_hybrid + реальные API вызовы в providers.py.
    """

    def __init__(self) -> None:
        self.provider = build_provider()

    async def analyze(self, lead: SeoLead) -> SeoReport:
        data = await self.provider.collect(lead.site_url)

        report_id = str(uuid.uuid4())
        created_at = datetime.now(tz=timezone.utc)
        expires_at = created_at + timedelta(hours=settings.report_ttl_hours)

        summary = (
            "Покажем за 30 минут, почему сайт не приносит заявки. "
            "Выявлены критические точки роста в техническом SEO, спросе и сравнении с конкурентами."
        )

        return SeoReport(
            report_id=report_id,
            site_url=lead.site_url,
            summary=summary,
            critical_errors=data.critical_errors,
            demand_score=data.demand_score,
            competitors=data.competitors,
            recommendations=data.recommendations,
            created_at=created_at,
            expires_at=expires_at,
        )
