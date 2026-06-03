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
from parser.freelancehunt import get_debug_info as _fh_debug
from parser.kabanchik import get_new_projects as _kb_projects
from parser.kabanchik import get_debug_info as _kb_debug
from parser.freelance_ua import get_new_projects as _flua_projects
from parser.freelance_ua import get_debug_info as _flua_debug

logger = logging.getLogger(__name__)

_PARSERS = [
    _fh_projects,   # Freelancehunt
    _kb_projects,   # Kabanchik
    _flua_projects, # FreelanceUA / free-lance.ru
]

_DEBUG_PARSERS = [
    _fh_debug,
    _kb_debug,
    _flua_debug,
]


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M UTC")


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


async def check_new_orders(bot: Bot, *, is_auto: bool = False) -> tuple[int, int]:
    """Returns (new_saved, notified) — safe to ignore from scheduler."""
    mode = "AUTO" if is_auto else "MANUAL"
    logger.info("=== %s SCAN STARTED ===", mode)

    async with AsyncSessionLocal() as session:
        raw = await get_setting(session, "min_score")
    min_score = int(raw) if raw else 6

    projects = await _fetch_all_projects()
    found_total = len(projects)
    logger.info("Fetched %d projects total across all platforms", found_total)

    new_saved = scored = notified = duplicates_skipped = below_min_score = errors = 0

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
                duplicates_skipped += 1
                continue

            new_saved += 1

            if score >= min_score:
                await _send_order_card(bot, order, project)

                async with AsyncSessionLocal() as session:
                    await update_order_status(session, order.id, "notified")

                notified += 1
                logger.info(
                    "Notified: order_id=%d score=%.1f title=%r",
                    order.id, score, order.title,
                )
            else:
                below_min_score += 1
                logger.info(
                    "Skipped: order_id=%d score=%.1f < min_score=%d",
                    order.id, score, min_score,
                )

        except Exception:
            errors += 1
            logger.exception("Error processing project: %s", project.get("url"))

    import state as _state
    _state.last_scan_time = datetime.utcnow()

    logger.info(
        "=== %s SCAN DONE — found_total=%d new_saved=%d duplicates_skipped=%d "
        "scored=%d notified=%d below_min_score=%d errors=%d ===",
        mode, found_total, new_saved, duplicates_skipped, scored, notified, below_min_score, errors,
    )

    if is_auto:
        _state.last_auto_scan_time = datetime.utcnow()
        _state.last_auto_found_total = found_total
        _state.last_auto_new_saved = new_saved
        _state.last_auto_notified = notified
        _state.last_auto_duplicates = duplicates_skipped
        _state.last_auto_below_min = below_min_score
        _state.last_auto_errors = errors
        _state.last_auto_error = f"{errors} помилок при обробці" if errors else None

        _state.daily_found_total += found_total
        _state.daily_new_saved += new_saved
        _state.daily_notified += notified
        _state.daily_duplicates += duplicates_skipped
        _state.daily_below_min += below_min_score
        _state.daily_errors += errors

        if errors > 0:
            alert = (
                f"🚨 <b>Auto Scan Error</b>\n\n"
                f"found_total={found_total}\n"
                f"new_saved={new_saved}\n"
                f"notified={notified}\n"
                f"errors={errors}"
            )
            try:
                await bot.send_message(chat_id=settings.admin_chat_id, text=alert)
            except Exception:
                logger.exception("Failed to send error alert to admin")

    return new_saved, notified


async def check_new_orders_debug() -> list[dict]:
    """Run all parsers in debug mode — returns per-platform filter stats."""
    results = await asyncio.gather(*[p() for p in _DEBUG_PARSERS], return_exceptions=True)
    platforms: list[dict] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error("Debug parser[%d] failed: %s", i, result)
            platforms.append({
                "platform": f"Parser[{i}]",
                "total": 0,
                "matched": [],
                "rejected": [],
                "error": str(result),
            })
        else:
            platforms.append(result)
    return platforms


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


async def daily_report(bot: Bot) -> None:
    import state as _state

    lines = [
        "📊 <b>Daily Agent Report</b>\n",
        "За останні 24 години:",
        f"📦 Знайдено всього: <b>{_state.daily_found_total}</b>",
        f"🆕 Нових збережено: <b>{_state.daily_new_saved}</b>",
        f"♻️ Дублікатів: <b>{_state.daily_duplicates}</b>",
        f"📨 Відправлено сповіщень: <b>{_state.daily_notified}</b>",
        f"⬇️ Нижче порогу: <b>{_state.daily_below_min}</b>",
        f"❌ Помилок: <b>{_state.daily_errors}</b>",
        "",
        "Останній авто-скан:",
        f"🕓 {_fmt_dt(_state.last_auto_scan_time)}",
        f"📦 Знайдено: {_state.last_auto_found_total if _state.last_auto_found_total is not None else '—'}",
        f"📨 Сповіщено: {_state.last_auto_notified if _state.last_auto_notified is not None else '—'}",
    ]

    try:
        await bot.send_message(chat_id=settings.admin_chat_id, text="\n".join(lines))
        logger.info("Daily report sent")
    except Exception:
        logger.exception("Failed to send daily report")

    _state.daily_found_total = 0
    _state.daily_new_saved = 0
    _state.daily_notified = 0
    _state.daily_duplicates = 0
    _state.daily_below_min = 0
    _state.daily_errors = 0


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Kyiv")

    scheduler.add_job(
        check_new_orders,
        trigger="interval",
        hours=1,
        id="check_new_orders",
        args=[bot],
        kwargs={"is_auto": True},
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        daily_report,
        trigger="cron",
        hour=9,
        minute=0,
        id="daily_report",
        args=[bot],
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
