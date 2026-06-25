from __future__ import annotations

from app.services.pdf import render_pdf


async def render_pdf_mock(
    niche: str,
    region: str,
    report: dict,
    aggregates: dict,
    output_path: str,
) -> str:
    return await render_pdf(niche, region, report, aggregates, output_path)
