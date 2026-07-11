"""APScheduler hook for Gmail-based job checking."""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def check_gmail_jobs(bot: Any) -> None:
    """Entry point called by APScheduler."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import settings

    if not settings.GMAIL_ENABLED:
        logger.debug("Gmail agent disabled (GMAIL_ENABLED=false)")
        return

    logger.info("=== GMAIL AUTO SCAN STARTED ===")

    from .gmail_provider import build_provider
    from .processor import GmailJobProcessor

    try:
        provider = build_provider(
            use_mock=settings.GMAIL_USE_MOCK,
            credentials_file=settings.GMAIL_CREDENTIALS_FILE,
            token_file=settings.GMAIL_TOKEN_FILE,
        )

        processor = GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=settings.TELEGRAM_CHAT_ID,
            min_score=settings.GMAIL_MIN_SCORE,
        )

        stats = await processor.run()

    except Exception as exc:
        logger.exception("GMAIL AUTO SCAN failed with exception")
        try:
            await bot.send_message(
                chat_id=settings.admin_chat_id,
                text=f"ERROR <b>Gmail Auto Scan failed</b>\n\n<code>{exc}</code>",
            )
        except Exception:
            logger.exception("Failed to send Gmail error alert to Telegram")
        return

    logger.info(
        "=== GMAIL AUTO SCAN DONE: fetched=%d sent=%d errors=%d ===",
        stats.emails_fetched,
        stats.sent,
        stats.errors,
    )

    if stats.errors > 0:
        try:
            details = "\n".join(stats.error_details[:3])
            details_block = f"\n\n<code>{details}</code>" if details else ""
            await bot.send_message(
                chat_id=settings.admin_chat_id,
                text=(
                    "WARNING <b>Gmail Auto Scan errors</b>\n\n"
                    f"fetched={stats.emails_fetched} sent={stats.sent} errors={stats.errors}"
                    f"{details_block}"
                ),
            )
        except Exception:
            logger.exception("Failed to send Gmail partial-error alert to Telegram")

    try:
        from datetime import datetime
        import sys as _sys

        sys_path = str(Path(__file__).parent.parent)
        if sys_path not in _sys.path:
            _sys.path.insert(0, sys_path)
        import state as _state

        new_count = stats.emails_fetched - stats.duplicates_skipped
        analyzed_count = max(0, new_count - stats.not_relevant)
        _state.gmail_scan_history.append(
            {
                "timestamp": datetime.utcnow(),
                "emails_found": stats.emails_fetched,
                "relevant": analyzed_count,
                "sent": stats.sent,
                "errors": stats.errors,
            }
        )
        if len(_state.gmail_scan_history) > 20:
            _state.gmail_scan_history = _state.gmail_scan_history[-20:]
    except Exception:
        logger.exception("Failed to save gmail scan history")


def register_gmail_job(scheduler: Any, bot: Any, interval_minutes: int = 30) -> None:
    """Register Gmail check as APScheduler recurring job."""
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import settings

    if not settings.GMAIL_ENABLED:
        logger.info("Gmail agent disabled - skipping scheduler registration")
        return

    scheduler.add_job(
        check_gmail_jobs,
        trigger="interval",
        minutes=interval_minutes,
        id="check_gmail_jobs",
        args=[bot],
        max_instances=1,
        coalesce=True,
    )
    logger.info("Gmail job registered: interval=%d min", interval_minutes)
