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


async def _check_playwright() -> None:
    try:
        from importlib.metadata import version, PackageNotFoundError
        try:
            pw_version = version("playwright")
            logger.info("Playwright version: %s", pw_version)
        except PackageNotFoundError:
            logger.error("playwright package not installed — run: pip install playwright")
            return

        from pathlib import Path
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser_path = pw.chromium.executable_path
            logger.info("Playwright Chromium path: %s", browser_path)
            if Path(browser_path).exists():
                logger.info("Playwright Chromium binary: OK")
            else:
                logger.error(
                    "Playwright Chromium binary NOT FOUND at: %s — "
                    "parsers will skip browser fallback. "
                    "Fix: Railway build command → python -m playwright install chromium --with-deps",
                    browser_path,
                )
    except Exception as exc:
        logger.error("Playwright startup check failed: %s", exc)


async def on_startup() -> None:
    global _scheduler
    await init_db()
    await _check_playwright()
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
