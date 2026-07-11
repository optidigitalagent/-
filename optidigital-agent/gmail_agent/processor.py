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
    error_details: list[str] = field(default_factory=list)
    sent_analyses: list[JobAnalysis] = field(default_factory=list)
    # First 5 samples for diagnostic display
    rejected_samples: list[dict] = field(default_factory=list)
    below_score_samples: list[dict] = field(default_factory=list)


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
        job_store_path: str | Path | None = None,
    ):
        self._provider = provider
        self._bot = bot
        self._chat_id = chat_id
        self._min_score = min_score
        self._dedup = dedup or EmailDedup(dedup_path or Path(__file__).parent / "processed_emails.json")
        self._openai_client = openai_client
        self._job_store_path = job_store_path

    async def _mark_processed(self, email_id: str) -> None:
        self._dedup.mark_processed(email_id)
        await self._provider.mark_as_processed(email_id)

    async def run(self) -> ProcessorStats:
        stats = ProcessorStats()

        try:
            emails = await self._provider.get_new_emails()
        except Exception as exc:
            logger.exception("GmailJobProcessor: failed to fetch emails")
            stats.errors += 1
            stats.error_details.append(str(exc))
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

                if not analysis.is_relevant:
                    await self._mark_processed(email.id)
                    stats.not_relevant += 1
                    logger.info(
                        "Not relevant: email_id=%s subject=%r", email.id, email.subject
                    )
                    if len(stats.rejected_samples) < 5:
                        stats.rejected_samples.append({
                            "from": email.sender[:50],
                            "subject": email.subject[:60],
                            "reason": analysis.reason or "not_job_alert",
                        })
                    continue

                if analysis.score < self._min_score:
                    await self._mark_processed(email.id)
                    stats.below_threshold += 1
                    logger.info(
                        "Below threshold: email_id=%s score=%.1f < %.1f",
                        email.id, analysis.score, self._min_score,
                    )
                    if len(stats.below_score_samples) < 5:
                        stats.below_score_samples.append({
                            "subject": email.subject[:60],
                            "score": analysis.score,
                            "reason": analysis.reason,
                    })
                    continue

                sent_ok = await send_job_card(self._bot, self._chat_id, analysis)
                if not sent_ok:
                    stats.errors += 1
                    stats.error_details.append(f"{email.id}: Telegram send failed")
                    continue

                await self._mark_processed(email.id)
                stats.sent += 1
                stats.sent_analyses.append(analysis)

                # Persist so /reply_job can find the job after a process restart.
                try:
                    from .job_store import save_job
                    save_job({
                        "email_id": analysis.email_id,
                        "title": analysis.title,
                        "platform": analysis.platform,
                        "score": analysis.score,
                        "reason": analysis.reason,
                        "budget": analysis.budget,
                        "url": analysis.url,
                        "urgency": analysis.urgency,
                        "why_relevant": analysis.why_relevant,
                    }, path=self._job_store_path)
                except Exception as exc:
                    stats.errors += 1
                    stats.error_details.append(f"{email.id}: job store save failed: {exc}")
                    logger.exception("Failed to persist Gmail job analysis")

            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(f"{email.id}: {exc}")
                logger.exception("Error processing email_id=%s", email.id)

        logger.info(
            "GmailJobProcessor done: fetched=%d dup=%d not_relevant=%d "
            "below_threshold=%d sent=%d errors=%d",
            stats.emails_fetched, stats.duplicates_skipped, stats.not_relevant,
            stats.below_threshold, stats.sent, stats.errors,
        )
        return stats

    async def run_debug(self, max_emails: int = 20) -> list[dict]:
        """Full pipeline analysis without sending to Telegram or marking as processed.

        Does NOT call send_job_card and does NOT update dedup state.
        Safe to run at any time without side effects.
        """
        results: list[dict] = []
        try:
            emails = await self._provider.get_new_emails()
        except Exception as exc:
            logger.exception("run_debug: failed to fetch emails")
            return [{"error": str(exc), "subject": "FETCH ERROR", "email_id": ""}]

        for email in emails[:max_emails]:
            entry: dict = {
                "email_id": email.id,
                "from": email.sender,
                "subject": email.subject,
                "date": email.received_at.strftime("%d.%m.%Y %H:%M") if email.received_at else "—",
                "is_duplicate": self._dedup.is_processed(email.id),
                "is_relevant": None,
                "score": None,
                "reason": None,
                "passed": False,
                "error": None,
            }
            if entry["is_duplicate"]:
                results.append(entry)
                continue
            try:
                analysis = await analyze_email(
                    email_id=email.id,
                    subject=email.subject,
                    sender=email.sender,
                    body=email.body,
                    client=self._openai_client,
                )
                entry["is_relevant"] = analysis.is_relevant
                entry["score"] = analysis.score
                entry["reason"] = analysis.reason
                entry["passed"] = analysis.is_relevant and analysis.score >= self._min_score
            except Exception as exc:
                logger.exception("run_debug: analyze failed for email_id=%s", email.id)
                entry["error"] = str(exc)
            results.append(entry)
        return results
