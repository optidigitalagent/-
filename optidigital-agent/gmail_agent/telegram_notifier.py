"""Format and send complete, HTML-safe Telegram action cards."""

from __future__ import annotations

import logging
from datetime import timezone
from typing import Any

from bot.html_utils import escape_html, safe_http_url

from .email_analyzer import JobAnalysis
from .email_classifier import EmailType
from .live_status import LiveStatus

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


def _score_emoji(score: float) -> str:
    if score >= 8:
        return "🔥"
    if score >= 6:
        return "✅"
    if score >= 4:
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
    lines = [
        f"{_score_emoji(analysis.score)} <b>New Job Match</b> {_urgency_emoji(analysis.urgency)}",
        f"<b>Event:</b> {escape_html(_short(analysis.event_type))}",
        f"<b>Отримано:</b> {escape_html(_received(analysis.received_at))}",
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
        f"<b>Score:</b> {escape_html(analysis.score_display)}",
        f"<b>Бюджет:</b> {escape_html(_short(analysis.budget))}",
        f"<b>Мова клієнта:</b> {escape_html(_short(analysis.language))}",
        f"<b>Повнота ТЗ:</b> {escape_html(_short(analysis.description_completeness))}",
        f"<b>Строк:</b> {escape_html(_short(analysis.deadline))}",
        f"<b>Категорія:</b> {escape_html(_short(analysis.category))}",
        f"<b>Ставок:</b> {escape_html(analysis.bid_count if analysis.bid_count is not None else '—')}",
        f"<b>Клієнт:</b> {escape_html(_short(analysis.client_name))}",
        "",
        f"<b>Service lane:</b> {escape_html(_short(analysis.service_lane))}",
        f"<b>Можемо виконати:</b> {escape_html(_short(analysis.executable or 'uncertain'))}",
        f"<b>Fit:</b> {escape_html(analysis.score_display)}",
        f"<b>Win signal:</b> {escape_html(_short(analysis.win_probability_signal))}",
        f"<b>Scope clarity:</b> {escape_html(_short(analysis.scope_clarity))}",
        f"<b>Трудомісткість:</b> {escape_html(_short(analysis.estimated_effort))}",
        f"<b>Ризик розробки:</b> {escape_html(_short(analysis.delivery_risk))}",
        f"<b>Ризик клієнта/оплати:</b> {escape_html(_short(analysis.client_payment_risk))}",
        f"<b>Режим:</b> {escape_html(_short(analysis.project_mode))} — {escape_html(_short(analysis.project_mode_reason))}",
        f"<b>Рекомендована ціна:</b> {escape_html(_short(analysis.recommended_price))}",
        f"<b>Реалістичний строк:</b> {escape_html(_short(analysis.realistic_timeline))}",
        f"<b>Релевантний кейс:</b> {escape_html(_short(analysis.selected_evidence))}",
    ]
    if analysis.reason:
        lines += [f"<b>Оцінка:</b> {escape_html(_short(analysis.reason))}"]
    if analysis.why_relevant:
        lines += [f"<b>Чому підходить:</b> {escape_html(_short(analysis.why_relevant))}"]
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
        in {EmailType.PROJECT_SINGLE.value, EmailType.PROJECT_DIGEST.value}
        and analysis.live_status
        and analysis.live_status != LiveStatus.ACTIVE_BIDDABLE.value
    ):
        return [format_live_status_card(analysis)]

    if analysis.event_type == EmailType.CLIENT_PRIVATE_MESSAGE.value:
        summary = _private_summary_lines(analysis)
        body_label = "Повний безпечний текст повідомлення"
        draft_label = "Готова відповідь"
    elif analysis.event_type in {
        EmailType.PROJECT_SINGLE.value,
        EmailType.PROJECT_DIGEST.value,
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

    next_action = analysis.next_action or (
        "Відкрити подію на Freelancehunt і виконати фінальну дію особисто."
    )
    commands = (
        f"<b>Наступна дія власниці:</b> {escape_html(next_action)}\n\n"
        f"<code>/reply_job {escape_html(analysis.email_id)}</code>   "
        f"<code>/skip_job {escape_html(analysis.email_id)}</code>"
    )
    _append_html_section(parts, commands)

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
            "Sent Telegram event card: event=%s key=%s parts=%d score=%.1f",
            analysis.event_type,
            analysis.email_id,
            len(parts),
            analysis.score,
        )
        return True
    except Exception:
        logger.exception("Failed to send job card: email_id=%s", analysis.email_id)
        return False
