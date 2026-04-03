from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _build_database_url() -> str:
    backend = settings.DB_BACKEND.strip().lower()

    if backend == "local":
        db_path = Path(settings.SQLITE_DB_PATH)
        if not db_path.exists():
            raise FileNotFoundError(
                f"Local SQLite database not found at '{db_path}'. "
                "Please initialize it first by running: python -m app.db"
            )
        return f"sqlite+aiosqlite:///{db_path.as_posix()}"

    if backend == "azure":
        azure_db_url = settings.AZURE_DB_URL.strip()
        if not azure_db_url or azure_db_url.startswith("mock://"):
            raise ValueError(
                "DB_BACKEND is 'azure' but AZURE_DB_URL is missing or mock placeholder. "
                "Please provide complete Azure DB connection info in .env"
            )
        return azure_db_url

    raise ValueError("DB_BACKEND must be either 'local' or 'azure'")


DATABASE_URL = _build_database_url()

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
