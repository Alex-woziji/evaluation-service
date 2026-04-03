from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_BACKEND: str = "local"  # "local" | "azure"
    SQLITE_DB_PATH: str = "data/evaluation.db"
    AZURE_DB_URL: str = "mock://placeholder"

    openai_api_key: str = ""
    log_level: str = "INFO"
    app_version: str = "1.0.0"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
