"""Format and send complete, HTML-safe Telegram action cards."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from bot.html_utils import escape_html, safe_http_url

from .email_analyzer import JobAnalysis
from .email_classifier import EmailType
from .freelancehunt_private_message import FreelancehuntPrivateMessageNotification
from .live_status import LiveStatus
from .quality_gate import (
    PROPOSAL_READY_QUALITY_STATUSES,
    QualityStatus,
    apply_validation,
    finite_score,
    is_proposal_ready,
    quality_errors,
    validate_analysis,
)
from .sales_closer import SalesProcessResult, opportunity_id_for_analysis
from .sales_storage import ConversationTurn, HumanInformationRequest, SalesOpportunity

logger = logging.getLogger(__name__)

TELEGRAM_TEXT_LIMIT = 4096
_SAFE_PART_LIMIT = 3900


def _short(value: Any, limit: int = 360) -> str:
    """Bound model-controlled summary fields before HTML escaping."""

    text = str(value or "—")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _append_html_section(parts: list[str], section: str) -> None:
    """Pack complete HTML sections without slicing tags or entities."""

    if not section:
        return
    if not parts:
        parts.append(section)
    elif len(parts[-1]) + len(section) + 2 <= _SAFE_PART_LIMIT:
        parts[-1] += "\n\n" + section
    else:
        parts.append(section)


def _pack_html_lines(lines: list[str]) -> list[str]:
    parts: list[str] = []
    current = ""
    for line in lines:
        candidate = line if not current else current + "\n" + line
        if len(candidate) <= _SAFE_PART_LIMIT:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = line
    if current:
        parts.append(current)
    return parts


def _urgency_emoji(urgency: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(urgency, "⚪")


def _score_emoji(score: Any) -> str:
    value = finite_score(score)
    if value is None:
        return "⚪"
    if value >= 8:
        return "🔥"
    if value >= 6:
        return "✅"
    if value >= 4:
        return "⚠️"
    return "❌"


def _received(value: Any) -> str:
    if value is None:
        return "—"
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(value)


def _latency(value: float | None) -> str:
    if value is None:
        return "—"
    try:
        return f"{max(0.0, float(value)):.1f} s"
    except (TypeError, ValueError):
        return "—"


def _split_text(value: str, max_escaped: int = 3000) -> list[str]:
    """Split source text before escaping so no HTML entity is cut."""

    remaining = value or ""
    if not remaining:
        return []
    chunks: list[str] = []
    while remaining:
        low, high = 1, len(remaining)
        best = 1
        while low <= high:
            mid = (low + high) // 2
            if len(escape_html(remaining[:mid])) <= max_escaped:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        cut = best
        if cut < len(remaining):
            newline = remaining.rfind("\n", 0, cut)
            space = remaining.rfind(" ", 0, cut)
            # Prefer semantic line boundaries even when a later word-space is
            # available, so copied requirements are not split mid-sentence.
            boundary = newline if newline >= max(1, cut // 2) else space
            if boundary >= max(1, cut // 2):
                cut = boundary + 1
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    return [chunk for chunk in chunks if chunk]


def _project_summary_lines(analysis: JobAnalysis) -> list[str]:
    safe_url = safe_http_url(analysis.url)
    bid_ready = is_proposal_ready(analysis)
    decision = (
        "GO"
        if bid_ready and finite_score(analysis.score) is not None and finite_score(analysis.score) >= 6
        else "REVIEW"
    )
    lines = [
        (
            f"{_score_emoji(analysis.score)} <b>{decision} — AI SALES CLOSER BID PACKAGE</b> "
            f"{_urgency_emoji(analysis.urgency)}"
            if bid_ready
            else f"{_score_emoji(analysis.score)} <b>New Job Match</b> {_urgency_emoji(analysis.urgency)}"
        ),
        *(
            [f"<b>Opportunity:</b> <code>{escape_html(opportunity_id_for_analysis(analysis))}</code>"]
            if bid_ready
            else []
        ),
        *( [f"<b>Decision:</b> {decision}"] if bid_ready else [] ),
        f"<b>Event:</b> {escape_html(_short(analysis.event_type))}",
        f"<b>Отримано:</b> {escape_html(_received(analysis.received_at))}",
        *(
            [f"<b>Опубліковано:</b> {escape_html(_received(analysis.source_publication_at))}"]
            if analysis.source_publication_at is not None
            else []
        ),
        *(
            [f"<b>Feed fetched:</b> {escape_html(_received(analysis.feed_fetched_at))}"]
            if analysis.feed_fetched_at is not None
            else []
        ),
        *(
            [f"<b>First seen:</b> {escape_html(_received(analysis.first_seen_at))}"]
            if analysis.first_seen_at is not None
            else []
        ),
        *(
            [
                "<b>Publication → Telegram:</b> "
                f"{escape_html(_latency(analysis.publication_to_telegram_latency_seconds))}"
            ]
            if analysis.publication_to_telegram_latency_seconds is not None
            else []
        ),
        *(
            [
                "<b>Live status:</b> ACTIVE — bid available",
                f"<b>Checked:</b> {escape_html(_received(analysis.live_status_checked_at))}",
            ]
            if analysis.live_status == LiveStatus.ACTIVE_BIDDABLE.value
            and analysis.biddable is True
            else []
        ),
        "",
        f"<b>Платформа:</b> {escape_html(_short(analysis.platform))}",
        f"<b>Назва:</b> {escape_html(_short(analysis.title))}",
        *(
            [
                "<b>Analysis quality:</b> "
                + (
                    "VALID"
                    if analysis.analysis_quality_status == QualityStatus.VALID.value
                    else "REPAIRED"
                )
            ]
            if analysis.analysis_quality_status in PROPOSAL_READY_QUALITY_STATUSES
            else []
        ),
        f"<b>Score:</b> {escape_html(analysis.score_display)}",
        f"<b>Бюджет:</b> {escape_html(_short(analysis.budget))}",
        *(
            [f"<b>Валюта:</b> {escape_html(_short(analysis.budget_currency))}"]
            if analysis.budget_currency
            else []
        ),
        f"<b>Мова клієнта:</b> {escape_html(_short(analysis.language))}",
        f"<b>Повнота ТЗ:</b> {escape_html(_short(analysis.description_completeness))}",
        f"<b>Строк:</b> {escape_html(_short(analysis.deadline))}",
        f"<b>Категорія:</b> {escape_html(_short(analysis.category))}",
        *(
            [f"<b>Теги:</b> {escape_html(_short(analysis.tags))}"]
            if analysis.tags
            else []
        ),
        f"<b>Competition/public bid signal:</b> {escape_html(analysis.bid_count if analysis.bid_count is not None else '—')}",
        f"<b>Клієнт:</b> {escape_html(_short(analysis.client_name))}",
        "",
        f"<b>Service lane:</b> {escape_html(_short(analysis.service_lane))}",
        f"<b>Можемо виконати:</b> {escape_html(_short(analysis.executable or 'maybe'))}",
        f"<b>Fit:</b> {escape_html(analysis.fit_score_display)}",
        f"<b>Win signal:</b> {escape_html(_short(analysis.win_probability_signal))}",
        f"<b>Scope clarity:</b> {escape_html(_short(analysis.scope_clarity))}",
        f"<b>Трудомісткість:</b> {escape_html(_short(analysis.estimated_effort))}",
        f"<b>Ризик розробки:</b> {escape_html(_short(analysis.delivery_risk))}",
        f"<b>Ризик клієнта/оплати:</b> {escape_html(_short(analysis.client_payment_risk))}",
        f"<b>Режим:</b> {escape_html(_short(analysis.project_mode))} — {escape_html(_short(analysis.project_mode_reason))}",
        f"<b>Рекомендована ціна:</b> {escape_html(_short(analysis.recommended_price))}",
        f"<b>Реалістичний строк:</b> {escape_html(_short(analysis.realistic_timeline))}",
        *(
            [f"<b>Evidence ID:</b> {escape_html(_short(analysis.evidence_case_id))}"]
            if analysis.evidence_case_id
            else []
        ),
        f"<b>Релевантний кейс:</b> {escape_html(_short(analysis.selected_evidence))}",
    ]
    if analysis.reason:
        lines += [f"<b>Оцінка:</b> {escape_html(_short(analysis.reason))}"]
    if analysis.why_relevant:
        lines += [f"<b>Чому підходить:</b> {escape_html(_short(analysis.why_relevant))}"]
    public_evidence = analysis.evidence or analysis.client_context
    if public_evidence:
        lines += [f"<b>Публічні докази:</b> {escape_html(_short(public_evidence))}"]
    if analysis.red_flags:
        bounded_flags = [_short(flag, 160) for flag in analysis.red_flags[:8]]
        if len(analysis.red_flags) > len(bounded_flags):
            bounded_flags.append(f"+{len(analysis.red_flags) - len(bounded_flags)} more")
        flags = ", ".join(escape_html(flag) for flag in bounded_flags)
        lines += [f"<b>Ризики:</b> {flags}"]
    if safe_url:
        lines += ["", f'🔗 <a href="{escape_html(safe_url)}">Відкрити замовлення</a>']
    else:
        lines += ["", "🔗 Посилання відсутнє"]
    return lines


def _private_summary_lines(analysis: JobAnalysis) -> list[str]:
    safe_url = safe_http_url(analysis.url)
    lines = [
        "🔴 <b>HIGH PRIORITY — Private message</b>",
        f"<b>Event:</b> {escape_html(_short(analysis.event_type))}",
        f"<b>Отримано:</b> {escape_html(_received(analysis.received_at))}",
        f"<b>Відправник:</b> {escape_html(_short(analysis.client_name))}",
        f"<b>Контекст:</b> {escape_html(_short(analysis.title))}",
        f"<b>Мова:</b> {escape_html(_short(analysis.language))}",
    ]
    if analysis.needs_context:
        lines.append("<b>NEEDS_CONTEXT</b>")
    if safe_url:
        lines.append(f'🔗 <a href="{escape_html(safe_url)}">Відкрити гілку Freelancehunt</a>')
    return lines


def _other_summary_lines(analysis: JobAnalysis) -> list[str]:
    event_type = analysis.event_type
    is_security = event_type == EmailType.ACCOUNT_OR_SECURITY_EVENT.value
    icon = "🛡" if is_security else "ℹ️"
    lines = [
        f"{icon} <b>{escape_html(_short(event_type))}</b>",
        f"<b>Отримано:</b> {escape_html(_received(analysis.received_at))}",
        f"<b>Тема:</b> {escape_html(_short(analysis.title))}",
        f"<b>Мова:</b> {escape_html(_short(analysis.language))}",
    ]
    if is_security:
        lines.append(
            "<b>Безпека:</b> чутливі дані та посилання відредаговано. "
            "Відкрийте Gmail або Freelancehunt напряму."
        )
    else:
        safe_url = safe_http_url(analysis.url)
        if safe_url:
            lines.append(f'🔗 <a href="{escape_html(safe_url)}">Відкрити подію</a>')
    return lines


def format_job_card_parts(analysis: JobAnalysis) -> list[str]:
    """Return a complete action card as one or more valid Telegram messages."""

    if (
        analysis.event_type
        in {
            EmailType.PROJECT_SINGLE.value,
            EmailType.PROJECT_DIGEST.value,
            EmailType.PROJECT_FEED.value,
        }
        and analysis.live_status
        and analysis.live_status != LiveStatus.ACTIVE_BIDDABLE.value
    ):
        return [format_live_status_card(analysis)]

    if (
        analysis.event_type
        in {
            EmailType.PROJECT_SINGLE.value,
            EmailType.PROJECT_DIGEST.value,
            EmailType.PROJECT_FEED.value,
        }
        and analysis.live_status == LiveStatus.ACTIVE_BIDDABLE.value
        and analysis.biddable is True
        and analysis.analysis_version
        and not analysis.analysis_quality_status
    ):
        apply_validation(analysis, validate_analysis(analysis))

    if (
        analysis.event_type
        in {
            EmailType.PROJECT_SINGLE.value,
            EmailType.PROJECT_DIGEST.value,
            EmailType.PROJECT_FEED.value,
        }
        and analysis.live_status == LiveStatus.ACTIVE_BIDDABLE.value
        and analysis.biddable is True
        and not is_proposal_ready(analysis)
    ):
        return format_quality_review_card_parts(analysis)

    if analysis.event_type == EmailType.CLIENT_PRIVATE_MESSAGE.value:
        summary = _private_summary_lines(analysis)
        body_label = "Повний безпечний текст повідомлення"
        draft_label = "Готова відповідь"
    elif analysis.event_type in {
        EmailType.PROJECT_SINGLE.value,
        EmailType.PROJECT_DIGEST.value,
        EmailType.PROJECT_FEED.value,
    }:
        summary = _project_summary_lines(analysis)
        body_label = "Повне доступне ТЗ"
        draft_label = "Готовий відгук"
    else:
        summary = _other_summary_lines(analysis)
        body_label = "Безпечний текст події"
        draft_label = "Чернетка відповіді"

    parts = _pack_html_lines(summary)

    for chunk in _split_text(analysis.full_description):
        _append_html_section(
            parts,
            f"<b>{body_label}:</b>\n{escape_html(chunk)}",
        )

    if analysis.proposal_draft:
        for chunk in _split_text(analysis.proposal_draft):
            _append_html_section(
                parts,
                f"<b>{draft_label}:</b>\n{escape_html(chunk)}",
            )
    elif analysis.event_type == EmailType.CLIENT_PRIVATE_MESSAGE.value:
        _append_html_section(parts, "<b>Готова відповідь:</b> NEEDS_CONTEXT")

    if is_proposal_ready(analysis) and analysis.event_type in {
        EmailType.PROJECT_SINGLE.value,
        EmailType.PROJECT_DIGEST.value,
        EmailType.PROJECT_FEED.value,
    }:
        opportunity_id = opportunity_id_for_analysis(analysis)
        proposal_version = str(analysis.proposal_version or "").strip() or "UNAVAILABLE"
        proposal_hash = str(analysis.proposal_content_sha256 or "").strip()
        hash_prefix = proposal_hash[:12] + "…" if proposal_hash else "UNAVAILABLE"
        commands = (
            f"<b>Validated proposal retrieval:</b> <code>/reply_job {escape_html(analysis.email_id)}</code>\n"
            f"<b>Exact package:</b> {escape_html(proposal_version)} · SHA-256 "
            f"<code>{escape_html(hash_prefix)}</code>\n"
            "<b>Наступна дія власниці (одна):</b> перевірити й вручну подати точний "
            "відгук у Freelancehunt, потім зафіксувати фактичні умови:\n"
            f"<code>/mark_bid_sent {escape_html(opportunity_id)} "
            f"{escape_html(proposal_version)} | &lt;price&gt; | &lt;timeline&gt; | "
            "OWNER_CONFIRMS</code>\n"
            "The command only records the adult owner's manual platform action; it never submits a bid."
        )
    else:
        next_action = analysis.next_action or (
            "Відкрити подію на Freelancehunt і виконати фінальну дію особисто."
        )
        commands = (
            f"<b>Наступна дія власниці:</b> {escape_html(next_action)}\n\n"
            f"<code>/reply_job {escape_html(analysis.email_id)}</code>   "
            f"<code>/skip_job {escape_html(analysis.email_id)}</code>"
        )
    _append_html_section(parts, commands)

    if getattr(analysis, "sales_tracking_unavailable", False):
        _append_html_section(
            parts,
            "⚠️ <b>SALES TRACKING TEMPORARILY UNAVAILABLE:</b> the Stage 4 card remains valid, "
            "but 5A opportunity persistence must retry before confirmation.",
        )

    if len(parts) > 1:
        total = len(parts)
        parts = [f"<b>Card {index}/{total}</b>\n{part}" for index, part in enumerate(parts, 1)]
    return parts


def format_job_card(analysis: JobAnalysis) -> str:
    """Backward-compatible single-message formatter used by existing callers."""

    return format_job_card_parts(analysis)[0]


def format_live_status_card(analysis: JobAnalysis) -> str:
    """Format a non-proposal diagnostic card for a non-biddable project."""

    unknown = analysis.live_status == LiveStatus.LIVE_STATUS_UNKNOWN.value
    heading = "LIVE STATUS NOT VERIFIED" if unknown else "Проект недоступен для ставки"
    safe_url = safe_http_url(analysis.url)
    lines = [
        f"⚠️ <b>{heading}</b>",
        f"<b>Назва:</b> {escape_html(_short(analysis.title))}",
        f"<b>Live status:</b> {escape_html(_short(analysis.live_status or LiveStatus.LIVE_STATUS_UNKNOWN.value))}",
        "<b>Bid available:</b> no",
        f"<b>Reason:</b> {escape_html(_short(analysis.live_status_evidence or analysis.live_status_last_error))}",
        f"<b>Checked:</b> {escape_html(_received(analysis.live_status_checked_at))}",
    ]
    if safe_url:
        lines.append(f'🔗 <a href="{escape_html(safe_url)}">Відкрити проєкт</a>')
    action = (
        "Дочекатися автоматичної повторної перевірки."
        if unknown
        else "Нічого не надсилати."
    )
    lines.append(f"<b>Наступна дія власниці:</b> {action}")
    return "\n".join(lines)


def format_quality_review_card_parts(analysis: JobAnalysis) -> list[str]:
    """Render full safe source context as bounded multipart manual review."""

    errors = quality_errors(analysis) or ["quality_state_not_proposal_ready"]
    safe_url = safe_http_url(analysis.url)
    lines = [
        "🟡 <b>QUALITY MANUAL REVIEW</b>",
        "<b>Проєкт активний:</b> yes",
        "<b>Bid-ready:</b> no",
        f"<b>Назва:</b> {escape_html(_short(analysis.title))}",
        f"<b>Повнота ТЗ:</b> {escape_html(_short(analysis.description_completeness))}",
        f"<b>Бюджет:</b> {escape_html(_short(analysis.budget))}",
        f"<b>Категорія:</b> {escape_html(_short(analysis.category))}",
        f"<b>Live status:</b> {escape_html(_short(analysis.live_status))}",
        f"<b>Live checked:</b> {escape_html(_received(analysis.live_status_checked_at))}",
        f"<b>Score:</b> {escape_html(analysis.score_display)}",
        f"<b>Fit:</b> {escape_html(analysis.fit_score_display)}",
        "<b>Quality errors:</b>",
    ]
    lines.extend(f"• <code>{escape_html(_short(error, 180))}</code>" for error in errors)
    if analysis.quality_clarification_question:
        lines.append(
            "<b>One clarification:</b> "
            + escape_html(_short(analysis.quality_clarification_question, 500))
        )
    if safe_url:
        lines.append(f'🔗 <a href="{escape_html(safe_url)}">Відкрити проєкт</a>')
    lines += [
        "<b>Usable proposal:</b> absent",
        "<b>Наступна дія власниці:</b> Перевірити помилки або виконати "
        f"<code>/quality_recheck {escape_html(analysis.email_id)}</code>; ставку не надсилати.",
    ]
    parts = _pack_html_lines(lines)
    for chunk in _split_text(analysis.full_description):
        _append_html_section(parts, f"<b>Повне безпечне ТЗ:</b>\n{escape_html(chunk)}")
    if len(parts) > 1:
        total = len(parts)
        parts = [
            f"<b>Manual review {index}/{total}</b>\n{part}"
            for index, part in enumerate(parts, 1)
        ]
    if any(len(part) > TELEGRAM_TEXT_LIMIT for part in parts):
        raise ValueError("Telegram quality-review card part exceeds 4096 characters")
    return parts


def format_quality_review_card(analysis: JobAnalysis) -> str:
    """Backward-compatible first part for callers expecting one string."""

    return format_quality_review_card_parts(analysis)[0]


async def send_live_status_card(bot: Any, chat_id: int, analysis: JobAnalysis) -> bool:
    """Send at most the caller-controlled diagnostic card, never a proposal."""

    try:
        text = format_live_status_card(analysis)
        if len(text) > TELEGRAM_TEXT_LIMIT:
            raise ValueError("Telegram live-status card exceeds 4096 characters")
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send live-status card: key=%s", analysis.email_id)
        return False


async def send_job_card(bot: Any, chat_id: int, analysis: JobAnalysis) -> bool:
    try:
        parts = format_job_card_parts(analysis)
        if any(len(part) > TELEGRAM_TEXT_LIMIT for part in parts):
            raise ValueError("Telegram card part exceeds 4096 characters")
        for part in parts:
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                disable_web_page_preview=True,
            )
        logger.info(
            "Sent Telegram event card: event=%s key=%s parts=%d score=%s",
            analysis.event_type,
            analysis.email_id,
            len(parts),
            analysis.score_display,
        )
        return True
    except Exception:
        logger.exception("Failed to send job card: email_id=%s", analysis.email_id)
        return False


def format_sales_response_card_parts(result: SalesProcessResult) -> list[str]:
    """Render the dedicated private-message card without exposing model JSON."""

    opportunity = result.opportunity
    incoming = result.incoming_turn
    reply = result.reply_turn
    urgent = incoming.intent in {
        "PRICE_OBJECTION",
        "TIMELINE_OBJECTION",
        "CALL_REQUEST",
        "CLIENT_READY_TO_SELECT",
        "SELECTED_OR_CONTRACT_STEP",
    }
    link = safe_http_url(opportunity.thread_url or opportunity.project_url)
    lines = [
        "🔴 <b>HIGH PRIORITY — CLIENT RESPONSE</b>",
        *( ["🚨 <b>URGENT commercial/selection event</b>"] if urgent else [] ),
        f"<b>Opportunity:</b> <code>{escape_html(opportunity.id)}</code>",
        f"<b>Project:</b> {escape_html(_short(opportunity.title, 500))}",
        f"<b>State:</b> {escape_html(opportunity.state)}",
        f"<b>Resolved by:</b> {escape_html(result.resolution_basis)}",
        f"<b>Parse confidence:</b> {escape_html(incoming.parse_confidence or '—')}",
        f"<b>Wrapper language:</b> {escape_html(incoming.wrapper_language or '—')}",
        f"<b>Client language:</b> {escape_html(incoming.language)}",
        f"<b>Intent:</b> {escape_html(incoming.intent)}",
        f"<b>Простое резюме:</b> {escape_html(_short(incoming.russian_summary, 700))}",
        f"<b>Что клиент хочет:</b> {escape_html(_short(incoming.actual_ask or incoming.content or result.safe_excerpt, 700))}",
        f"<b>Previous promises:</b> proposal {escape_html(opportunity.proposal_version or '—')}; "
        f"price {escape_html(_short(opportunity.actual_submitted_price))}; "
        f"timeline {escape_html(_short(opportunity.actual_submitted_timeline))}",
        f"<b>Negotiation recommendation:</b> {escape_html(_short(incoming.negotiation_strategy, 700))}",
        f"<b>Risks:</b> {escape_html(_short(incoming.risks or opportunity.risks, 700))}",
        f"<b>Missing facts:</b> {escape_html(_short(incoming.missing_facts))}",
        f"<b>Detection latency:</b> {escape_html(_latency(incoming.response_latency_seconds))}",
        f"<b>Acknowledge:</b> <code>/ack_lead {escape_html(incoming.id)}</code>",
        (
            "<b>SLA ≤2 min:</b> MET"
            if incoming.response_latency_seconds is None
            or incoming.response_latency_seconds <= 120
            else "🚨 <b>SLA ≤2 min:</b> MISSED"
        ),
    ]
    if link:
        lines.append(f'🔗 <a href="{escape_html(link)}">Open safe Freelancehunt thread</a>')
    parts = _pack_html_lines(lines)
    if incoming.content:
        for chunk in _split_text(incoming.content):
            _append_html_section(parts, f"<b>Client message:</b>\n{escape_html(chunk)}")
    elif result.safe_excerpt:
        for chunk in _split_text(result.safe_excerpt):
            _append_html_section(
                parts,
                f"<b>Sanitized notification excerpt:</b>\n{escape_html(chunk)}",
            )
    if reply is not None:
        _append_html_section(
            parts,
            f"<b>Exact reply package:</b> {escape_html(reply.reply_version)} · SHA-256 "
            f"<code>{escape_html(reply.content_sha256[:12])}…</code>",
        )
        for chunk in _split_text(reply.content):
            _append_html_section(
                parts,
                f"<b>Copy-ready answer · {escape_html(reply.reply_version)}:</b>\n{escape_html(chunk)}",
            )
    else:
        status = (
            "NOT_REQUIRED_EXPLICIT_REJECTION"
            if opportunity.state == "LOST" and incoming.intent == "REJECTION"
            else "NEEDS_CONTEXT"
            if result.missing_context
            else "NEEDS_HUMAN_INPUT"
        )
        _append_html_section(parts, f"<b>Copy-ready answer:</b> {status}")
    _append_html_section(
        parts,
        f"<b>Next action (one):</b> {escape_html(result.next_action)}",
    )
    _append_html_section(
        parts,
        "⚠️ This bot only prepares and records copy-ready work; it performs no Freelancehunt action.",
    )
    if len(parts) > 1:
        total = len(parts)
        parts = [
            f"<b>Sales card {index}/{total}</b>\n{part}"
            for index, part in enumerate(parts, 1)
        ]
    if any(len(part) > TELEGRAM_TEXT_LIMIT for part in parts):
        raise ValueError("Telegram sales card part exceeds 4096 characters")
    return parts


async def send_sales_response_card(
    bot: Any, chat_id: int, result: SalesProcessResult
) -> bool:
    try:
        for part in format_sales_response_card_parts(result):
            await bot.send_message(
                chat_id=chat_id,
                text=part,
                disable_web_page_preview=True,
            )
        return True
    except Exception:
        logger.exception(
            "Failed to send sales card: opportunity=%s turn=%s",
            result.opportunity.id,
            result.incoming_turn.id,
        )
        return False


def format_sales_escalation_card(turn: ConversationTurn) -> str:
    return (
        "🚨 <b>UNACKNOWLEDGED CLIENT RESPONSE — 5 MINUTES</b>\n"
        f"Opportunity: <code>{escape_html(turn.opportunity_id)}</code>\n"
        f"Incoming turn: <code>{escape_html(turn.id)}</code>\n"
        f"Intent: <b>{escape_html(turn.intent)}</b>\n"
        f"Summary: {escape_html(_short(turn.russian_summary or turn.actual_ask, 700))}\n"
        f"Acknowledge now: <code>/ack_lead {escape_html(turn.id)}</code>"
    )


async def send_sales_escalation_card(
    bot: Any, chat_id: int, turn: ConversationTurn
) -> bool:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=format_sales_escalation_card(turn),
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send sales escalation: turn=%s", turn.id)
        return False


def format_sales_fallback_card(
    *, email_id: str, subject: str, safe_excerpt: str, thread_url: str = ""
) -> str:
    lines = [
        "🔴 <b>CLIENT RESPONSE — SALES TRACKING UNAVAILABLE</b>",
        f"Gmail message: <code>{escape_html(email_id)}</code>",
        f"Subject: {escape_html(_short(subject, 500))}",
        f"Sanitized excerpt: {escape_html(_short(safe_excerpt, 900))}",
        "<b>State:</b> durable retry pending; no platform action was performed.",
        "<b>Next action (one):</b> Open the exact Freelancehunt thread and review manually.",
    ]
    link = safe_http_url(thread_url)
    if link and "freelancehunt." in link.casefold():
        lines.insert(4, f'🔗 <a href="{escape_html(link)}">Open Freelancehunt thread</a>')
    return "\n".join(lines)


async def send_sales_fallback_card(
    bot: Any,
    chat_id: int,
    *,
    email_id: str,
    subject: str,
    safe_excerpt: str,
    thread_url: str = "",
) -> bool:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=format_sales_fallback_card(
                email_id=email_id,
                subject=subject,
                safe_excerpt=safe_excerpt,
                thread_url=thread_url,
            ),
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send sales fallback: email_id=%s", email_id)
        return False


def format_platform_support_card(
    notification: FreelancehuntPrivateMessageNotification,
) -> str:
    """Render a non-sales card for platform support/onboarding notifications."""

    lines = [
        "ℹ️ <b>FREELANCEHUNT PLATFORM MESSAGE</b>",
        f"<b>Sender:</b> {escape_html(_short(notification.sender_display_name, 300))}",
        f"<b>Subject:</b> {escape_html(_short(notification.conversation_subject, 500))}",
        f"<b>Wrapper language:</b> {escape_html(notification.wrapper_language or '—')}",
        f"<b>Message language:</b> {escape_html(notification.client_message_language or '—')}",
        f"<b>Message:</b> {escape_html(_short(notification.actual_message_text or notification.safe_excerpt, 900))}",
        "<b>Sales pipeline:</b> not created or changed.",
        "<b>Next action (one):</b> Review this platform message manually if it requires account-owner attention.",
    ]
    link = safe_http_url(notification.safe_thread_url)
    if link:
        lines.insert(6, f'🔗 <a href="{escape_html(link)}">Open safe Freelancehunt thread</a>')
    return "\n".join(lines)


async def send_platform_support_card(
    bot: Any,
    chat_id: int,
    notification: FreelancehuntPrivateMessageNotification,
) -> bool:
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=format_platform_support_card(notification),
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logger.exception("Failed to send Freelancehunt platform support card")
        return False


def format_pipeline_counts(counts: dict[str, int]) -> str:
    labels = (
        ("PROPOSAL_READY", "proposal ready"),
        ("BID_SUBMITTED", "bid submitted"),
        ("CLIENT_REPLIED", "client replied"),
        ("NEEDS_CONTEXT", "needs context"),
        ("NEEDS_HUMAN_INPUT", "needs human input"),
        ("NEGOTIATING", "negotiating"),
        ("WAITING_CLIENT", "waiting client"),
        ("SELECTION_REVIEW", "selection review"),
        ("CONTRACT_REVIEW", "contract review"),
        ("SELECTED", "selected"),
        ("LOST", "lost"),
    )
    lines = ["📊 <b>Sales pipeline · Stage 5A</b>"]
    lines.extend(
        f"<b>{escape_html(label)}:</b> {int(counts.get(state, 0) or 0)}"
        for state, label in labels
    )
    lines.append("<i>Follow-up scheduler: disabled in Release 5A.</i>")
    return "\n".join(lines)


def format_lead_timeline(
    opportunity: SalesOpportunity,
    transitions: list[Any],
    turns: list[Any],
    requests: list[HumanInformationRequest],
) -> list[str]:
    lines = [
        "🧭 <b>Sales lead timeline</b>",
        f"<b>Opportunity:</b> <code>{escape_html(opportunity.id)}</code>",
        f"<b>Project:</b> {escape_html(_short(opportunity.title, 600))}",
        f"<b>Current state:</b> {escape_html(opportunity.state)}",
        f"<b>Actual terms:</b> {escape_html(_short(opportunity.actual_submitted_price))} · "
        f"{escape_html(_short(opportunity.actual_submitted_timeline))}",
    ]
    for transition in transitions:
        lines.append(
            f"• {escape_html(_received(transition.timestamp))} · "
            f"{escape_html(transition.previous_state or 'START')} → "
            f"<b>{escape_html(transition.new_state)}</b> · "
            f"{escape_html(transition.actor)} · {escape_html(_short(transition.reason, 260))}"
        )
    for turn in turns:
        if turn.direction == "OUTGOING_REJECTED":
            continue
        lines.append(
            f"• {escape_html(_received(turn.created_at))} · {escape_html(turn.direction)} "
            f"{escape_html(turn.reply_version or turn.intent or '')} · "
            f"{escape_html(_short(turn.content, 240))}"
        )
    for request in requests:
        lines.append(
            f"• human fact {escape_html(request.status)} · "
            f"{escape_html(_short(request.question, 260))}"
        )
    action = {
        "PROPOSAL_READY": "Adult owner manually submits the bid and confirms actual terms.",
        "NEEDS_CONTEXT": "Open and sync the exact Freelancehunt thread.",
        "NEEDS_HUMAN_INPUT": "Answer the one open human-information request.",
        "NEGOTIATING": "Adult owner manually sends the exact validated reply and confirms its version.",
        "WAITING_CLIENT": "Wait for the client; no automatic follow-up runs in 5A.",
        "SELECTION_REVIEW": "Adult owner urgently reviews selection; no acceptance was performed.",
        "CONTRACT_REVIEW": "Adult owner urgently reviews contract terms; no acceptance was performed.",
        "SELECTED": "Review the contract step manually; Release 5C handoff is not active.",
        "LOST": "No action; the opportunity is retained for audit.",
    }.get(opportunity.state, "Review the current state manually.")
    lines.append(f"<b>Next action (one):</b> {escape_html(action)}")
    parts = _pack_html_lines(lines)
    if len(parts) > 1:
        total = len(parts)
        parts = [f"<b>Lead {index}/{total}</b>\n{part}" for index, part in enumerate(parts, 1)]
    return parts
