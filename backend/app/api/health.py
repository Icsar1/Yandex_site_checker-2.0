from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import Settings, get_settings
from app.db.database import get_db

router = APIRouter()


def _get_request_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or get_settings()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> dict[str, Any]:
    settings = _get_request_settings(request)
    checks: dict[str, str] = {"db": "ok", "redis": "ok"}
    errors: list[dict[str, str]] = []

    try:
        async with get_db(settings.DATABASE_PATH) as db:
            await db.execute("SELECT 1")
    except Exception as exc:
        checks["db"] = "error"
        errors.append({"check": "db", "detail": str(exc)})

    redis_client: Redis | None = None
    try:
        redis_client = Redis.from_url(settings.REDIS_URL)
        await redis_client.ping()
    except RedisConnectionError as exc:
        checks["redis"] = "error"
        errors.append({"check": "redis", "detail": str(exc)})
    except Exception as exc:
        checks["redis"] = "error"
        errors.append({"check": "redis", "detail": str(exc)})
    finally:
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                pass

    if errors:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "checks": checks, "errors": errors},
        )

    return {"status": "ready", "checks": checks}
