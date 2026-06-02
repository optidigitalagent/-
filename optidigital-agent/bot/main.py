import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import state
from config import settings
from db import engine
from db.models import init_db
from scheduler import setup_scheduler

from bot.handlers import admin_router, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=settings.TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

_scheduler: AsyncIOScheduler | None = None


async def _check_playwright() -> bool:
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            pw_version = version("playwright")
            logger.info("Playwright version: %s", pw_version)
        except PackageNotFoundError:
            logger.error("playwright package not installed — run: pip install playwright")
            return False

        from pathlib import Path
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser_path = pw.chromium.executable_path
            logger.info("Playwright Chromium path: %s", browser_path)
            if Path(browser_path).exists():
                logger.info("Playwright Chromium binary: OK")
                return True
            else:
                logger.error(
                    "Playwright Chromium binary NOT FOUND at: %s — "
                    "parsers will skip browser fallback. "
                    "Fix: Railway build command → python -m playwright install chromium --with-deps",
                    browser_path,
                )
                return False
    except Exception as exc:
        logger.error("Playwright startup check failed: %s", exc)
        return False


async def on_startup() -> None:
    global _scheduler
    state.start_time = datetime.utcnow()
    await init_db()
    state.playwright_ok = await _check_playwright()
    logger.info("OptiDigital Agent started ✅")
    _scheduler = setup_scheduler(bot)
    _scheduler.start()
    state.scheduler = _scheduler
    logger.info("Scheduler running (check every 15 min, weekly report Sun 09:00 Kyiv).")


async def on_shutdown() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
    await engine.dispose()


async def main() -> None:
    dp.include_router(router)
    dp.include_router(admin_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
