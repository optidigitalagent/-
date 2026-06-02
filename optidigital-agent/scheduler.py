import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from ai.scorer import score_order
from config import settings
from db import AsyncSessionLocal
from db.crud import get_setting, save_order, update_order_status
from db.models import Order
from parser.freelancehunt import get_new_projects as _fh_projects
from parser.kabanchik import get_new_projects as _kb_projects
from parser.freelance_ua import get_new_projects as _flua_projects

logger = logging.getLogger(__name__)

_PARSERS = [
    _fh_projects,   # Freelancehunt
    _kb_projects,   # Kabanchik
    _flua_projects, # FreelanceUA / free-lance.ru
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


async def _send_order_card(bot: Bot, order: Order, project: dict) -> None:
    from bot.keyboards import order_card_keyboard

    desc = (order.description or "").strip()
    if len(desc) > 1000:
        desc = desc[:1000] + "…"

    budget = _format_budget(project)
    deadline = order.deadline or "—"
    bid_count = order.bid_count if order.bid_count is not None else project.get("bid_count", 0)
    category = order.category or "—"

    lines = [
        "━━━━━━━━━━━━━━━━━━━",
        f"📌 <b>{order.title}</b>",
        f"🆔 ID: <code>{order.id}</code>",
        "",
    ]

    if desc:
        lines += [f"📝 <b>Опис:</b>\n{desc}", ""]

    lines += [
        f"💰 <b>Бюджет:</b> {budget}",
        f"⏰ <b>Строки:</b> {deadline}",
        f"👥 <b>Конкурентів:</b> {bid_count}",
        f"🏷 <b>Категорія:</b> {category}",
        f"🖥 <b>Платформа:</b> {order.platform}",
        "",
        f'🔗 <a href="{order.url}">Відкрити проєкт</a>',
    ]

    if order.employer_url:
        name = order.employer_name or "Профіль замовника"
        lines.append(f'👤 <a href="{order.employer_url}">{name}</a>')
    elif order.employer_name:
        lines.append(f"👤 <b>Замовник:</b> {order.employer_name}")

    contacts = []
    if order.employer_phone:
        contacts.append(f"📞 {order.employer_phone}")
    if order.employer_telegram:
        contacts.append(f"✈️ {order.employer_telegram}")
    if order.employer_email:
        contacts.append(f"📧 {order.employer_email}")

    if contacts:
        lines += ["", "<b>Контакти замовника:</b>"] + contacts

    lines += ["", f"<i>Відповісти: /reply {order.id}</i>", "━━━━━━━━━━━━━━━━━━━"]

    await bot.send_message(
        chat_id=settings.TELEGRAM_CHAT_ID,
        text="\n".join(lines),
        reply_markup=order_card_keyboard(order.id, order.url),
        disable_web_page_preview=True,
    )


async def check_new_orders(bot: Bot) -> tuple[int, int]:
    """Returns (found_new, sent_notified) — safe to ignore from scheduler."""
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
                "platform":          project.get("platform", "Unknown"),
                "title":             project["title"],
                "description":       project.get("description", ""),
                "budget":            float(budget_raw) if budget_raw else None,
                "url":               project["url"],
                "score":             score,
                "status":            "new",
                "employer_name":     project.get("employer_name") or "",
                "employer_url":      project.get("employer_url") or "",
                "category":          project.get("category") or "",
                "deadline":          project.get("deadline") or "",
                "bid_count":         int(project.get("bid_count") or 0),
                "employer_phone":    project.get("employer_phone"),
                "employer_telegram": project.get("employer_telegram"),
                "employer_email":    project.get("employer_email"),
            }

            async with AsyncSessionLocal() as session:
                order = await save_order(session, order_data)

            if order is None:
                logger.debug("Duplicate skipped: %s", project.get("url"))
                continue

            found += 1

            if score >= min_score:
                await _send_order_card(bot, order, project)

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

    import state as _state
    _state.last_scan_time = datetime.utcnow()

    logger.info(
        "=== check_new_orders: done — found=%d scored=%d sent=%d ===",
        found, scored, sent,
    )
    return found, sent


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
