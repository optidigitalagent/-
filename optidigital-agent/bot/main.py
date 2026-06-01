import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import settings
from db import engine
from db.models import init_db
from scheduler import setup_scheduler

from bot.handlers import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_scheduler: AsyncIOScheduler | None = None


async def on_startup() -> None:
    global _scheduler
    await init_db()
    logger.info("OptiDigital Agent started ✅")
    _scheduler = setup_scheduler(bot)
    _scheduler.start()
    logger.info("Scheduler running (check every 15 min, weekly report Sun 09:00 Kyiv).")


async def on_shutdown() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
    await engine.dispose()


async def main() -> None:
    dp.include_router(router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
