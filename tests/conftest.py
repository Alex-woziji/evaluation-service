"""
pytest conftest — set required env vars before any app module is imported,
so tests work without a real .env file or database.
"""
import os

# Must be set before app imports so pydantic-settings doesn't fail
os.environ.setdefault("DB_BACKEND", "azure")
os.environ.setdefault("AZURE_DB_URL", "sqlite+aiosqlite:///./data/test.db")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-key")
