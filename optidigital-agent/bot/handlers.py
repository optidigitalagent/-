import logging
from datetime import datetime, timedelta

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
