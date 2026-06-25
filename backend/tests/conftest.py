from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.db.database import init_db
from app.main import create_app


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    env_values = {
        "APP_ENV": "test",
        "DOMAIN": "test.local",
        "MOCK_YANDEX": "true",
        "LOG_LEVEL": "DEBUG",
        "DATABASE_PATH": str(tmp_path / "settings.db"),
        "REDIS_URL": "redis://localhost:6379/15",
        "WORDSTAT_API_KEY": "test-wordstat-secret",
        "YANDEX_GPT_API_KEY": "test-gpt-secret",
        "YANDEX_DIRECT_LOGIN": "test-login",
        "YANDEX_DIRECT_PASSWORD": "test-password",
        "ADMIN_PASSWORD": "test-admin-password",
        "SESSION_SECRET": "test-session-secret-at-least-32-chars",
    }
    for name, value in env_values.items():
        monkeypatch.setenv(name, value)

    return Settings()


@pytest_asyncio.fixture
async def tmp_db(tmp_path: Path) -> AsyncIterator[Path]:
    db_path = tmp_path / "tasks.db"
    await init_db(str(db_path))
    yield db_path

    for suffix in ("", "-wal", "-shm"):
        path = Path(f"{db_path}{suffix}")
        if path.exists():
            path.unlink()


@pytest_asyncio.fixture
async def client(settings: Settings, tmp_db: Path) -> AsyncIterator[AsyncClient]:
    app_settings = settings.model_copy(update={"DATABASE_PATH": str(tmp_db)})
    app = create_app(app_settings)

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as http_client:
            yield http_client
