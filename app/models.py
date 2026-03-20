from typing import Dict, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SeoLead:
    name: str
    phone: str
    email: str
    site_url: str


@dataclass
class SeoReport:
    report_id: str
    site_url: str
    summary: str
    critical_errors: List[str]
    demand_score: int
    competitors: List[Dict[str, str]]
    recommendations: List[str]
    created_at: datetime
    expires_at: datetime
