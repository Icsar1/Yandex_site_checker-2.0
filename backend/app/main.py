from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.admin import access_router, router as admin_router
from app.api.client import router as client_router
from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.db.database import init_db
from app.logging_conf import setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = app_settings
        setup_logging(app_settings.LOG_LEVEL)
        await init_db(app_settings.DATABASE_PATH)
        yield

    app = FastAPI(title="Yandex Mediaplan API", lifespan=lifespan)
    app.state.settings = app_settings
    app.include_router(health_router)
    app.include_router(client_router)
    app.include_router(access_router)
    app.include_router(admin_router)
    return app


app = create_app()
