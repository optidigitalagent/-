import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from ai.scorer import score_order
from ai.writer import generate_response
from config import settings
from db import AsyncSessionLocal
from db.crud import get_setting, save_order, save_response, update_order_status
from db.models import Order
from parser.freelancehunt import get_new_projects

logger = logging.getLogger(__name__)

# Add new platform parsers here — each must return list[dict] with a "platform" key
_PARSERS = [
    get_new_projects,  # Freelancehunt
]


def _format_budget(project: dict) -> str:
    bf = project.get("budget_from")
    bt = project.get("budget_to")
    cur = project.get("currency", "UAH")
    if bf and bt:
        return f"{bf}–{bt} {cur}"
    if bf:
        return f"від {bf} {cur}"
    if bt:
        return f"до {bt} {cur}"
    return "не вказано"


async def _fetch_all_projects() -> list[dict]:
    results = await asyncio.gather(*[p() for p in _PARSERS], return_exceptions=True)
    projects: list[dict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Parser[%d] failed: %s", i, result)
        else:
            projects.extend(result)
    return projects


async def _send_order_card(bot: Bot, order: Order, project: dict, score_data: dict, response_text: str) -> None:
    from bot.keyboards import order_card_keyboard

    red_flags = score_data.get("red_flags", [])
    flags_line = f"\n🚩 {', '.join(red_flags)}" if red_flags else ""
    score = score_data.get("score", order.score or 0)

    card = (
        "━━━━━━━━━━━━━━━\n"
        f"🔥 <b>{score}/10</b> | {order.platform}\n"
        f"📋 {order.title}\n"
        f"💰 {_format_budget(project)}\n"
        f"👤 Конкурентів: {project.get('bid_count', 0)}\n"
        f"📊 {score_data.get('reason', '')}"
        f"{flags_line}\n"
        "━━━━━━━━━━━━━━━"
    )
    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID,
        text=card,
        reply_markup=order_card_keyboard(order.id, order.url),
    )

    if response_text:
        await bot.send_message(
            chat_id=settings.TELEGRAM_CHAT_ID,
            text=f"📝 <b>Готовий відгук:</b>\n\n{response_text}",
        )


async def check_new_orders(bot: Bot) -> None:
    logger.info("=== check_new_orders: start ===")

    async with AsyncSessionLocal() as session:
        raw = await get_setting(session, "min_score")
    min_score = int(raw) if raw else 6

    projects = await _fetch_all_projects()
    logger.info("Fetched %d projects total across all platforms", len(projects))

    found = scored = sent = 0

    for project in projects:
        try:
            score_data = await score_order(project)
            score = float(score_data.get("score", 0))
            scored += 1

            budget_raw = project.get("budget_to") or project.get("budget_from")
            order_data = {
                "platform": project.get("platform", "Unknown"),
                "title": project["title"],
                "description": project.get("description", ""),
                "budget": float(budget_raw) if budget_raw else None,
                "url": project["url"],
                "score": score,
                "status": "new",
            }

            async with AsyncSessionLocal() as session:
                order = await save_order(session, order_data)

            if order is None:
                logger.debug("Duplicate skipped: %s", project.get("url"))
                continue

            found += 1

            if score >= min_score:
                response_text = await generate_response(project)

                if response_text:
                    async with AsyncSessionLocal() as session:
                        await save_response(session, order.id, response_text, result="draft")

                await _send_order_card(bot, order, project, score_data, response_text)

                async with AsyncSessionLocal() as session:
                    await update_order_status(session, order.id, "notified")

                sent += 1
                logger.info(
                    "Notified: order_id=%d score=%.1f title=%r",
                    order.id, score, order.title,
                )
            else:
                logger.info(
                    "Skipped: order_id=%d score=%.1f < min_score=%d",
                    order.id, score, min_score,
                )

        except Exception:
            logger.exception("Error processing project: %s", project.get("url"))

    logger.info(
        "=== check_new_orders: done — found=%d scored=%d sent=%d ===",
        found, scored, sent,
    )


async def weekly_report(bot: Bot) -> None:
    week_ago = datetime.utcnow() - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        found = await session.scalar(
            select(func.count()).select_from(Order).where(Order.created_at >= week_ago)
        ) or 0
        scored = await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.created_at >= week_ago,
                Order.score.isnot(None),
            )
        ) or 0
        sent = await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.created_at >= week_ago,
                Order.status == "notified",
            )
        ) or 0

    text = (
        "📊 <b>Тижневий звіт OptiDigital</b>\n\n"
        f"🔍 Знайдено: <b>{found}</b>\n"
        f"⚡ Оцінено: <b>{scored}</b>\n"
        f"✅ Відправлено відгуків: <b>{sent}</b>"
    )
    await bot.send_message(chat_id=settings.TELEGRAM_CHAT_ID, text=text)
    logger.info("Weekly report sent: found=%d scored=%d sent=%d", found, scored, sent)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

    scheduler.add_job(
        check_new_orders,
        trigger="interval",
        minutes=15,
        id="check_new_orders",
        args=[bot],
        max_instances=1,  # prevent overlap if job takes longer than 15 min
        coalesce=True,
    )

    scheduler.add_job(
        weekly_report,
        trigger="cron",
        day_of_week="sun",
        hour=9,
        minute=0,
        id="weekly_report",
        args=[bot],
    )

    return scheduler
