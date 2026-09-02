"""Sends job analysis cards to Telegram."""

import logging
from typing import Any

from bot.html_utils import escape_html, safe_http_url

from .email_analyzer import JobAnalysis

logger = logging.getLogger(__name__)


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


def format_job_card(analysis: JobAnalysis) -> str:
    se = _score_emoji(analysis.score)
    ue = _urgency_emoji(analysis.urgency)
    safe_url = safe_http_url(analysis.url)

    lines = [
        f"{se} <b>New Job Match</b> {ue}",
        "",
        f"<b>Платформа:</b> {escape_html(analysis.platform)}",
        f"<b>Назва:</b> {escape_html(analysis.title)}",
        f"<b>Score:</b> {escape_html(analysis.score_display)}",
        f"<b>Бюджет:</b> {escape_html(analysis.budget)}",
    ]

    if analysis.reason:
        lines += ["", f"<b>Оцінка:</b> {escape_html(analysis.reason)}"]

    if analysis.why_relevant:
        lines += [f"<b>Чому підходить:</b> {escape_html(analysis.why_relevant)}"]

    if analysis.red_flags:
        flags = ", ".join(escape_html(flag) for flag in analysis.red_flags)
        lines += [f"<b>Ризики:</b> {flags}"]

    if safe_url:
        lines += ["", f'🔗 <a href="{escape_html(safe_url)}">Відкрити замовлення</a>']
    else:
        lines += ["", "🔗 Посилання відсутнє"]

    lines += [
        "",
        f"<code>/reply_job {escape_html(analysis.email_id)}</code>   "
        f"<code>/skip_job {escape_html(analysis.email_id)}</code>",
    ]

    return "\n".join(lines)


async def send_job_card(
    bot: Any,
    chat_id: int,
    analysis: JobAnalysis,
) -> bool:
    try:
        text = format_job_card(analysis)
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info(
            "Sent job card to Telegram: email_id=%s score=%.1f title=%r",
            analysis.email_id, analysis.score, analysis.title,
        )
        return True
    except Exception:
        logger.exception(
            "Failed to send job card: email_id=%s", analysis.email_id
        )
        return False
