from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine

from app.utils.config import db_settings
from app.utils.constants import DEFAULT_DB_PATH
from app.db.models import Base


async def init_local_db(db_path: str) -> None:
    sqlite_path = Path(db_path)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_path.as_posix()}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


async def _main() -> None:
    if db_settings.DB_BACKEND.strip().lower() != "local":
        raise ValueError("DB init script supports local SQLite only. Set DB_BACKEND=local in .env")

    db_path = db_settings.SQLITE_DB_PATH or str(DEFAULT_DB_PATH)
    await init_local_db(db_path)
    print(f"Local SQLite DB initialized at: {db_path}")


if __name__ == "__main__":
    asyncio.run(_main())
