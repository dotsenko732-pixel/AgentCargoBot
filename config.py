from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str = ""
    deepseek_api_key: str = ""
    database_url: str = "sqlite+aiosqlite:///./agentcargo.db"
    log_level: str = "INFO"

    # DeepSeek model settings
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_max_tokens: int = 2048

    # Telegram Payments (provider token from @BotFather → Payments)
    payment_provider_token: str = ""

    # Monetization settings
    free_cargo_limit: int = 3  # cargos per month for free users
    commission_rate: float = 0.02  # 2% commission on deals
    promo_price_kgs: int = 150  # boost cargo price in KGS
    verify_price_kgs: int = 500  # paid verification price in KGS

    # Subscription prices (KGS per month)
    standard_price_kgs: int = 990
    business_price_kgs: int = 2990

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
