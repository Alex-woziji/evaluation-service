from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    """Database configuration loaded from environment variables."""

    DB_BACKEND: str = "local"  # "local" | "azure"
    SQLITE_DB_PATH: str = "data/evaluation.db"
    AZURE_DB_URL: str = "mock://placeholder"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class LLMSettings(BaseSettings):
    """LLM client configuration loaded from environment variables."""

    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2025-01-01-preview"
    LLM_MODEL: str = "gpt-4.1"
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_ATTEMPTS: int = 3
    LLM_BASE_WAIT: float = 2.0
    LLM_MAX_WAIT: float = 10.0
    LLM_JITTER: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


class AppSettings(BaseSettings):
    """Application-level configuration loaded from environment variables."""

    log_level: str = "INFO"
    app_version: str = "1.0.0"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


db_settings = DBSettings()
llm_settings = LLMSettings()
app_settings = AppSettings()
