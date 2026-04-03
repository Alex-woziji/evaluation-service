"""
pytest conftest — set required env vars before any app module is imported,
so tests work without a real .env file or database.
"""
import os

# Must be set before app imports so pydantic-settings doesn't fail
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
