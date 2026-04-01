"""AgentCargoBot — AI Freight Marketplace for Telegram."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import cargo, carrier, deals, payments, profile, start
from config import settings
from models.database import init_db

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Initializing database...")
    await init_db()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Register routers
    dp.include_router(start.router)
    dp.include_router(deals.router)
    dp.include_router(cargo.router)
    dp.include_router(carrier.router)
    dp.include_router(payments.router)
    dp.include_router(profile.router)

    logger.info("AgentCargoBot starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
