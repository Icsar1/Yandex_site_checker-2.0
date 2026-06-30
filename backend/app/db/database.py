from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite


async def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")

    async with aiosqlite.connect(path) as db:
        await db.executescript(schema)
        await db.commit()

        # Idempotent migration for existing DBs
        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN suggested_niche TEXT")
            await db.commit()
        except Exception:
            pass  # Column already exists

        try:
            await db.execute("ALTER TABLE tasks ADD COLUMN search_masks TEXT")
            await db.commit()
        except Exception:
            pass


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON;")
    try:
        yield db
    finally:
        await db.close()
