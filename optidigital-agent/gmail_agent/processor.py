"""Main pipeline: fetch emails → analyze → deduplicate → notify Telegram."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .dedup import EmailDedup
from .email_analyzer import JobAnalysis, analyze_email
from .gmail_provider import GmailProvider
from .telegram_notifier import send_job_card

logger = logging.getLogger(__name__)


@dataclass
class ProcessorStats:
    emails_fetched: int = 0
    duplicates_skipped: int = 0
    not_relevant: int = 0
    below_threshold: int = 0
    sent: int = 0
    errors: int = 0
    sent_analyses: list[JobAnalysis] = field(default_factory=list)


class GmailJobProcessor:
    def __init__(
        self,
        provider: GmailProvider,
        bot: Any,
        chat_id: int,
        min_score: float = 6.0,
        dedup: EmailDedup | None = None,
        openai_client: Any | None = None,
        dedup_path: str | Path | None = None,
    ):
        self._provider = provider
        self._bot = bot
        self._chat_id = chat_id
        self._min_score = min_score
        self._dedup = dedup or EmailDedup(dedup_path or Path(__file__).parent / "processed_emails.json")
        self._openai_client = openai_client

    async def run(self) -> ProcessorStats:
        stats = ProcessorStats()

        try:
            emails = await self._provider.get_new_emails()
        except Exception:
            logger.exception("GmailJobProcessor: failed to fetch emails")
            stats.errors += 1
            return stats

        stats.emails_fetched = len(emails)
        logger.info("GmailJobProcessor: fetched %d emails", stats.emails_fetched)

        for email in emails:
            try:
                if self._dedup.is_processed(email.id):
                    stats.duplicates_skipped += 1
                    logger.debug("Duplicate skipped: %s", email.id)
                    continue

                analysis = await analyze_email(
                    email_id=email.id,
                    subject=email.subject,
                    sender=email.sender,
                    body=email.body,
                    client=self._openai_client,
                )

                # Mark processed regardless of score — prevents reprocessing
                self._dedup.mark_processed(email.id)
                await self._provider.mark_as_processed(email.id)

                if not analysis.is_relevant:
                    stats.not_relevant += 1
                    logger.info(
                        "Not relevant: email_id=%s subject=%r", email.id, email.subject
                    )
                    continue

                if analysis.score < self._min_score:
                    stats.below_threshold += 1
                    logger.info(
                        "Below threshold: email_id=%s score=%.1f < %.1f",
                        email.id, analysis.score, self._min_score,
                    )
                    continue

                await send_job_card(self._bot, self._chat_id, analysis)
                stats.sent += 1
                stats.sent_analyses.append(analysis)

                # Register in handler store so /reply_job can find it
                try:
                    from bot.handlers import register_gmail_job_analysis
                    register_gmail_job_analysis({
                        "email_id": analysis.email_id,
                        "title": analysis.title,
                        "platform": analysis.platform,
                        "score": analysis.score,
                        "reason": analysis.reason,
                        "budget": analysis.budget,
                        "url": analysis.url,
                        "urgency": analysis.urgency,
                        "why_relevant": analysis.why_relevant,
                    })
                except ImportError:
                    pass

            except Exception:
                stats.errors += 1
                logger.exception("Error processing email_id=%s", email.id)

        logger.info(
            "GmailJobProcessor done: fetched=%d dup=%d not_relevant=%d "
            "below_threshold=%d sent=%d errors=%d",
            stats.emails_fetched, stats.duplicates_skipped, stats.not_relevant,
            stats.below_threshold, stats.sent, stats.errors,
        )
        return stats
