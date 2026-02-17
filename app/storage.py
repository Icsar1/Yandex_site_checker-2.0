import json
import sqlite3
from datetime import datetime
from typing import Optional

from app.config import settings
from app.models import SeoReport


class Storage:
    def __init__(self, db_path: str = settings.db_path) -> None:
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    report_id TEXT PRIMARY KEY,
                    site_url TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )

    def save_report(self, report: SeoReport) -> None:
        payload = {
            "summary": report.summary,
            "critical_errors": report.critical_errors,
            "demand_score": report.demand_score,
            "competitors": report.competitors,
            "recommendations": report.recommendations,
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO reports (report_id, site_url, payload, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.site_url,
                    json.dumps(payload, ensure_ascii=False),
                    report.created_at.isoformat(),
                    report.expires_at.isoformat(),
                ),
            )

    def get_report(self, report_id: str) -> Optional[SeoReport]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT report_id, site_url, payload, created_at, expires_at FROM reports WHERE report_id = ?",
                (report_id,),
            ).fetchone()

        if not row:
            return None

        payload = json.loads(row[2])
        return SeoReport(
            report_id=row[0],
            site_url=row[1],
            summary=payload["summary"],
            critical_errors=payload["critical_errors"],
            demand_score=payload["demand_score"],
            competitors=payload["competitors"],
            recommendations=payload["recommendations"],
            created_at=datetime.fromisoformat(row[3]),
            expires_at=datetime.fromisoformat(row[4]),
        )

    def delete_expired(self, now: datetime) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM reports WHERE expires_at < ?",
                (now.isoformat(),),
            )
            return cursor.rowcount
