from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    anthropic_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./agentcargo.db"
    log_level: str = "INFO"

    # Claude model settings
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 2048

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
