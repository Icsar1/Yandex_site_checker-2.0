from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.logging_config import setup_logging
from app.schemas import MediaPlanRequest
from app.services.media_plan import MediaPlanService
from app.services.pdf_export import PDFExportService
from app.services.wordstat_client import (
    WordstatAPIError,
    WordstatAuthError,
    WordstatClient,
    WordstatRateLimitError,
    WordstatTimeoutError,
)

setup_logging(settings.request_log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

wordstat_client = WordstatClient()
media_plan_service = MediaPlanService()
pdf_export_service = PDFExportService()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"error": None})


@app.post("/generate", response_class=Response)
async def generate_media_plan(
    request: Request,
    niche: str = Form(...),
    region: str = Form(...),
    monthly_budget: float | None = Form(default=None),
    campaign_goal: str | None = Form(default=None),
) -> Response:
    try:
        req = MediaPlanRequest(
            niche=niche,
            region=region,
            monthly_budget=monthly_budget,
            campaign_goal=campaign_goal,
        )
        keywords = await wordstat_client.get_keywords(niche=req.niche, region=req.region)
        plan = media_plan_service.build_plan(req=req, keywords=keywords)
        pdf_bytes = pdf_export_service.generate(plan)
    except ValueError as exc:
        return templates.TemplateResponse(
            request,
            "index.html",
            {"error": f"Ошибка валидации: {exc}"},
            status_code=400,
        )
    except WordstatAuthError as exc:
        return _render_error(request, f"Ошибка авторизации API: {exc}", 502)
    except WordstatRateLimitError as exc:
        return _render_error(request, f"Слишком много запросов к API: {exc}", 429)
    except WordstatTimeoutError as exc:
        return _render_error(request, f"API не ответил вовремя: {exc}", 504)
    except WordstatAPIError as exc:
        return _render_error(request, f"Ошибка Wordstat API: {exc}", 502)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected generation error: %s", exc)
        return _render_error(request, "Внутренняя ошибка сервиса", 500)
    headers = {"Content-Disposition": 'attachment; filename="media_plan_wordstat.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


def _parse_tilda_payload(content_type: str, payload_candidate: Any) -> dict[str, Any]:
    if "application/json" in content_type and isinstance(payload_candidate, dict):
        return payload_candidate
    if isinstance(payload_candidate, dict):
        return payload_candidate
    return {}


async def _handle_tilda_webhook(request: Request) -> PlainTextResponse:
    payload: dict[str, Any] = {}
    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            json_payload = await request.json()
            payload = _parse_tilda_payload(content_type, json_payload)
        else:
            form_data = await request.form()
            payload = dict(form_data)
    except Exception:  # noqa: BLE001
        payload = {}
    if payload.get("test") == "test":
        return PlainTextResponse("ok", status_code=200)
    logger.info(
        "Tilda webhook received: keys=%s referer=%s content_type=%s",
        list(payload.keys()),
        request.headers.get("referer", "-"),
        content_type or "-",
    )
    return PlainTextResponse("ok", status_code=200)


@app.post("/webhook/tilda")
async def tilda_webhook(request: Request) -> PlainTextResponse:
    return await _handle_tilda_webhook(request)


@app.post("/lead/seo")
async def tilda_webhook_legacy(request: Request) -> PlainTextResponse:
    return await _handle_tilda_webhook(request)


def _render_error(request: Request, message: str, status_code: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"error": message},
        status_code=status_code,
    )
