import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from ai.writer import generate_response
from config import settings
from db import AsyncSessionLocal
from db.crud import get_setting, save_response, set_setting, update_order_status
from db.models import Order, Response

from .keyboards import (
    OrderCb,
    ResponseCb,
    order_card_keyboard,
    response_keyboard,
    score_picker_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.id == settings.TELEGRAM_CHAT_ID)
router.callback_query.filter(F.message.chat.id == settings.TELEGRAM_CHAT_ID)

admin_router = Router()
admin_router.message.filter(F.chat.id == settings.admin_chat_id)

DEFAULT_MIN_SCORE = 6


# ─── /stats ──────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    week_ago = datetime.utcnow() - timedelta(days=7)

    async with AsyncSessionLocal() as session:
        found = await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.status.in_(["notified", "skipped", "sent"]),
                Order.created_at >= week_ago,
            )
        ) or 0
        sent = await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.status == "sent",
                Order.created_at >= week_ago,
            )
        ) or 0
        skipped = await session.scalar(
            select(func.count()).select_from(Order).where(
                Order.status == "skipped",
                Order.created_at >= week_ago,
            )
        ) or 0

    await message.answer(
        "📊 <b>Статистика за тиждень</b>\n\n"
        f"🔍 Знайдено: <b>{found}</b>\n"
        f"✅ Відправлено: <b>{sent}</b>\n"
        f"❌ Пропущено: <b>{skipped}</b>"
    )


# ─── /settings ───────────────────────────────────────────────────────────────

@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        val = await get_setting(session, "min_score")
    current = int(val) if val else DEFAULT_MIN_SCORE

    await message.answer(
        "⚙️ <b>Налаштування</b>\n\n"
        f"Мінімальний score для сповіщень: <b>{current}</b>\n\n"
        "Обери новий мінімальний score:",
        reply_markup=score_picker_keyboard(current),
    )


@router.callback_query(F.data.startswith("score:"))
async def cb_set_score(callback: CallbackQuery) -> None:
    score = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        await set_setting(session, "min_score", str(score))

    await callback.answer(f"✅ Score встановлено: {score}")
    await callback.message.edit_text(
        "⚙️ <b>Налаштування</b>\n\n"
        f"Мінімальний score для сповіщень: <b>{score}</b>\n\n"
        "Обери новий мінімальний score:",
        reply_markup=score_picker_keyboard(score),
    )


# ─── Order card callbacks ─────────────────────────────────────────────────────

@router.callback_query(OrderCb.filter(F.action == "view"))
async def cb_view_response(callback: CallbackQuery, callback_data: OrderCb) -> None:
    await callback.answer()
    await callback.message.edit_text("⏳ Генерую відгук...", reply_markup=None)

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, callback_data.order_id)

    if not order:
        await callback.message.edit_text("❌ Замовлення не знайдено")
        return

    order_dict = {
        "title": order.title,
        "description": order.description or "",
        "budget_from": None,
        "budget_to": order.budget,
        "currency": "UAH",
        "url": order.url,
    }

    text = await generate_response(order_dict)
    if not text:
        await callback.message.edit_text(
            "❌ Не вдалося згенерувати відгук. Спробуй ще раз.",
            reply_markup=order_card_keyboard(order.id, order.url),
        )
        return

    async with AsyncSessionLocal() as session:
        draft = await save_response(session, order.id, text, result="draft")

    await callback.message.edit_text(
        f"📝 <b>Згенерований відгук:</b>\n\n{text}",
        reply_markup=response_keyboard(order.id, draft.id),
    )


@router.callback_query(OrderCb.filter(F.action == "skip"))
async def cb_skip(callback: CallbackQuery, callback_data: OrderCb) -> None:
    await callback.answer("Пропущено")
    async with AsyncSessionLocal() as session:
        await update_order_status(session, callback_data.order_id, "skipped")
    await callback.message.edit_reply_markup(reply_markup=None)


# ─── Response callbacks ───────────────────────────────────────────────────────

@router.callback_query(ResponseCb.filter(F.action == "send"))
async def cb_send_manual(callback: CallbackQuery, callback_data: ResponseCb) -> None:
    await callback.answer()

    async with AsyncSessionLocal() as session:
        draft = await session.get(Response, callback_data.response_id)
        order = await session.get(Order, callback_data.order_id)
        if draft:
            draft.result = "sent"
            await session.commit()
        if order:
            await update_order_status(session, order.id, "sent")

    if not draft or not order:
        await callback.answer("❌ Помилка: дані не знайдено", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ Скопіюй відгук нижче та відправ вручну на платформі.",
        reply_markup=None,
    )
    await callback.message.answer(
        f"📋 <b>Відповідь для копіювання:</b>\n\n{draft.text}\n\n"
        f"🔗 <a href='{order.url}'>Відкрити замовлення</a>"
    )


@router.callback_query(ResponseCb.filter(F.action == "rewrite"))
async def cb_rewrite(callback: CallbackQuery, callback_data: ResponseCb) -> None:
    await callback.answer()
    await callback.message.edit_text("⏳ Переписую відгук...", reply_markup=None)

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, callback_data.order_id)

    if not order:
        await callback.message.edit_text("❌ Замовлення не знайдено")
        return

    order_dict = {
        "title": order.title,
        "description": order.description or "",
        "budget_from": None,
        "budget_to": order.budget,
        "currency": "UAH",
        "url": order.url,
    }

    text = await generate_response(order_dict)
    if not text:
        await callback.message.edit_text("❌ Не вдалося згенерувати відгук. Спробуй ще раз.")
        return

    async with AsyncSessionLocal() as session:
        new_draft = await save_response(session, order.id, text, result="draft")

    await callback.message.edit_text(
        f"📝 <b>Новий варіант відгуку:</b>\n\n{text}",
        reply_markup=response_keyboard(order.id, new_draft.id),
    )


@router.callback_query(ResponseCb.filter(F.action == "cancel"))
async def cb_cancel(callback: CallbackQuery) -> None:
    await callback.answer("Скасовано")
    await callback.message.edit_reply_markup(reply_markup=None)


# ─── /reply ──────────────────────────────────────────────────────────────────

@router.message(Command("reply"))
async def cmd_reply(message: Message) -> None:
    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip().isdigit():
        await message.answer(
            "❌ Використання: <code>/reply &lt;project_id&gt;</code>\n"
            "Приклад: <code>/reply 42</code>"
        )
        return

    project_id = int(raw[1].strip())

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, project_id)

    if not order:
        await message.answer(f"❌ Проєкт <code>#{project_id}</code> не знайдено в базі")
        return

    await message.answer(f"⏳ Генерую відгук для <b>{order.title}</b>…")

    order_dict = {
        "title":       order.title,
        "description": order.description or "",
        "budget_from": None,
        "budget_to":   order.budget,
        "currency":    "UAH",
        "url":         order.url,
    }

    text = await generate_response(order_dict)
    if not text:
        await message.answer("❌ Не вдалося згенерувати відгук. Спробуй ще раз.")
        return

    async with AsyncSessionLocal() as session:
        draft = await save_response(session, order.id, text, result="draft")

    await message.answer(
        f"📝 <b>Відгук для #{project_id}:</b>\n\n{text}\n\n"
        f'🔗 <a href="{order.url}">Відкрити проєкт</a>',
        reply_markup=response_keyboard(order.id, draft.id),
    )


# ─── Admin commands ───────────────────────────────────────────────────────────

def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M:%S UTC")


def _fmt_uptime(since: datetime) -> str:
    delta = datetime.utcnow() - since
    total = int(delta.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}г {m}хв {s}с"


@admin_router.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    args = (message.text or "").strip().split()
    if len(args) > 1 and args[1].lower() == "debug":
        await _cmd_scan_debug(message)
        return

    from scheduler import check_new_orders

    await message.answer("🔍 <b>Сканування запущено...</b>")
    try:
        found, sent = await check_new_orders(message.bot)
        await message.answer(
            f"✅ <b>Сканування завершено</b>\n\n"
            f"📦 Нових заказів знайдено: <b>{found}</b>\n"
            f"📨 Відправлено сповіщень: <b>{sent}</b>"
        )
    except Exception as exc:
        logger.exception("Admin /scan failed")
        await message.answer(f"❌ Помилка під час сканування:\n<code>{exc}</code>")


async def _cmd_scan_debug(message: Message) -> None:
    from scheduler import check_new_orders_debug

    await message.answer("🐛 <b>Debug scan запущено...</b>")
    try:
        platforms = await check_new_orders_debug()

        summary_lines = ["🐛 <b>Debug Scan — зведення по платформах</b>\n"]
        all_rejected: list[dict] = []

        for p in platforms:
            name = p.get("platform", "Unknown")
            total = p.get("total", 0)
            matched = len(p.get("matched", []))
            rejected = p.get("rejected", [])
            error = p.get("error")

            excluded_cnt = sum(
                1 for r in rejected if r.get("_reject_reason", "").startswith("EXCLUDED")
            )
            no_kw_cnt = sum(
                1 for r in rejected if r.get("_reject_reason", "").startswith("ALLOWED")
            )

            if error:
                summary_lines.append(f"<b>{name}</b> — ❌ помилка: {error}\n")
            else:
                summary_lines.append(
                    f"<b>{name}</b>\n"
                    f"  📊 Всього знайдено: {total}\n"
                    f"  ✅ Пройшли фільтр: {matched}\n"
                    f"  🚫 Відсіяно EXCLUDED_KEYWORDS: {excluded_cnt}\n"
                    f"  ❓ Відсіяно (немає ALLOWED_KEYWORDS): {no_kw_cnt}\n"
                )

            all_rejected.extend(rejected)

        await message.answer("\n".join(summary_lines))

        # Show matched projects with keyword info
        all_matched: list[dict] = []
        for p in platforms:
            all_matched.extend(p.get("matched", []))

        if all_matched:
            sample = all_matched[:5]
            await message.answer(f"✅ <b>Пройшли фільтр (показано {len(sample)} з {len(all_matched)}):</b>")
            for i, proj in enumerate(sample, 1):
                title = proj.get("title") or "—"
                matched_kw = proj.get("_matched_keyword") or "—"
                url = proj.get("url") or ""
                card = (
                    f"<b>{i}. {title}</b>\n"
                    f"🔑 Ключове слово: <code>{matched_kw}</code>\n"
                    f"🔗 <a href='{url}'>Посилання</a>"
                )
                await message.answer(card, disable_web_page_preview=True)

        if not all_rejected:
            await message.answer("✅ Відхилених проєктів немає — всі пройшли фільтр або платформи порожні")
            return

        rejected_allowed = [r for r in all_rejected if r.get("_reject_reason", "").startswith("ALLOWED")][:5]
        rejected_excluded = [r for r in all_rejected if r.get("_reject_reason", "").startswith("EXCLUDED")][:5]

        for group_title, group in [
            ("Відхилено ALLOWED — немає ключових слів", rejected_allowed),
            ("Відхилено EXCLUDED — заборонене слово", rejected_excluded),
        ]:
            if not group:
                continue
            await message.answer(f"📋 <b>{group_title} (показано {len(group)}):</b>")
            for i, proj in enumerate(group, 1):
                title = proj.get("title") or "—"
                category = proj.get("category") or "—"
                desc = (proj.get("description") or "")[:300]
                reason = proj.get("_reject_reason") or "—"
                url = proj.get("url") or "—"
                card = (
                    f"<b>{i}. {title}</b>\n"
                    f"🏷 Категорія: {category}\n"
                    f"📝 {desc}\n\n"
                    f"❌ Причина: <code>{reason}</code>\n"
                    f"🔗 <a href='{url}'>Посилання</a>"
                )
                await message.answer(card, disable_web_page_preview=True)

    except Exception as exc:
        logger.exception("Admin /scan debug failed")
        await message.answer(f"❌ Помилка debug scan:\n<code>{exc}</code>")


@admin_router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    import state

    uptime = _fmt_uptime(state.start_time)
    pw_status = "✅ OK" if state.playwright_ok else "❌ недоступний"

    if state.scheduler is not None and state.scheduler.running:
        sched_status = "✅ запущено"
        job = state.scheduler.get_job("check_new_orders")
        next_run = _fmt_dt(job.next_run_time) if job else "—"
    else:
        sched_status = "❌ зупинено"
        next_run = "—"

    await message.answer(
        "📊 <b>Статус бота</b>\n\n"
        f"⏱ Uptime: <b>{uptime}</b>\n"
        f"🎭 Playwright: <b>{pw_status}</b>\n"
        f"🕐 Scheduler: <b>{sched_status}</b>\n"
        f"⏭ Наступний скан: <b>{next_run}</b>\n"
        f"🕓 Останній скан: <b>{_fmt_dt(state.last_scan_time)}</b>"
    )


@admin_router.message(Command("testfh"))
async def cmd_testfh(message: Message) -> None:
    from parser.freelancehunt import get_new_projects

    await message.answer("🔄 Запускаю Freelancehunt parser...")
    try:
        projects = await get_new_projects()
        await message.answer(
            f"✅ <b>Freelancehunt</b>\n\n"
            f"📦 Знайдено проєктів: <b>{len(projects)}</b>"
        )
    except Exception as exc:
        logger.exception("Admin /testfh failed")
        await message.answer(f"❌ Помилка Freelancehunt parser:\n<code>{exc}</code>")


@admin_router.message(Command("testua"))
async def cmd_testua(message: Message) -> None:
    from parser.freelance_ua import get_new_projects

    await message.answer("🔄 Запускаю FreelanceUA parser...")
    try:
        projects = await get_new_projects()
        await message.answer(
            f"✅ <b>FreelanceUA</b>\n\n"
            f"📦 Знайдено проєктів: <b>{len(projects)}</b>"
        )
    except Exception as exc:
        logger.exception("Admin /testua failed")
        await message.answer(f"❌ Помилка FreelanceUA parser:\n<code>{exc}</code>")
