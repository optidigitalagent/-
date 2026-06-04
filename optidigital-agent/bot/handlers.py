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


# ─── Gmail agent commands (/reply_job, /skip_job) ────────────────────────────

_gmail_job_store: dict[str, dict] = {}


def register_gmail_job_analysis(analysis_dict: dict) -> None:
    """Called by gmail_agent.processor to register analyses for /reply_job."""
    _gmail_job_store[str(analysis_dict["email_id"])] = analysis_dict


@router.message(Command("reply_job"))
async def cmd_reply_job(message: Message) -> None:
    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2:
        await message.answer(
            "❌ Використання: <code>/reply_job &lt;email_id&gt;</code>"
        )
        return

    job_id = raw[1].strip()
    job = _gmail_job_store.get(job_id)

    if not job:
        await message.answer(
            f"❌ Замовлення <code>{job_id}</code> не знайдено.\n"
            "Можливо, воно вже застаріло або бот перезапускався."
        )
        return

    await message.answer(f"⏳ Генерую відгук для <b>{job.get('title', job_id)}</b>…")

    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from gmail_agent.reply_generator import generate_reply

    text = await generate_reply(
        title=job.get("title", ""),
        description=job.get("reason", "") + "\n" + job.get("why_relevant", ""),
        platform=job.get("platform", ""),
        budget=job.get("budget", "не вказано"),
        url=job.get("url", ""),
    )

    if not text:
        await message.answer("❌ Не вдалося згенерувати відгук. Спробуй ще раз.")
        return

    url = job.get("url", "")
    link = f'\n\n🔗 <a href="{url}">Відкрити замовлення</a>' if url else ""
    await message.answer(
        f"📝 <b>Відгук для {job.get('platform', '')} — {job.get('title', job_id)}:</b>\n\n"
        f"{text}"
        f"{link}"
    )


@router.message(Command("skip_job"))
async def cmd_skip_job(message: Message) -> None:
    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2:
        await message.answer("❌ Використання: <code>/skip_job &lt;email_id&gt;</code>")
        return

    job_id = raw[1].strip()
    if job_id in _gmail_job_store:
        del _gmail_job_store[job_id]
        await message.answer(f"✅ Замовлення <code>{job_id}</code> пропущено.")
    else:
        await message.answer(f"⚠️ Замовлення <code>{job_id}</code> не знайдено (вже пропущено або не існує).")


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

    def _v(val) -> str:
        return "—" if val is None else str(val)

    error_line = (
        f"\n⚠️ Остання помилка: <b>{state.last_auto_error}</b>"
        if state.last_auto_error else ""
    )

    await message.answer(
        "📊 <b>Статус бота</b>\n\n"
        f"⏱ Uptime: <b>{uptime}</b>\n"
        f"🎭 Playwright: <b>{pw_status}</b>\n"
        f"🕐 Scheduler: <b>{sched_status}</b>\n"
        f"⏭ Наступний скан: <b>{next_run}</b>\n"
        f"🕓 Останній скан: <b>{_fmt_dt(state.last_scan_time)}</b>\n\n"
        f"🤖 <b>Авто-скан (scheduler)</b>\n"
        f"🕓 Останній запуск: <b>{_fmt_dt(state.last_auto_scan_time)}</b>\n"
        f"📦 Знайдено: <b>{_v(state.last_auto_found_total)}</b>\n"
        f"🆕 Нових збережено: <b>{_v(state.last_auto_new_saved)}</b>\n"
        f"♻️ Дублікатів: <b>{_v(state.last_auto_duplicates)}</b>\n"
        f"📨 Уведомлень: <b>{_v(state.last_auto_notified)}</b>\n"
        f"⬇️ Нижче порогу: <b>{_v(state.last_auto_below_min)}</b>\n"
        f"❌ Помилок: <b>{_v(state.last_auto_errors)}</b>"
        + error_line
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


# ─── /gmail_test ──────────────────────────────────────────────────────────────

def _diagnose_gmail_connection(creds_file: str, token_file: str) -> dict:
    """
    Check Gmail connection without triggering browser OAuth flow.
    Sync — runs in executor. Never calls flow.run_local_server().
    """
    result: dict = {"status": "unknown", "message": "", "emails": [], "job_alert_count": 0}
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        result["status"] = "missing_deps"
        result["message"] = "Залежності не встановлено. Запусти: pip install google-auth-oauthlib google-api-python-client"
        return result

    try:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        creds = Credentials.from_authorized_user_file(token_file, scopes)

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
            else:
                result["status"] = "need_reauth"
                result["message"] = (
                    "Токен недійсний або прострочений без refresh_token.\n"
                    "Потрібна повторна авторизація локально:\n"
                    "1. Встанови GMAIL_USE_MOCK=false локально\n"
                    "2. Запусти бот — відкриється браузер\n"
                    "3. Завантаж оновлений gmail_token.json на сервер"
                )
                return result

        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds)

        resp = svc.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=10
        ).execute()
        messages = resp.get("messages", [])

        from gmail_agent.gmail_provider import _JOB_ALERT_SENDERS, _JOB_ALERT_SUBJECTS

        for i, meta in enumerate(messages[:10]):
            raw = svc.users().messages().get(
                userId="me",
                id=meta["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()
            headers = {
                h["name"].lower(): h["value"]
                for h in raw.get("payload", {}).get("headers", [])
            }
            sender = headers.get("from", "")
            subject = headers.get("subject", "")
            date = headers.get("date", "")

            if i < 5:
                result["emails"].append({
                    "subject": subject[:60] or "—",
                    "from": sender[:45] or "—",
                    "date": date[:30] or "—",
                })

            if any(s in sender.lower() for s in _JOB_ALERT_SENDERS) or \
               any(kw in subject.lower() for kw in _JOB_ALERT_SUBJECTS):
                result["job_alert_count"] += 1

        result["status"] = "ok"
        return result

    except Exception as exc:
        result["status"] = "error"
        result["message"] = str(exc)
        return result


@admin_router.message(Command("gmail_test"))
async def cmd_gmail_test(message: Message) -> None:
    import asyncio
    from pathlib import Path

    lines = ["🔍 <b>Gmail Agent — Діагностика</b>\n"]
    lines.append(f"GMAIL_ENABLED: <code>{'true' if settings.GMAIL_ENABLED else 'false'}</code>")
    lines.append(f"GMAIL_USE_MOCK: <code>{'true' if settings.GMAIL_USE_MOCK else 'false'}</code>")
    lines.append(f"GMAIL_MIN_SCORE: <code>{settings.GMAIL_MIN_SCORE}</code>")
    lines.append(f"GMAIL_CHECK_INTERVAL: <code>{settings.GMAIL_CHECK_INTERVAL_MINUTES} хв</code>\n")

    creds_file = settings.GMAIL_CREDENTIALS_FILE
    token_file = settings.GMAIL_TOKEN_FILE
    creds_exists = Path(creds_file).exists()
    token_exists = Path(token_file).exists()

    lines.append(
        f"credentials.json: {'✅ знайдено' if creds_exists else '❌ відсутній'} "
        f"(<code>{creds_file}</code>)"
    )
    lines.append(
        f"token.json: {'✅ знайдено' if token_exists else '❌ відсутній'} "
        f"(<code>{token_file}</code>)"
    )

    if not settings.GMAIL_ENABLED:
        lines.append("\n⚠️ Gmail агент вимкнено. Встанови <code>GMAIL_ENABLED=true</code>.")
        await message.answer("\n".join(lines))
        return

    if settings.GMAIL_USE_MOCK:
        lines.append("\n📋 Режим: <b>MOCK</b> — реальний Gmail не використовується.")
        lines.append("Для реального Gmail: <code>GMAIL_USE_MOCK=false</code>")
        await message.answer("\n".join(lines))
        return

    if not creds_exists:
        lines.append(
            "\n❌ <b>credentials.json не знайдено.</b>\n"
            "Отримай в Google Cloud Console:\n"
            "APIs &amp; Services → Credentials → OAuth 2.0 → Desktop app → Download JSON"
        )
        await message.answer("\n".join(lines))
        return

    if not token_exists:
        lines.append(
            "\n⚠️ <b>gmail_token.json не знайдено.</b>\n"
            "Потрібна перша авторизація:\n"
            "1. Локально: <code>GMAIL_ENABLED=true</code>, <code>GMAIL_USE_MOCK=false</code>\n"
            "2. Запусти бот — браузер відкриється\n"
            "3. Увійди в Google — token.json збережеться\n"
            "4. Завантаж <code>gmail_token.json</code> на сервер"
        )
        await message.answer("\n".join(lines))
        return

    await message.answer("\n".join(lines) + "\n\n⏳ Підключення до Gmail...")

    try:
        loop = asyncio.get_running_loop()
        diag = await asyncio.wait_for(
            loop.run_in_executor(None, _diagnose_gmail_connection, creds_file, token_file),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        await message.answer("⏱ Timeout (30с) при підключенні до Gmail. Перевір credentials.")
        return

    if diag["status"] == "ok":
        result_lines = ["✅ <b>Gmail підключено!</b>\n"]
        result_lines.append("📧 <b>Останні листи в Inbox:</b>")
        for i, em in enumerate(diag["emails"], 1):
            result_lines.append(
                f"\n{i}. <b>{em['subject']}</b>\n"
                f"   Від: {em['from']}\n"
                f"   Дата: {em['date']}"
            )
        result_lines.append(
            f"\n🎯 <b>Потенційних job alerts (з 10 нових): {diag['job_alert_count']}</b>"
        )
        if diag["job_alert_count"] == 0:
            result_lines.append(
                "💡 Підпишись на email-сповіщення на Freelancehunt/Work.ua/Upwork"
            )
        await message.answer("\n".join(result_lines))
    else:
        status_labels = {
            "missing_deps": "❌ Відсутні залежності",
            "need_reauth": "⚠️ Потрібна повторна авторизація",
            "invalid": "❌ Токен недійсний",
            "error": "❌ Помилка підключення",
        }
        label = status_labels.get(diag["status"], "❌ Помилка")
        await message.answer(f"{label}:\n\n{diag['message']}")



# ─── /gmail_scan ──────────────────────────────────────────────────────────────

@admin_router.message(Command("gmail_scan"))
async def cmd_gmail_scan(message: Message) -> None:
    if not settings.GMAIL_ENABLED:
        await message.answer(
            "⚠️ Gmail агент вимкнено.\n"
            "Встанови <code>GMAIL_ENABLED=true</code> в .env для активації."
        )
        return

    mode = "MOCK" if settings.GMAIL_USE_MOCK else "REAL Gmail"
    await message.answer(f"⏳ <b>Gmail scan запущено...</b>\nРежим: <b>{mode}</b>")

    try:
        from gmail_agent.gmail_provider import build_provider
        from gmail_agent.processor import GmailJobProcessor

        provider = build_provider(
            use_mock=settings.GMAIL_USE_MOCK,
            credentials_file=settings.GMAIL_CREDENTIALS_FILE,
            token_file=settings.GMAIL_TOKEN_FILE,
        )

        processor = GmailJobProcessor(
            provider=provider,
            bot=message.bot,
            chat_id=settings.TELEGRAM_CHAT_ID,
            min_score=settings.GMAIL_MIN_SCORE,
        )

        stats = await processor.run()

        summary = (
            f"✅ <b>Gmail scan завершено</b>\n\n"
            f"📬 Знайдено листів: <b>{stats.emails_fetched}</b>\n"
            f"♻️ Дублікатів (вже оброблено): <b>{stats.duplicates_skipped}</b>\n"
            f"🚫 Нерелевантних: <b>{stats.not_relevant}</b>\n"
            f"⬇️ Нижче порогу score &lt; {settings.GMAIL_MIN_SCORE}: <b>{stats.below_threshold}</b>\n"
            f"📨 Відправлено в Telegram: <b>{stats.sent}</b>\n"
            f"❌ Помилок: <b>{stats.errors}</b>"
        )

        if stats.emails_fetched == 0:
            summary += "\n\n📭 Inbox порожній або немає нових листів."
        elif stats.sent == 0 and stats.emails_fetched > 0:
            summary += "\n\n💡 Листи знайдено, але жоден не пройшов фільтр."

        await message.answer(summary)

    except Exception as exc:
        logger.exception("gmail_scan failed")
        await message.answer(f"❌ Помилка gmail scan:\n<code>{exc}</code>")
