"""Sends job analysis cards to Telegram."""

import logging
from typing import Any

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

    lines = [
        f"{se} <b>New Job Match</b> {ue}",
        "",
        f"<b>Платформа:</b> {analysis.platform}",
        f"<b>Назва:</b> {analysis.title}",
        f"<b>Score:</b> {analysis.score_display}",
        f"<b>Бюджет:</b> {analysis.budget}",
    ]

    if analysis.reason:
        lines += ["", f"<b>Оцінка:</b> {analysis.reason}"]

    if analysis.why_relevant:
        lines += [f"<b>Чому підходить:</b> {analysis.why_relevant}"]

    if analysis.red_flags:
        flags = ", ".join(analysis.red_flags)
        lines += [f"<b>Ризики:</b> {flags}"]

    if analysis.url:
        lines += ["", f'🔗 <a href="{analysis.url}">Відкрити замовлення</a>']

    lines += [
        "",
        f"<code>/reply_job {analysis.email_id}</code>   "
        f"<code>/skip_job {analysis.email_id}</code>",
    ]

    return "\n".join(lines)


async def send_job_card(
    bot: Any,
    chat_id: int,
    analysis: JobAnalysis,
) -> None:
    text = format_job_card(analysis)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            disable_web_page_preview=True,
        )
        logger.info(
            "Sent job card to Telegram: email_id=%s score=%.1f title=%r",
            analysis.email_id, analysis.score, analysis.title,
        )
    except Exception:
        logger.exception(
            "Failed to send job card: email_id=%s", analysis.email_id
        )
