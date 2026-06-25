from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


TEMPLATE_NAME = "report.html.j2"
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def get_template_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(("html", "xml", "j2")),
    )
    env.filters["format_number"] = format_number
    return env


def format_number(value: Any) -> str:
    if value is None:
        return "0"

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if number.is_integer():
        return f"{int(number):,}".replace(",", " ")

    formatted = f"{number:,.2f}".rstrip("0").rstrip(".")
    return formatted.replace(",", " ").replace(".", ",")


def render_report_html(
    niche: str,
    region: str,
    report: dict,
    aggregates: dict,
    generated_at: str | None = None,
) -> str:
    template = get_template_environment().get_template(TEMPLATE_NAME)
    return template.render(
        niche=niche,
        region=region,
        report=report,
        aggregates=aggregates,
        generated_at=generated_at or datetime.now().isoformat(timespec="seconds"),
    )


async def render_pdf(
    niche: str,
    region: str,
    report: dict,
    aggregates: dict,
    output_path: str,
    headless: bool = True,
) -> str:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    html = render_report_html(niche, region, report, aggregates)

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = None
        context = None
        page = None
        try:
            browser = await playwright.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            await page.set_content(html, wait_until="load")
            await page.emulate_media(media="print")
            await page.evaluate("document.fonts.ready")
            await page.pdf(
                path=str(output),
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
            )
        finally:
            if page is not None:
                await page.close()
            if context is not None:
                await context.close()
            if browser is not None:
                await browser.close()

    return str(output)
