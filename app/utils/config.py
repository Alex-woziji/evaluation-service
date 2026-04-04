from pydantic_settings import BaseSettings, SettingsConfigDict


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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


llm_settings = LLMSettings()

if __name__ == "__main__":
    for setting in llm_settings:
        print(setting)
