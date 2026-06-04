"""APScheduler hook for Gmail-based job checking."""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def check_gmail_jobs(bot: Any) -> None:
    """Entry point called by APScheduler."""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import settings

    gmail_enabled = os.getenv("GMAIL_ENABLED", "false").lower() == "true"
    if not gmail_enabled:
        logger.debug("Gmail agent disabled (GMAIL_ENABLED=false)")
        return

    use_mock = os.getenv("GMAIL_USE_MOCK", "true").lower() == "true"
    credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
    token_file = os.getenv("GMAIL_TOKEN_FILE", "gmail_token.json")
    min_score = float(os.getenv("GMAIL_MIN_SCORE", "6"))

    from .gmail_provider import build_provider
    from .processor import GmailJobProcessor

    provider = build_provider(
        use_mock=use_mock,
        credentials_file=credentials_file,
        token_file=token_file,
    )

    processor = GmailJobProcessor(
        provider=provider,
        bot=bot,
        chat_id=settings.TELEGRAM_CHAT_ID,
        min_score=min_score,
    )

    stats = await processor.run()
    logger.info(
        "Gmail check done: fetched=%d sent=%d errors=%d",
        stats.emails_fetched, stats.sent, stats.errors,
    )


def register_gmail_job(scheduler: Any, bot: Any, interval_minutes: int = 30) -> None:
    """Register Gmail check as APScheduler recurring job."""
    gmail_enabled = os.getenv("GMAIL_ENABLED", "false").lower() == "true"
    if not gmail_enabled:
        logger.info("Gmail agent disabled — skipping scheduler registration")
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
