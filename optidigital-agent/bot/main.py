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

        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser_path = pw.chromium.executable_path
            logger.info("Playwright Chromium executable target: %s", browser_path)
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
            logger.info("Playwright Chromium headless launch: OK")
            return True
    except Exception as exc:
        logger.error("Playwright startup check failed: %s", exc)
        return False


async def on_startup() -> None:
    global _scheduler
    state.start_time = datetime.utcnow()
    await init_db()
    state.playwright_ok = await _check_playwright()
    logger.info("Antonov Digital Revenue Agent started ✅")
    _scheduler = setup_scheduler(bot)

    # Register Gmail job if enabled
    if settings.GMAIL_ENABLED:
        from gmail_agent.scheduler import register_gmail_job
        register_gmail_job(
            _scheduler,
            bot,
            interval_minutes=settings.GMAIL_CHECK_INTERVAL_MINUTES,
        )
        logger.info("Gmail agent enabled: check every %d min", settings.GMAIL_CHECK_INTERVAL_MINUTES)
    else:
        logger.info("Gmail agent disabled (GMAIL_ENABLED=false)")

    if settings.FREELANCEHUNT_DISCOVERY_ENABLED:
        from gmail_agent.freelancehunt_discovery import (
            register_freelancehunt_discovery_job,
        )

        register_freelancehunt_discovery_job(
            _scheduler,
            bot,
            interval_seconds=settings.FREELANCEHUNT_DISCOVERY_INTERVAL_SECONDS,
        )
    else:
        logger.info("Freelancehunt instant discovery disabled")

    _scheduler.start()
    state.scheduler = _scheduler
    logger.info(
        "Scheduler running (Freelancehunt discovery every 60 seconds; "
        "Gmail at configured interval; reports 09:00 Kyiv)."
    )


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
