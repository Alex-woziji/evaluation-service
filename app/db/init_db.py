from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.db.models import Base


async def init_local_db(db_path: str) -> None:
    sqlite_path = Path(db_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_path.as_posix()}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _main() -> None:
    if settings.DB_BACKEND.strip().lower() != "local":
        raise ValueError("DB init script supports local SQLite only. Set DB_BACKEND=local in .env")

    await init_local_db(settings.SQLITE_DB_PATH)
    print(f"Local SQLite DB initialized at: {settings.SQLITE_DB_PATH}")


if __name__ == "__main__":
    asyncio.run(_main())
