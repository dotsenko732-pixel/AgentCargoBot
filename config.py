from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./agentcargo.db"
    log_level: str = "INFO"

    # Claude model settings
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 2048

    # Railway injects DATABASE_URL as postgres:// but asyncpg needs postgresql+asyncpg://
    @property
    def async_database_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
