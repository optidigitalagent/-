import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from config import settings
from db import AsyncSessionLocal
from db.crud import (
    get_setting,
    set_setting,
    update_order_fields,
    update_order_status,
)
from db.models import Order, Response

from .html_utils import escape_html, safe_http_url
from .keyboards import (
    OrderCb,
    ResponseCb,
    score_picker_keyboard,
)

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.id == settings.TELEGRAM_CHAT_ID)
router.callback_query.filter(F.message.chat.id == settings.TELEGRAM_CHAT_ID)

admin_router = Router()
admin_router.message.filter(F.chat.id == settings.admin_chat_id)

DEFAULT_MIN_SCORE = 6


def _value(record: object, field: str, default: object = None) -> object:
    return record.get(field, default) if isinstance(record, dict) else getattr(record, field, default)


def _live_status_refusal(record: object, recheck_id: str = "") -> str:
    status = str(_value(record, "live_status") or "LIVE_STATUS_UNKNOWN")
    reason = str(
        _value(record, "live_status_evidence")
        or _value(record, "live_status_last_error")
        or "LIVE STATUS NOT VERIFIED"
    )
    retry = (
        f"\nНаступна дія: лише read-only <code>/recheck_live {escape_html(recheck_id)}</code>."
        if status == "LIVE_STATUS_UNKNOWN" and recheck_id
        else "\nНаступна дія: <b>Нічого не надсилати.</b>"
    )
    return (
        "⚠️ <b>Відгук не створено</b>\n\n"
        f"Live status: <b>{escape_html(status)}</b>\n"
        "Bid available: <b>no</b>\n"
        f"Reason: {escape_html(reason)}"
        f"{retry}"
    )


def _quality_refusal(record: object, event_id: str = "") -> str:
    from gmail_agent.quality_gate import quality_errors

    status = str(_value(record, "analysis_quality_status") or "QUALITY_MANUAL_REVIEW")
    errors = quality_errors(record) or ["quality_state_not_proposal_ready"]
    recheck = (
        f"\nНаступна дія: <code>/quality_recheck {escape_html(event_id)}</code>."
        if event_id
        else "\nНаступна дія: перевірити quality state; ставку не надсилати."
    )
    return (
        "🟡 <b>Відгук не доступний</b>\n\n"
        f"Analysis quality: <b>{escape_html(status)}</b>\n"
        "Bid-ready: <b>no</b>\n"
        "Errors: <code>"
        + escape_html(", ".join(errors[:8]))
        + "</code>"
        + recheck
    )


def _quality_allows_action(record: object) -> bool:
    platform = str(_value(record, "platform") or "").casefold()
    if "freelancehunt" not in platform:
        return True
    from gmail_agent.quality_gate import is_proposal_ready

    return is_proposal_ready(record)


def _legacy_order_generation_refusal(order_id: int) -> str:
    return (
        "🟡 <b>Legacy proposal generation disabled</b>\n\n"
        "Новий неперевірений текст не створено. Цей direct Order path не має "
        "повного канонічного Stage 4 package.\n"
        f"Використайте відповідний feed/Gmail event через <code>/reply_job …</code>; "
        f"legacy order <code>#{order_id}</code> залишається лише для аудиту."
    )


def _response_draft_errors(draft: object, order: object) -> list[str]:
    """Validate the exact Response text/version that would be copied."""

    from gmail_agent.quality_gate import (
        ANALYSIS_VERSION,
        PROPOSAL_READY_QUALITY_STATUSES,
        proposal_text_hash,
    )

    errors: list[str] = []
    version = str(_value(draft, "proposal_version") or "")
    if not version:
        errors.append("response_proposal_version_missing")
    content_hash = str(_value(draft, "proposal_content_sha256") or "")
    if not content_hash:
        errors.append("response_content_hash_missing")
    elif content_hash != proposal_text_hash(str(_value(draft, "text") or "")):
        errors.append("response_content_hash_mismatch")
    if str(_value(draft, "analysis_quality_status") or "") not in PROPOSAL_READY_QUALITY_STATUSES:
        errors.append("response_quality_not_validated")
    if not isinstance(_value(draft, "quality_checked_at"), datetime):
        errors.append("response_quality_timestamp_missing")
    if str(_value(draft, "source_job_identity") or "") != f"order:{_value(order, 'id')}":
        errors.append("response_source_identity_mismatch")
    validated_live = _value(draft, "validated_live_status_at")
    current_live = _value(order, "live_status_checked_at")
    if not isinstance(validated_live, datetime) or not isinstance(current_live, datetime):
        errors.append("response_live_validation_missing")
    else:
        left = validated_live if validated_live.tzinfo else validated_live.replace(tzinfo=timezone.utc)
        right = current_live if current_live.tzinfo else current_live.replace(tzinfo=timezone.utc)
        if abs((right - left).total_seconds()) > 60:
            errors.append("response_live_validation_stale")
    if version != str(_value(order, "proposal_version") or ""):
        errors.append("response_version_differs_from_validated_order")
    if str(_value(order, "analysis_version") or "") != ANALYSIS_VERSION:
        errors.append("response_parent_analysis_version_stale")
    if str(_value(draft, "result") or "") == "sent":
        errors.append("response_version_already_delivered")
    return errors


async def _ensure_order_current_biddable(
    order: Order, *, force: bool = False, manual: bool = False
):
    """Detach, read live page, then persist in a separate short transaction."""

    from gmail_agent.live_status import (
        FreelancehuntLiveStatusChecker,
        LiveStatus,
        ensure_current_biddable_status,
    )

    async def persist(result) -> None:
        previous_count = int(getattr(order, "live_status_retry_count", 0) or 0)
        retry_count = previous_count + int(result.status == LiveStatus.LIVE_STATUS_UNKNOWN)
        if result.status == LiveStatus.ACTIVE_BIDDABLE:
            next_status = "live_status_active_manual" if manual else order.status
        elif result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
            next_status = (
                "live_status_unknown_exhausted"
                if retry_count >= 3
                else "live_status_pending"
            )
        else:
            next_status = "live_status_terminal"
        fields = {
            "live_status": result.status.value,
            "live_status_checked_at": result.checked_at,
            "live_status_evidence": result.evidence,
            "biddable": result.biddable,
            "live_status_retry_count": retry_count,
            "live_status_last_error": result.last_error,
            "qualified": bool(getattr(order, "qualified", False)) if result.biddable else False,
            "status": next_status,
        }
        async with AsyncSessionLocal() as session:
            await update_order_fields(session, order.id, fields)
        for key, value in fields.items():
            setattr(order, key, value)

    checker = FreelancehuntLiveStatusChecker(cache_ttl_seconds=0)
    return await ensure_current_biddable_status(
        order, checker, persist, force=force
    )


async def _ensure_gmail_job_current_biddable(
    job_id: str,
    job: dict,
    repository: object | None,
    *,
    force: bool = False,
    manual: bool = False,
):
    from gmail_agent.live_status import (
        FreelancehuntLiveStatusChecker,
        LiveStatus,
        ensure_current_biddable_status,
    )

    async def persist(result) -> None:
        previous_count = int(job.get("live_status_retry_count") or 0)
        retry_count = previous_count + int(result.status == LiveStatus.LIVE_STATUS_UNKNOWN)
        if result.status == LiveStatus.ACTIVE_BIDDABLE:
            next_status = "live_status_active_manual" if manual else str(job.get("status") or "sent")
        elif result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
            next_status = (
                "live_status_unknown_exhausted"
                if retry_count >= 3
                else "live_status_pending"
            )
        else:
            next_status = "live_status_terminal"
        fields = {
            "live_status": result.status.value,
            "live_status_checked_at": result.checked_at,
            "live_status_evidence": result.evidence,
            "biddable": result.biddable,
            "live_status_retry_count": retry_count,
            "live_status_last_error": result.last_error,
            "qualified": bool(job.get("qualified")) if result.biddable else False,
            "status": next_status,
        }
        job.update(fields)
        if repository is not None:
            import inspect

            update_result = repository.update_job_fields(job_id, fields)
            if inspect.isawaitable(update_result):
                await update_result
        _gmail_job_store[job_id] = job

    checker = FreelancehuntLiveStatusChecker(cache_ttl_seconds=0)
    return await ensure_current_biddable_status(
        job, checker, persist, force=force
    )


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

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, callback_data.order_id)

    if not order:
        await callback.message.edit_text("❌ Замовлення не знайдено")
        return

    guard = await _ensure_order_current_biddable(order)
    if not guard.allowed:
        await callback.message.edit_text(
            _live_status_refusal(order, str(order.id)), reply_markup=None
        )
        return
    if not _quality_allows_action(order):
        await callback.message.edit_text(
            _quality_refusal(order), reply_markup=None
        )
        return

    await callback.message.edit_text(
        _legacy_order_generation_refusal(order.id),
        reply_markup=None,
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
        order = await session.get(Order, callback_data.order_id)

    if order is None:
        await callback.answer("❌ Помилка: дані не знайдено", show_alert=True)
        return
    guard = await _ensure_order_current_biddable(order)
    if not guard.allowed:
        await callback.message.edit_text(
            _live_status_refusal(order, str(order.id)), reply_markup=None
        )
        return

    draft_errors: list[str] = []
    async with AsyncSessionLocal() as session:
        # Lock and revalidate the exact rows immediately before the state
        # transition. This prevents a changed draft/version from winning the
        # gap between the external live check and manual-copy authorization.
        draft = await session.get(
            Response, callback_data.response_id, with_for_update=True
        )
        locked_order = await session.get(
            Order, callback_data.order_id, with_for_update=True
        )
        if draft is None:
            draft_errors.append("response_missing")
        if locked_order is None:
            draft_errors.append("response_parent_missing")
        elif not _quality_allows_action(locked_order):
            draft_errors.append("response_parent_not_proposal_ready")
        if draft is not None and locked_order is not None:
            draft_errors.extend(_response_draft_errors(draft, locked_order))
        draft_text = str(_value(draft, "text") or "") if draft is not None else ""
        draft_version = (
            str(_value(draft, "proposal_version") or "") if draft is not None else ""
        )
        order_url = str(_value(locked_order, "url") or "") if locked_order is not None else ""

    if draft_errors:
        await callback.message.edit_text(
            "🟡 <b>Response draft blocked</b>\n\n"
            "Exact draft/version is not copy-safe: <code>"
            + escape_html(", ".join(dict.fromkeys(draft_errors)))
            + "</code>\nOnly bounded regeneration through the canonical "
            "feed/Gmail package is allowed.",
            reply_markup=None,
        )
        return

    await callback.message.edit_text(
        "✅ Скопіюй відгук нижче та відправ вручну на платформі.",
        reply_markup=None,
    )
    safe_url = safe_http_url(order_url)
    link = (
        f"\n\n🔗 <a href='{escape_html(safe_url)}'>Відкрити замовлення</a>"
        if safe_url
        else ""
    )
    await callback.message.answer(
        f"📋 <b>Відповідь для копіювання:</b>\n\n{escape_html(draft_text)}{link}"
    )

    # Telegram accepted the copy message. Only now may the exact unchanged
    # Response and its parent move to sent.
    async with AsyncSessionLocal() as session:
        delivered_draft = await session.get(
            Response, callback_data.response_id, with_for_update=True
        )
        delivered_order = await session.get(
            Order, callback_data.order_id, with_for_update=True
        )
        post_send_errors: list[str] = []
        if delivered_draft is None or delivered_order is None:
            post_send_errors.append("response_or_parent_missing_after_delivery")
        else:
            post_send_errors.extend(
                _response_draft_errors(delivered_draft, delivered_order)
            )
            if str(delivered_draft.text or "") != draft_text:
                post_send_errors.append("response_text_changed_during_delivery")
            if str(delivered_draft.proposal_version or "") != draft_version:
                post_send_errors.append("response_version_changed_during_delivery")
        if not post_send_errors:
            delivered_draft.result = "sent"
            delivered_draft.sent_at = datetime.now(timezone.utc)
            delivered_order.status = "sent"
            await session.commit()
        else:
            logger.error(
                "Response delivered but sent state was not committed: %s",
                ",".join(dict.fromkeys(post_send_errors)),
            )


@router.callback_query(ResponseCb.filter(F.action == "rewrite"))
async def cb_rewrite(callback: CallbackQuery, callback_data: ResponseCb) -> None:
    await callback.answer()

    async with AsyncSessionLocal() as session:
        order = await session.get(Order, callback_data.order_id)

    if not order:
        await callback.message.edit_text("❌ Замовлення не знайдено")
        return

    guard = await _ensure_order_current_biddable(order)
    if not guard.allowed:
        await callback.message.edit_text(
            _live_status_refusal(order, str(order.id)), reply_markup=None
        )
        return
    if not _quality_allows_action(order):
        await callback.message.edit_text(
            _quality_refusal(order), reply_markup=None
        )
        return

    await callback.message.edit_text(
        _legacy_order_generation_refusal(order.id),
        reply_markup=None,
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

    guard = await _ensure_order_current_biddable(order)
    if not guard.allowed:
        await message.answer(_live_status_refusal(order, str(order.id)))
        return
    if not _quality_allows_action(order):
        await message.answer(_quality_refusal(order))
        return

    await message.answer(_legacy_order_generation_refusal(order.id))


# ─── Gmail agent commands (/reply_job, /skip_job) ────────────────────────────

_gmail_job_store: dict[str, dict] = {}


def register_gmail_job_analysis(analysis_dict: dict) -> None:
    """Called by gmail_agent.processor to register analyses for /reply_job."""
    _gmail_job_store[str(analysis_dict["email_id"])] = analysis_dict
    try:
        from gmail_agent.job_store import save_job
        save_job(analysis_dict)
    except Exception:
        logger.exception("Failed to persist Gmail job analysis")


@router.message(Command("reply_job"))
async def cmd_reply_job(message: Message) -> None:
    raw = (message.text or "").strip().split()
    if len(raw) < 2:
        await message.answer(
            "❌ Використання: <code>/reply_job &lt;event_id&gt; [rewrite]</code>"
        )
        return

    job_id = raw[1].strip()
    rewrite = len(raw) >= 3 and raw[2].casefold() == "rewrite"
    job = None
    repository = None
    repository_unavailable = False
    try:
        from dataclasses import asdict, is_dataclass
        from gmail_agent.storage import PostgresGmailRepository

        repository = PostgresGmailRepository(AsyncSessionLocal)
        stored_job = await repository.get_job(job_id)
        if stored_job is not None:
            job = asdict(stored_job) if is_dataclass(stored_job) else dict(stored_job)
            job.setdefault("email_id", job_id)
            _gmail_job_store[job_id] = job
    except Exception:
        repository_unavailable = True
        logger.exception("Failed to load Gmail job from PostgreSQL")

    if not job:
        job = _gmail_job_store.get(job_id)
    if not job and repository_unavailable:
        try:
            from gmail_agent.job_store import get_job

            job = get_job(job_id)
            if job:
                _gmail_job_store[job_id] = job
        except Exception:
            logger.exception("Failed to load legacy Gmail job analysis")

    if not job:
        await message.answer(
            f"❌ Замовлення <code>{escape_html(job_id)}</code> не знайдено.\n"
            "Можливо, воно вже застаріло або бот перезапускався."
        )
        return

    project_event = str(job.get("event_type") or "") in {
        "PROJECT_SINGLE",
        "PROJECT_DIGEST",
        "PROJECT_FEED",
    }
    is_freelancehunt = "freelancehunt" in str(job.get("platform") or "").casefold()
    if (
        project_event
        and is_freelancehunt
        and (
            str(job.get("live_status") or "") != "ACTIVE_BIDDABLE"
            or job.get("biddable") is not True
        )
    ):
        await message.answer(_live_status_refusal(job, job_id))
        return
    if not (project_event and is_freelancehunt and repository is not None):
        await message.answer(
            "🟡 Новий proposal заблоковано: потрібен канонічний "
            "Freelancehunt feed/Gmail package у PostgreSQL."
        )
        return

    from gmail_agent.live_status import FreelancehuntLiveStatusChecker
    from gmail_agent.processor import GmailJobProcessor
    from gmail_agent.proposal_service import ProposalGenerationStatus
    from gmail_agent.quality_gate import is_proposal_ready
    from gmail_agent.telegram_notifier import format_quality_review_card_parts

    processor = GmailJobProcessor(
        provider=object(),
        bot=message.bot,
        chat_id=settings.TELEGRAM_CHAT_ID,
        min_score=0.0,
        repository=repository,
        live_status_checker=FreelancehuntLiveStatusChecker(),
    )

    async def send_copy(analysis) -> bool:
        url = safe_http_url(analysis.url)
        link = (
            f'\n\n🔗 <a href="{escape_html(url)}">Відкрити подію</a>'
            if url else ""
        )
        await message.answer(
            f"📝 <b>Перевірена відповідь · {escape_html(analysis.proposal_version)}</b>\n\n"
            f"{escape_html(analysis.proposal_draft)}{link}"
        )
        return True

    saved_proposal = str(job.get("proposal_draft") or "").strip()
    if saved_proposal and not rewrite:
        delivered = await processor.deliver_validated_proposal_text_version(
            job_id, send_copy
        )
        if not delivered:
            current = await repository.get_job(job_id)
            if current is not None and is_proposal_ready(current):
                await message.answer(
                    "🟡 Перевірена proposal version не була доставлена; "
                    "повторіть явну команду /reply_job."
                )
            elif current is not None and current.live_status != "ACTIVE_BIDDABLE":
                await message.answer(_live_status_refusal(current, job_id))
            else:
                await message.answer(_quality_refusal(current or job, job_id))
        return

    if rewrite and not _quality_allows_action(job):
        await message.answer(_quality_refusal(job, job_id))
        return

    await message.answer(
        f"⏳ {'Переписую' if rewrite else 'Генерую'} і перевіряю відгук для "
        f"<b>{escape_html(job.get('title', job_id))}</b>…"
    )
    result = await processor.generate_validate_and_persist_proposal(
        job_id, rewrite=rewrite
    )
    if result.status == ProposalGenerationStatus.VALIDATED_PROPOSAL.value:
        delivered = await processor.deliver_validated_proposal_text_version(
            job_id, send_copy, live_status_already_checked=True
        )
        if not delivered:
            await message.answer(
                "🟡 Перевірена proposal version не була доставлена або перестала бути актуальною."
            )
        return
    if result.status == ProposalGenerationStatus.LIVE_STATUS_BLOCKED.value:
        current = await repository.get_job(job_id)
        await message.answer(_live_status_refusal(current or job, job_id))
        return
    if result.status == ProposalGenerationStatus.PROVIDER_RETRYABLE.value:
        await message.answer(
            "🟡 Provider failure: жоден draft не показано; стан retryable."
        )
        return
    for part in format_quality_review_card_parts(result.analysis):
        await message.answer(part, disable_web_page_preview=True)


@router.message(Command("skip_job"))
async def cmd_skip_job(message: Message) -> None:
    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2:
        await message.answer("❌ Використання: <code>/skip_job &lt;email_id&gt;</code>")
        return

    job_id = raw[1].strip()
    skipped = False
    repository_unavailable = False
    try:
        from gmail_agent.storage import PostgresGmailRepository

        repository = PostgresGmailRepository(AsyncSessionLocal)
        skipped = await repository.update_job_status(job_id, "skipped") is not None
    except Exception:
        repository_unavailable = True
        logger.exception("Failed to update Gmail job status in PostgreSQL")

    # Compatibility lookup only when PostgreSQL cannot be reached. A skip is a
    # durable status transition, so neither the cache nor legacy JSON is deleted.
    if repository_unavailable:
        legacy_job = _gmail_job_store.get(job_id)
        if legacy_job is None:
            try:
                from gmail_agent.job_store import get_job

                legacy_job = get_job(job_id)
            except Exception:
                logger.exception("Failed to load legacy Gmail job analysis")
        if legacy_job is not None:
            legacy_job["status"] = "skipped"
            _gmail_job_store[job_id] = legacy_job
            skipped = True

    if skipped:
        await message.answer(f"✅ Замовлення <code>{escape_html(job_id)}</code> пропущено.")
    else:
        await message.answer(
            f"⚠️ Замовлення <code>{escape_html(job_id)}</code> не знайдено "
            "(вже пропущено або не існує)."
        )


# ─── Admin commands ───────────────────────────────────────────────────────────

@admin_router.message(Command("recheck_live"))
async def cmd_recheck_live(message: Message) -> None:
    """Force one anonymous read-only status refresh; never create a proposal."""

    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip():
        await message.answer(
            "❌ Використання: <code>/recheck_live &lt;order_or_event_id&gt;</code>"
        )
        return
    target = raw[1].strip()

    order = None
    if target.isdigit():
        async with AsyncSessionLocal() as session:
            order = await session.get(Order, int(target))
    if order is not None:
        guard = await _ensure_order_current_biddable(order, force=True, manual=True)
        record: object = order
    else:
        repository = None
        job = None
        try:
            from dataclasses import asdict
            from gmail_agent.storage import PostgresGmailRepository

            repository = PostgresGmailRepository(AsyncSessionLocal)
            stored = await repository.get_job(target)
            if stored is not None:
                job = asdict(stored)
                job.setdefault("email_id", target)
        except Exception:
            logger.exception("Failed to load Gmail job for read-only live recheck")
        if job is None:
            job = _gmail_job_store.get(target)
        if job is None:
            await message.answer("❌ Запис для read-only перевірки не знайдено.")
            return
        guard = await _ensure_gmail_job_current_biddable(
            target, job, repository, force=True, manual=True
        )
        record = job

    checked_at = guard.result.checked_at.isoformat(timespec="seconds")
    if guard.allowed:
        next_action = "Окремою наступною командою можна запросити відгук."
    elif guard.result.status.value == "LIVE_STATUS_UNKNOWN":
        next_action = "Статус не підтверджено; можна повторити лише read-only перевірку."
    else:
        next_action = "Відгук заблоковано; нічого не надсилати."
    await message.answer(
        "🔎 <b>Read-only live recheck</b>\n\n"
        f"Live status: <b>{escape_html(guard.result.status.value)}</b>\n"
        f"Bid available: <b>{'yes' if guard.allowed else 'no'}</b>\n"
        f"Checked: <code>{escape_html(checked_at)}</code>\n"
        f"Reason: {escape_html(str(_value(record, 'live_status_evidence') or guard.result.evidence))}\n"
        f"Наступна дія: {escape_html(next_action)}"
    )


@admin_router.message(Command("quality_recheck"))
async def cmd_quality_recheck(message: Message) -> None:
    """Run one live refresh and at most one quality reanalysis; never bid."""

    raw = (message.text or "").strip().split(maxsplit=1)
    if len(raw) < 2 or not raw[1].strip():
        await message.answer(
            "❌ Використання: <code>/quality_recheck &lt;event_id&gt;</code>"
        )
        return
    event_id = raw[1].strip()
    try:
        from gmail_agent.live_status import FreelancehuntLiveStatusChecker
        from gmail_agent.processor import GmailJobProcessor, ProcessorStats
        from gmail_agent.quality_gate import QualityStatus, is_proposal_ready
        from gmail_agent.storage import PostgresGmailRepository

        repository = PostgresGmailRepository(AsyncSessionLocal)
        stored = await repository.get_job(event_id)
        if stored is None:
            await message.answer("❌ Подію для quality recheck не знайдено.")
            return
        stats = ProcessorStats()
        processor = GmailJobProcessor(
            provider=object(),
            bot=message.bot,
            chat_id=settings.TELEGRAM_CHAT_ID,
            min_score=0.0,
            repository=repository,
            live_status_checker=FreelancehuntLiveStatusChecker(),
        )
        reanalyzed, delivered = await processor.recheck_quality_and_deliver(
            event_id, stats
        )
        if not reanalyzed.analysis_succeeded:
            await message.answer(
                "🟡 Quality recheck provider failure; жоден draft не показано, "
                "стан retryable."
            )
            return
        if reanalyzed.live_status != "ACTIVE_BIDDABLE":
            await message.answer(_live_status_refusal(reanalyzed, event_id))
            return
        if reanalyzed.analysis_quality_status == QualityStatus.NON_EXECUTABLE.value:
            await message.answer("ℹ️ Quality recheck: NON_EXECUTABLE; proposal відсутній.")
            return
        if not is_proposal_ready(reanalyzed):
            await message.answer(
                "🟡 Quality recheck завершено у MANUAL_REVIEW; usable proposal "
                + ("відсутній, source-context card доставлена." if delivered else "відсутній.")
            )
            return
        if delivered:
            await message.answer(
                "✅ Quality recheck завершено; exact proposal version доставлена "
                "через єдиний version-aware path."
            )
        elif is_proposal_ready(reanalyzed):
            await message.answer(
                "ℹ️ Ця proposal version вже доставлена; duplicate card не надіслано."
            )
    except Exception as exc:
        logger.exception("Admin quality recheck failed")
        await message.answer(
            "❌ Quality recheck failed closed: "
            f"<code>{escape_html(type(exc).__name__)}</code>. Ставку не надсилати."
        )


@admin_router.message(Command("quality_backfill"))
async def cmd_quality_backfill(message: Message) -> None:
    """Admin-only controlled preview/execute path for legacy active rows."""

    parts = (message.text or "").strip().split()
    if len(parts) != 3 or parts[1] not in {"preview", "execute"} or not parts[2].isdigit():
        await message.answer(
            "❌ Використання: <code>/quality_backfill preview|execute &lt;1..100&gt;</code>"
        )
        return
    limit = int(parts[2])
    if not 1 <= limit <= 100:
        await message.answer("❌ limit має бути від 1 до 100.")
        return
    try:
        from gmail_agent.live_status import FreelancehuntLiveStatusChecker
        from gmail_agent.processor import GmailJobProcessor
        from gmail_agent.storage import PostgresGmailRepository

        processor = GmailJobProcessor(
            provider=object(),
            bot=message.bot,
            chat_id=settings.TELEGRAM_CHAT_ID,
            min_score=0.0,
            repository=PostgresGmailRepository(AsyncSessionLocal),
            live_status_checker=FreelancehuntLiveStatusChecker(),
        )
        if parts[1] == "preview":
            preview = await processor.run_quality_backfill_preview(limit)
            await message.answer(
                "🔎 <b>Quality backfill preview — counts only</b>\n"
                f"Bounded limit: <b>{preview.limit}</b>\n"
                f"Candidates: <b>{preview.candidates}</b>\n"
                f"Score missing: <b>{preview.missing_score}</b>\n"
                f"Score invalid: <b>{preview.invalid_score}</b>\n"
                f"Score real zero: <b>{preview.actual_zero_score}</b>\n"
                f"Fit missing: <b>{preview.missing_fit_state}</b>\n"
                f"Fit invalid: <b>{preview.invalid_fit_state}</b>\n"
                f"Fit real zero: <b>{preview.actual_zero_fit}</b>\n"
                f"Missing price: <b>{preview.missing_price}</b>\n"
                f"Missing timeline: <b>{preview.missing_timeline}</b>\n"
                f"Missing proposal: <b>{preview.missing_proposal}</b>\n"
                f"Invalid evidence: <b>{preview.missing_or_invalid_evidence}</b>\n"
                "No rows or Telegram cards changed."
            )
            return
        stats = await processor.run_quality_backfill(
            limit, send_replacements=False
        )
        await message.answer(
            "✅ <b>Bounded quality backfill complete</b>\n"
            f"AI analyzed: <b>{stats.ai_analyzed}</b>\n"
            f"VALID: <b>{stats.quality_valid}</b>\n"
            f"REPAIRED: <b>{stats.quality_repaired}</b>\n"
            f"MANUAL_REVIEW: <b>{stats.quality_manual_review}</b>\n"
            f"NON_EXECUTABLE: <b>{stats.quality_non_executable}</b>\n"
            f"FAILED: <b>{stats.quality_failed}</b>\n"
            "Replacement cards: <b>0</b> (explicit send path not requested)."
        )
    except Exception as exc:
        logger.exception("Quality backfill command failed")
        await message.answer(
            "❌ Quality backfill failed closed: "
            f"<code>{escape_html(type(exc).__name__)}</code>."
        )

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
    import asyncio
    import json
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
        f"\n⚠️ Остання помилка: <b>{escape_html(state.last_auto_error)}</b>"
        if state.last_auto_error else ""
    )

    # Gmail Agent block
    gmail_enabled = settings.GMAIL_ENABLED
    gmail_mode = "MOCK" if settings.GMAIL_USE_MOCK else "REAL Gmail"
    gmail_next_run = "—"
    gmail_telemetry = None
    gmail_memory_fallback = False

    if state.scheduler is not None and state.scheduler.running:
        gmail_job = state.scheduler.get_job("check_gmail_jobs")
        if gmail_job:
            gmail_next_run = _fmt_dt(gmail_job.next_run_time)

    try:
        from gmail_agent.storage import PostgresGmailRepository

        repository = PostgresGmailRepository(AsyncSessionLocal)
        history = await asyncio.wait_for(
            repository.list_scan_runs(limit=1), timeout=5.0
        )
        # Scan runs are appended only after processor completion, so an older
        # row without finished_at is still a completed legacy record.
        if history:
            last = history[0]
            gmail_telemetry = {
                "timestamp": last.finished_at or last.started_at,
                "trigger": last.trigger,
                "emails": last.emails_inspected,
                "candidates": last.candidates_found,
                "ai_analyzed": last.ai_analyzed,
                "relevant": last.relevant,
                "qualified": last.qualified,
                "duplicates": last.duplicates,
                "sent": last.sent,
                "sent_from_queue": last.sent_from_queue,
                "errors": last.errors,
                "mailbox_alias": getattr(last, "mailbox_alias", None) or "—",
                "latency": getattr(last, "max_detection_latency_seconds", None),
                "event_counts": getattr(last, "event_counts", "{}") or "{}",
                "quality_valid": getattr(last, "quality_valid", 0),
                "quality_repaired": getattr(last, "quality_repaired", 0),
                "quality_manual_review": getattr(last, "quality_manual_review", 0),
                "quality_failed": getattr(last, "quality_failed", 0),
                "repair_calls": getattr(last, "repair_calls", 0),
                "proposal_versions_sent": getattr(last, "proposal_versions_sent", 0),
            }
    except Exception as exc:
        gmail_memory_fallback = True
        logger.error(
            "Failed to read latest completed Gmail scan from PostgreSQL: %s",
            type(exc).__name__,
        )
        if state.gmail_scan_history:
            last = state.gmail_scan_history[-1]
            gmail_telemetry = {
                "timestamp": last.get("finished_at") or last.get("timestamp"),
                "trigger": last.get("trigger", "—"),
                "emails": last.get("emails", last.get("emails_found", 0)),
                "candidates": last.get("candidates", 0),
                "ai_analyzed": last.get("ai_analyzed", 0),
                "relevant": last.get("relevant", 0),
                "qualified": last.get("qualified", 0),
                "duplicates": last.get("duplicates", 0),
                "sent": last.get("sent", 0),
                "sent_from_queue": last.get("sent_from_queue", 0),
                "errors": last.get("errors", 0),
                "mailbox_alias": last.get("mailbox_alias", "—"),
                "latency": last.get("max_detection_latency_seconds"),
                "event_counts": last.get("event_counts", "{}"),
                "quality_valid": last.get("quality_valid", 0),
                "quality_repaired": last.get("quality_repaired", 0),
                "quality_manual_review": last.get("quality_manual_review", 0),
                "quality_failed": last.get("quality_failed", 0),
                "repair_calls": last.get("repair_calls", 0),
                "proposal_versions_sent": last.get("proposal_versions_sent", 0),
            }

    if gmail_telemetry is None:
        gmail_telemetry = {
            "timestamp": None,
            "trigger": "—",
            "emails": "—",
            "candidates": "—",
            "ai_analyzed": "—",
            "relevant": "—",
            "qualified": "—",
            "duplicates": "—",
            "sent": "—",
            "sent_from_queue": "—",
            "errors": "—",
            "mailbox_alias": "—",
            "latency": None,
            "event_counts": "{}",
            "quality_valid": "—",
            "quality_repaired": "—",
            "quality_manual_review": "—",
            "quality_failed": "—",
            "repair_calls": "—",
            "proposal_versions_sent": "—",
        }

    try:
        raw_event_counts = gmail_telemetry.get("event_counts", "{}")
        event_counts = (
            raw_event_counts
            if isinstance(raw_event_counts, dict)
            else json.loads(raw_event_counts)
        )
        event_counts_text = ", ".join(
            f"{key}={value}" for key, value in sorted(event_counts.items())
        ) or "—"
    except (TypeError, ValueError, json.JSONDecodeError):
        event_counts_text = "—"
    latency = gmail_telemetry.get("latency")
    latency_text = "—" if latency is None else f"{float(latency):.1f}s"

    telemetry_source = (
        "\nTelemetry source: <b>memory fallback</b>" if gmail_memory_fallback else ""
    )

    gmail_block = (
        "\n\n📬 <b>Gmail Agent</b>\n"
        f"Enabled: <b>{'✅ так' if gmail_enabled else '❌ ні'}</b>\n"
        f"Mode: <b>{gmail_mode}</b>\n"
        f"OAuth identity: <b>{escape_html(gmail_telemetry['mailbox_alias'])}</b>\n"
        f"Next scan: <b>{gmail_next_run}</b>\n"
        f"Last completed scan: <b>{_fmt_dt(gmail_telemetry['timestamp'])}</b>\n"
        f"Trigger: <b>{escape_html(gmail_telemetry['trigger'])}</b>\n"
        f"Emails: <b>{gmail_telemetry['emails']}</b>\n"
        f"Candidates: <b>{gmail_telemetry['candidates']}</b>\n"
        f"AI analyzed: <b>{gmail_telemetry['ai_analyzed']}</b>\n"
        f"Relevant: <b>{gmail_telemetry['relevant']}</b>\n"
        f"Qualified: <b>{gmail_telemetry['qualified']}</b>\n"
        f"Duplicates: <b>{gmail_telemetry['duplicates']}</b>\n"
        f"Sent: <b>{gmail_telemetry['sent']}</b>\n"
        f"Sent from queue: <b>{gmail_telemetry['sent_from_queue']}</b>\n"
        f"Errors: <b>{gmail_telemetry['errors']}</b>"
        f"\nMax detection latency: <b>{latency_text}</b>"
        f"\nEvent counts: <b>{escape_html(event_counts_text)}</b>"
        f"\nQuality VALID/REPAIRED: <b>{gmail_telemetry['quality_valid']}/{gmail_telemetry['quality_repaired']}</b>"
        f"\nQuality MANUAL/FAILED: <b>{gmail_telemetry['quality_manual_review']}/{gmail_telemetry['quality_failed']}</b>"
        f"\nQuality repair calls: <b>{gmail_telemetry['repair_calls']}</b>"
        f"\nProposal versions sent: <b>{gmail_telemetry['proposal_versions_sent']}</b>"
        + telemetry_source
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
        + gmail_block
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


# ─── /gmail_account ───────────────────────────────────────────────────────────

@admin_router.message(Command("gmail_account"))
async def cmd_gmail_account(message: Message) -> None:
    """Show only safe Gmail OAuth identity details to the admin chat."""
    import asyncio

    if settings.GMAIL_USE_MOCK:
        await message.answer(
            "Connected Gmail account: <code>mock</code>\n"
            "Inbox messages count: <b>0</b>\n"
            "OAuth status: <b>MOCK</b>"
        )
        return

    try:
        from gmail_agent.gmail_provider import RealGmailProvider, mask_email_address

        provider = RealGmailProvider(
            credentials_file=settings.GMAIL_CREDENTIALS_FILE,
            token_file=settings.GMAIL_TOKEN_FILE,
            expected_account=getattr(settings, "GMAIL_EXPECTED_ACCOUNT", None),
            lookback_days=getattr(settings, "GMAIL_LOOKBACK_DAYS", 7),
        )
        profile = await asyncio.wait_for(provider.get_account_profile(), timeout=30.0)
        await message.answer(
            f"Connected Gmail account: <code>{escape_html(mask_email_address(profile['email_address']))}</code>\n"
            f"Inbox messages count: <b>{int(profile['inbox_messages_count'])}</b>\n"
            f"OAuth status: <b>{escape_html(profile['oauth_status'])}</b>"
        )
    except Exception as exc:
        error_type = escape_html(type(exc).__name__)
        logger.warning("gmail_account failed (%s)", type(exc).__name__)
        await message.answer(
            "Connected Gmail account: <code>unavailable</code>\n"
            "Inbox messages count: <b>unavailable</b>\n"
            f"OAuth status: <b>ERROR ({error_type})</b>"
        )


# ─── /gmail_test ──────────────────────────────────────────────────────────────

def _diagnose_gmail_connection(creds_file: str, token_file: str) -> dict:
    """
    Check Gmail connection without triggering browser OAuth flow.
    Sync — runs in executor. Never calls flow.run_local_server().
    Checks GMAIL_TOKEN_JSON env var first, falls back to token_file.
    Returns up to 10 emails with: subject, from, date, msg_id, size_kb, links, attachments.
    """
    import base64 as _b64
    import json as _json
    import os as _os
    import re as _re

    result: dict = {
        "status": "unknown",
        "message": "",
        "emails": [],
        "sender_match_count": 0,
        "subject_match_count": 0,
        "job_alert_count": 0,
    }
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        result["status"] = "missing_deps"
        result["message"] = "Залежності не встановлено. Запусти: pip install google-auth-oauthlib google-api-python-client"
        return result

    def _extract_text(payload: dict) -> str:
        body_data = payload.get("body", {}).get("data", "")
        text = ""
        if body_data:
            try:
                text = _b64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
            except Exception:
                pass
        for part in payload.get("parts", []):
            text += _extract_text(part)
        return text

    def _has_attachments(payload: dict) -> bool:
        fname = payload.get("filename", "")
        if fname and payload.get("body", {}).get("size", 0) > 0:
            return True
        return any(_has_attachments(p) for p in payload.get("parts", []))

    try:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
        token_json_env = _os.getenv("GMAIL_TOKEN_JSON")
        _from_env = False

        if token_json_env:
            try:
                creds = Credentials.from_authorized_user_info(
                    _json.loads(token_json_env), scopes
                )
                _from_env = True
            except Exception as exc:
                result["status"] = "error"
                result["message"] = f"Invalid GMAIL_TOKEN_JSON: {exc}"
                return result
        elif _os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, scopes)
        else:
            result["status"] = "no_token"
            result["message"] = (
                "Токен не знайдено.\n"
                "На Railway: встанови GMAIL_TOKEN_JSON\n"
                "Локально: запусти OAuth flow та збережи gmail_token.json"
            )
            return result

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    if "invalid_grant" in str(exc):
                        result["status"] = "need_reauth"
                        result["message"] = (
                            "Gmail OAuth token cannot be refreshed (invalid_grant).\n"
                            "Run locally: python -m gmail_agent.oauth_local "
                            "--credentials credentials.json --token gmail_token.json\n"
                            "Then update GMAIL_TOKEN_JSON on Railway."
                        )
                        return result
                    raise
                if not _from_env:
                    try:
                        with open(token_file, "w") as f:
                            f.write(creds.to_json())
                    except OSError:
                        pass
            else:
                result["status"] = "need_reauth"
                result["message"] = (
                    "Токен недійсний або прострочений без refresh_token.\n"
                    "Запусти OAuth локально, отримай новий token.json,\n"
                    "встанови GMAIL_TOKEN_JSON на Railway."
                )
                return result

        from googleapiclient.discovery import build
        svc = build("gmail", "v1", credentials=creds)

        expected_account = _os.getenv("GMAIL_EXPECTED_ACCOUNT", "").strip().casefold()
        if not expected_account:
            result["status"] = "identity_required"
            result["message"] = "GMAIL_EXPECTED_ACCOUNT is required in real mode"
            return result
        profile = svc.users().getProfile(userId="me").execute()
        observed_account = str(profile.get("emailAddress", "")).strip().casefold()
        if observed_account != expected_account:
            result["status"] = "identity_mismatch"
            result["message"] = "Gmail OAuth mailbox mismatch; scan refused"
            return result

        resp = svc.users().messages().list(
            userId="me", labelIds=["INBOX"], maxResults=10
        ).execute()
        messages = resp.get("messages", [])

        from gmail_agent.gmail_provider import build_email_diagnostic

        for meta in messages[:10]:
            raw = svc.users().messages().get(
                userId="me",
                id=meta["id"],
                format="full",
            ).execute()
            payload = raw.get("payload", {})
            headers = {
                h["name"].lower(): h["value"]
                for h in payload.get("headers", [])
            }
            sender = headers.get("from", "—")
            subject = headers.get("subject", "—")
            date = headers.get("date", "—")
            msg_id = raw.get("id", "—")
            size_bytes = raw.get("sizeEstimate", 0)

            body_text = _extract_text(payload)
            link_count = len(_re.findall(r'https?://', body_text))
            has_att = _has_attachments(payload)

            result["emails"].append({
                "subject": subject[:60] or "—",
                "from": sender[:50] or "—",
                "date": date[:30] or "—",
                "msg_id": msg_id,
                "size_kb": round(size_bytes / 1024, 1),
                "links": link_count,
                "attachments": has_att,
            })

            match = build_email_diagnostic(sender=sender, subject=subject, date=date)
            result["sender_match_count"] += int(match.sender_matched)
            result["subject_match_count"] += int(match.subject_matched)
            if match.is_job_alert:
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
    import os as _os
    from pathlib import Path

    lines = ["🔍 <b>Gmail Agent — Діагностика</b>\n"]
    lines.append(f"GMAIL_ENABLED: <code>{'true' if settings.GMAIL_ENABLED else 'false'}</code>")
    lines.append(f"GMAIL_USE_MOCK: <code>{'true' if settings.GMAIL_USE_MOCK else 'false'}</code>")
    lines.append(f"GMAIL_MIN_SCORE: <code>{settings.GMAIL_MIN_SCORE}</code>")
    lines.append(f"GMAIL_CHECK_INTERVAL: <code>{settings.GMAIL_CHECK_INTERVAL_MINUTES} хв</code>")
    lines.append(
        "GMAIL_EXPECTED_ACCOUNT: "
        + ("<code>configured</code>" if getattr(settings, "GMAIL_EXPECTED_ACCOUNT", None) else "<code>missing</code>")
    )

    creds_file = settings.GMAIL_CREDENTIALS_FILE
    token_file = settings.GMAIL_TOKEN_FILE
    creds_exists = Path(creds_file).exists()
    token_exists = Path(token_file).exists()
    creds_json_set = bool(_os.getenv("GMAIL_CREDENTIALS_JSON"))
    token_json_set = bool(_os.getenv("GMAIL_TOKEN_JSON"))

    lines.append("\n<b>Railway env vars:</b>")
    lines.append(f"GMAIL_CREDENTIALS_JSON: {'✅ set' if creds_json_set else '❌ missing'}")
    lines.append(f"GMAIL_TOKEN_JSON: {'✅ set' if token_json_set else '❌ missing'}")

    lines.append("\n<b>File fallback:</b>")
    lines.append(
        f"credentials file: {'✅ знайдено' if creds_exists else '❌ відсутній'} "
        f"(<code>{escape_html(creds_file)}</code>)"
    )
    lines.append(
        f"token file: {'✅ знайдено' if token_exists else '❌ відсутній'} "
        f"(<code>{escape_html(token_file)}</code>)"
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

    if not creds_json_set and not creds_exists:
        lines.append(
            "\n❌ <b>Credentials не налаштовано.</b>\n"
            "Railway: встанови <code>GMAIL_CREDENTIALS_JSON</code> (вміст credentials.json)\n"
            "Локально: завантаж credentials.json з Google Cloud Console\n"
            "(APIs &amp; Services → Credentials → OAuth 2.0 → Desktop app → Download JSON)"
        )
        await message.answer("\n".join(lines))
        return

    if not token_json_set and not token_exists:
        lines.append(
            "\n⚠️ <b>Token не знайдено.</b>\n"
            "Railway: встанови <code>GMAIL_TOKEN_JSON</code> (вміст gmail_token.json)\n"
            "Для отримання токену:\n"
            "1. Локально: <code>GMAIL_ENABLED=true</code>, <code>GMAIL_USE_MOCK=false</code>\n"
            "2. Запусти бот — браузер відкриється\n"
            "3. Увійди в Google — збережеться gmail_token.json\n"
            "4. Скопіюй вміст у <code>GMAIL_TOKEN_JSON</code> на Railway"
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
        header_lines = [
            "✅ <b>Gmail підключено!</b>\n",
            f"📬 Листів в Inbox: <b>{len(diag['emails'])}</b>",
            f"📨 Збіг sender domain: <b>{diag['sender_match_count']}</b>",
            f"📝 Збіг subject keyword: <b>{diag['subject_match_count']}</b>",
            f"🎯 Потенційних job alerts: <b>{diag['job_alert_count']}</b>",
        ]
        if diag["job_alert_count"] == 0:
            header_lines.append("💡 Підпишись на email-сповіщення на Freelancehunt/Work.ua/Upwork")
        await message.answer("\n".join(header_lines))

        for i, em in enumerate(diag["emails"], 1):
            att_str = "yes" if em["attachments"] else "no"
            card = (
                f"📧 <b>Email #{i}</b>\n\n"
                f"From: <code>{escape_html(em['from'])}</code>\n"
                f"Subject: {escape_html(em['subject'])}\n"
                f"Date: {escape_html(em['date'])}\n"
                f"Size: {em['size_kb']} KB\n"
                f"Links: {em['links']}\n"
                f"Attachments: {att_str}"
            )
            await message.answer(card)
    else:
        status_labels = {
            "missing_deps": "❌ Відсутні залежності",
            "need_reauth": "⚠️ Потрібна повторна авторизація",
            "invalid": "❌ Токен недійсний",
            "error": "❌ Помилка підключення",
        }
        label = status_labels.get(diag["status"], "❌ Помилка")
        await message.answer(f"{label}:\n\n{escape_html(diag['message'])}")



# ─── /gmail_scan ──────────────────────────────────────────────────────────────

async def _send_gmail_scan_output(message: Message, text: str, block: str) -> bool:
    """Send one diagnostic block without changing an already-computed scan result."""
    try:
        await message.answer(text)
        return True
    except Exception:
        logger.exception("Failed to send Gmail scan %s output", block)
        return False


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
        from gmail_agent.live_status import FreelancehuntLiveStatusChecker
        from gmail_agent.processor import GmailJobProcessor
        from gmail_agent.storage import PostgresGmailRepository

        provider = build_provider(
            use_mock=settings.GMAIL_USE_MOCK,
            credentials_file=settings.GMAIL_CREDENTIALS_FILE,
            token_file=settings.GMAIL_TOKEN_FILE,
            expected_account=getattr(settings, "GMAIL_EXPECTED_ACCOUNT", None),
            lookback_days=getattr(settings, "GMAIL_LOOKBACK_DAYS", 7),
        )
        try:
            repository = PostgresGmailRepository(AsyncSessionLocal)
        except Exception:
            if not settings.GMAIL_USE_MOCK:
                raise
            repository = None
            logger.exception(
                "PostgreSQL Gmail repository unavailable; using mock/local fallback"
            )

        processor = GmailJobProcessor(
            provider=provider,
            bot=message.bot,
            chat_id=settings.TELEGRAM_CHAT_ID,
            min_score=settings.GMAIL_MIN_SCORE,
            repository=repository,
            max_cards_per_scan=10,
            digest_enabled=getattr(settings, "GMAIL_DIGEST_ENABLED", False),
            live_status_checker=FreelancehuntLiveStatusChecker(),
        )

        stats = await processor.run(trigger="manual")
    except Exception as exc:
        logger.exception("Gmail processor failed")
        await _send_gmail_scan_output(
            message,
            f"❌ Помилка gmail scan:\n<code>{escape_html(exc)}</code>",
            "processor-error",
        )
        return

    emails_fetched = max(0, stats.emails_fetched)
    candidates_found = max(0, getattr(stats, "candidates_found", 0))
    ai_analyzed = max(0, getattr(stats, "ai_analyzed", 0))
    relevant = max(0, getattr(stats, "relevant", 0))
    qualified = max(0, getattr(stats, "qualified", 0))
    below_threshold = max(0, stats.below_threshold)
    not_relevant = max(0, stats.not_relevant)
    duplicates = max(0, stats.duplicates_skipped)
    sent = max(0, stats.sent)
    sent_from_queue = max(0, getattr(stats, "sent_from_queue", 0))
    fresh_sent = max(0, sent - sent_from_queue)
    errors = max(0, stats.errors)

    summary = (
        f"✅ <b>Gmail scan завершено</b>\n\n"
        f"📊 <b>Gmail Scan Details</b>\n\n"
        f"📬 Email-повідомлень перевірено: <b>{emails_fetched}</b>\n"
        f"🧩 Job candidates знайдено: <b>{candidates_found}</b>\n"
        f"🧠 Нових AI-аналізів: <b>{ai_analyzed}</b>\n"
        f"✅ Нових релевантних: <b>{relevant}</b>\n"
        f"🎯 Пройшли score ≥ {settings.GMAIL_MIN_SCORE}: <b>{qualified}</b>\n"
        f"⬇️ Нижче порогу: <b>{below_threshold}</b>\n"
        f"🚫 Нерелевантних: <b>{not_relevant}</b>\n"
        f"♻️ Дублікатів: <b>{duplicates}</b>\n"
        f"📤 Відправлено нових: <b>{fresh_sent}</b>\n"
        f"🔁 Відправлено з черги: <b>{sent_from_queue}</b>\n"
        f"📨 Всього відправлено: <b>{sent}</b>\n"
        f"❌ Помилок: <b>{errors}</b>\n"
        f"⏱ Max detection latency: <b>{float(getattr(stats, 'max_detection_latency_seconds', 0.0)):.1f}s</b>\n"
        f"📮 OAuth identity: <b>{escape_html(getattr(stats, 'mailbox_alias', '') or '—')}</b>"
    )

    if sent_from_queue > 0:
        summary += (
            "\n\nЧастина карток могла бути проаналізована в попередньому запуску "
            "та надіслана з постійної черги."
        )

    if stats.emails_fetched == 0:
        summary += "\n\n📭 Inbox порожній або немає нових листів."
    elif stats.sent == 0 and stats.emails_fetched > 0:
        summary += "\n\n💡 Листи знайдено, але жоден не пройшов фільтр."

    if stats.error_details:
        summary += (
            "\n\n<b>Error details:</b>\n<code>"
            + escape_html("\n".join(stats.error_details[:3]))
            + "</code>"
        )

    await _send_gmail_scan_output(message, summary, "summary")

    if stats.rejected_samples:
        rej_lines = [f"❌ <b>Відхилені (нерелевантні) — перші {len(stats.rejected_samples)}:</b>"]
        for sample in stats.rejected_samples:
            rej_lines.append(
                f"\n❌ <b>Ignored</b>\n"
                f"From: <code>{escape_html(sample.get('from'))}</code>\n"
                f"Subject: {escape_html(sample.get('subject'))}\n"
                f"Reason: {escape_html(sample.get('reason'))}"
            )
            rej_lines.append("—" * 20)
        await _send_gmail_scan_output(message, "\n".join(rej_lines), "rejected-samples")

    if stats.below_score_samples:
        low_lines = [f"⚠️ <b>Нижче порогу score — перші {len(stats.below_score_samples)}:</b>"]
        for sample in stats.below_score_samples:
            low_lines.append(
                f"\n⚠️ <b>Below Score Threshold</b>\n"
                f"Subject: {escape_html(sample.get('subject'))}\n"
                f"Score: {sample['score']:.1f}\n"
                f"Reason: {escape_html(sample.get('reason'))}"
            )
            low_lines.append("—" * 20)
        await _send_gmail_scan_output(message, "\n".join(low_lines), "below-score-samples")

    if stats.sent_analyses:
        pass_lines = [f"✅ <b>Відправлено в Telegram — {len(stats.sent_analyses)}:</b>"]
        for analysis in stats.sent_analyses[:5]:
            display_url = safe_http_url(analysis.url) or "—"
            pass_lines.append(
                f"\n✅ <b>Passed</b>\n"
                f"Subject: {escape_html(analysis.title)}\n"
                f"Score: {escape_html(analysis.score_display)}\n"
                f"Budget: {escape_html(analysis.budget or '—')}\n"
                f"URL: {escape_html(display_url)}\n"
                f"Reason: {escape_html(analysis.reason)}"
            )
            pass_lines.append("—" * 20)
        await _send_gmail_scan_output(message, "\n".join(pass_lines), "sent-analyses")

    # Retain short-lived telemetry for /status compatibility. /gmail_history
    # reads its authoritative records from PostgreSQL.
    try:
        import state as _state

        _state.gmail_scan_history.append({
            "timestamp": datetime.utcnow(),
            "finished_at": datetime.utcnow(),
            "trigger": "manual",
            "emails": emails_fetched,
            "emails_found": emails_fetched,
            "candidates": candidates_found,
            "ai_analyzed": ai_analyzed,
            "relevant": relevant,
            "qualified": qualified,
            "duplicates": duplicates,
            "not_relevant": not_relevant,
            "below_threshold": below_threshold,
            "sent": sent,
            "sent_from_queue": sent_from_queue,
            "errors": errors,
            "event_counts": getattr(stats, "event_counts", {}),
            "mailbox_alias": getattr(stats, "mailbox_alias", ""),
            "max_detection_latency_seconds": getattr(
                stats, "max_detection_latency_seconds", None
            ),
        })
        if len(_state.gmail_scan_history) > 20:
            _state.gmail_scan_history = _state.gmail_scan_history[-20:]
    except Exception:
        logger.exception("Failed to save Gmail scan status telemetry")



# ─── /gmail_history ───────────────────────────────────────────────────────────

def _gmail_digest_days(message: Message) -> int | None:
    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    days = int(parts[1])
    return days if 1 <= days <= 30 else None


def _gmail_digest_processor(message: Message):
    from gmail_agent.gmail_provider import build_provider
    from gmail_agent.live_status import FreelancehuntLiveStatusChecker
    from gmail_agent.processor import GmailJobProcessor
    from gmail_agent.storage import PostgresGmailRepository

    provider = build_provider(
        use_mock=settings.GMAIL_USE_MOCK,
        credentials_file=settings.GMAIL_CREDENTIALS_FILE,
        token_file=settings.GMAIL_TOKEN_FILE,
        expected_account=getattr(settings, "GMAIL_EXPECTED_ACCOUNT", None),
        lookback_days=getattr(settings, "GMAIL_LOOKBACK_DAYS", 7),
    )
    repository = PostgresGmailRepository(AsyncSessionLocal)
    return GmailJobProcessor(
        provider=provider,
        bot=message.bot,
        chat_id=settings.TELEGRAM_CHAT_ID,
        min_score=settings.GMAIL_MIN_SCORE,
        repository=repository,
        max_cards_per_scan=10,
        digest_enabled=True,
        live_status_checker=FreelancehuntLiveStatusChecker(),
    )


@admin_router.message(Command("gmail_digest_preview"))
async def cmd_gmail_digest_preview(message: Message) -> None:
    days = _gmail_digest_days(message)
    if days is None:
        await message.answer(
            "❌ Використання: <code>/gmail_digest_preview &lt;days&gt;</code>; "
            "days має бути від <b>1</b> до <b>30</b>."
        )
        return
    if not settings.GMAIL_ENABLED:
        await message.answer("⚠️ Gmail агент вимкнено (<code>GMAIL_ENABLED=false</code>).")
        return

    try:
        processor = _gmail_digest_processor(message)
        preview = await processor.run_digest_preview(days)
    except Exception:
        logger.exception("Gmail digest preview failed")
        await message.answer(
            "❌ Digest preview unavailable: не вдалося підключитися до Gmail/PostgreSQL."
        )
        return

    lines = [
        "🔎 <b>Freelancehunt digest preview</b>",
        f"Days: <b>{days}</b>",
        f"Candidates: <b>{preview.stats.candidates_found}</b>",
        f"Errors: <b>{preview.stats.errors}</b>",
    ]
    for index, item in enumerate(preview.items, 1):
        lines.append(
            f"\n{index}. <b>{escape_html(item.title)}</b>\n"
            f"Score: <b>{float(item.score):.1f}/10</b>\n"
            f"Reason: {escape_html(item.reason)}"
        )
    await message.answer("\n".join(lines))


@admin_router.message(Command("gmail_digest_backfill"))
async def cmd_gmail_digest_backfill(message: Message) -> None:
    days = _gmail_digest_days(message)
    if days is None:
        await message.answer(
            "❌ Використання: <code>/gmail_digest_backfill &lt;days&gt;</code>; "
            "days має бути від <b>1</b> до <b>30</b>."
        )
        return
    if not settings.GMAIL_ENABLED:
        await message.answer("⚠️ Gmail агент вимкнено (<code>GMAIL_ENABLED=false</code>).")
        return

    try:
        processor = _gmail_digest_processor(message)
        stats = await processor.run_digest_backfill(days)
    except Exception:
        logger.exception("Gmail digest backfill failed")
        await message.answer(
            "❌ Digest backfill unavailable: не вдалося підключитися до Gmail/PostgreSQL."
        )
        return

    lines = [
        "✅ <b>Freelancehunt digest backfill завершено</b>",
        f"Emails: <b>{stats.emails_fetched}</b>",
        f"Candidates: <b>{stats.candidates_found}</b>",
        f"AI analyzed: <b>{getattr(stats, 'ai_analyzed', 0)}</b>",
        f"Relevant: <b>{stats.relevant}</b>",
        f"Qualified: <b>{getattr(stats, 'qualified', 0)}</b>",
        f"Duplicates: <b>{stats.duplicates_skipped}</b>",
        f"Not relevant: <b>{stats.not_relevant}</b>",
        f"Below threshold: <b>{stats.below_threshold}</b>",
        f"Sent (cap 10): <b>{stats.sent}</b>",
        f"Sent from queue: <b>{getattr(stats, 'sent_from_queue', 0)}</b>",
        f"Errors: <b>{stats.errors}</b>",
    ]
    if stats.error_details:
        lines.append("<code>" + escape_html("\n".join(stats.error_details[:3])) + "</code>")
    await message.answer("\n".join(lines))


@admin_router.message(Command("gmail_history"))
async def cmd_gmail_history(message: Message) -> None:
    try:
        from gmail_agent.storage import PostgresGmailRepository

        repository = PostgresGmailRepository(AsyncSessionLocal)
        history = await repository.list_scan_runs(limit=20)
    except Exception:
        logger.exception("Failed to read Gmail scan history from PostgreSQL")
        await message.answer(
            "📋 <b>Gmail Scan History</b>\n\n"
            "⚠️ Історія тимчасово недоступна (database unavailable)."
        )
        return

    if not history:
        await message.answer(
            "📋 <b>Gmail Scan History</b>\n\nЗаписів у базі даних ще немає."
        )
        return

    lines = [f"📋 <b>Gmail Scan History</b> (останні {len(history)})\n"]
    for i, entry in enumerate(history, 1):
        ts = entry.started_at.strftime("%d.%m %H:%M")
        lines.append(
            f"{i}. <b>{ts}</b> — {escape_html(entry.trigger)}; "
            f"emails: {entry.emails_inspected}, "
            f"candidates: {entry.candidates_found}, "
            f"analyzed: {entry.ai_analyzed}, "
            f"relevant: {entry.relevant}, "
            f"qualified: {entry.qualified}, "
            f"sent: {entry.sent}, "
            f"queue: {entry.sent_from_queue}, "
            f"duplicates: {entry.duplicates}, "
            f"errors: {entry.errors}"
            f", quality valid/repaired/manual/failed: "
            f"{getattr(entry, 'quality_valid', 0)}/"
            f"{getattr(entry, 'quality_repaired', 0)}/"
            f"{getattr(entry, 'quality_manual_review', 0)}/"
            f"{getattr(entry, 'quality_failed', 0)}, "
            f"repair calls: {getattr(entry, 'repair_calls', 0)}, "
            f"proposal versions: {getattr(entry, 'proposal_versions_sent', 0)}"
        )
    await message.answer("\n".join(lines))


# ─── /gmail_debug ─────────────────────────────────────────────────────────────

def _format_gmail_debug_results(results: list) -> list[str]:
    """Format header-only diagnostics; result objects cannot contain email bodies or IDs."""
    from bot.html_utils import escape_html

    inspected = len(results)
    sender_matches = sum(item.sender_matched for item in results)
    subject_matches = sum(item.subject_matched for item in results)
    job_alerts = sum(item.is_job_alert for item in results)
    messages = [
        "📊 <b>Gmail Debug — header-only</b>\n"
        f"Inbox inspected: <b>{inspected}</b>\n"
        f"Matched sender domain: <b>{sender_matches}</b>\n"
        f"Matched subject keyword: <b>{subject_matches}</b>\n"
        f"Returned job alerts: <b>{job_alerts}</b>"
    ]

    for index, item in enumerate(results, 1):
        display_name = escape_html((item.sender_display_name or "—")[:80])
        sender_email = escape_html((item.sender_email or "—")[:120])
        subject = escape_html((item.subject or "—").replace("\n", " ")[:200])
        date = escape_html((item.date or "—")[:80])
        platform = escape_html(item.platform or "Unknown")
        messages.append(
            f"📧 <b>Email #{index}</b>\n"
            f"Sender name: {display_name}\n"
            f"Sender email: <code>{sender_email}</code>\n"
            f"Subject: {subject}\n"
            f"Date: {date}\n"
            f"Platform: <b>{platform}</b>\n"
            f"Sender matched: <b>{'yes' if item.sender_matched else 'no'}</b>\n"
            f"Subject matched: <b>{'yes' if item.subject_matched else 'no'}</b>\n"
            f"Final job-alert match: <b>{'yes' if item.is_job_alert else 'no'}</b>"
        )
    return messages


@admin_router.message(Command("gmail_debug"))
async def cmd_gmail_debug(message: Message) -> None:
    if not settings.GMAIL_ENABLED:
        await message.answer(
            "⚠️ Gmail агент вимкнено.\n"
            "Встанови <code>GMAIL_ENABLED=true</code>."
        )
        return

    mode = "MOCK" if settings.GMAIL_USE_MOCK else "REAL Gmail"
    await message.answer(
        f"🔍 <b>Gmail Debug (dry-run)</b>\n"
        f"Режим: <b>{mode}</b>\n"
        "⚠️ Body не читається; AI, dedup і job cards не запускаються"
    )

    try:
        from gmail_agent.gmail_provider import build_provider

        mock_emails = None
        if settings.GMAIL_USE_MOCK:
            from gmail_agent.tests.mock_emails import ALL_MOCK_EMAILS
            mock_emails = ALL_MOCK_EMAILS

        provider = build_provider(
            use_mock=settings.GMAIL_USE_MOCK,
            mock_emails=mock_emails,
            credentials_file=settings.GMAIL_CREDENTIALS_FILE,
            token_file=settings.GMAIL_TOKEN_FILE,
            expected_account=getattr(settings, "GMAIL_EXPECTED_ACCOUNT", None),
            lookback_days=getattr(settings, "GMAIL_LOOKBACK_DAYS", 7),
        )

        results = await provider.get_recent_email_diagnostics(max_results=10)

        if not results:
            await message.answer("📭 Листів не знайдено.")
            return

        for output in _format_gmail_debug_results(results):
            await message.answer(output)

    except Exception as exc:
        error_type = type(exc).__name__
        logger.warning("gmail_debug failed (%s)", error_type)
        if "invalid_grant" in str(exc):
            detail = "Gmail OAuth token потребує повторної авторизації."
        else:
            detail = f"{error_type}. Перевір Gmail configuration і server logs."
        await message.answer(f"❌ Помилка gmail_debug:\n<code>{detail}</code>")
