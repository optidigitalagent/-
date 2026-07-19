"""Main Gmail pipeline: classify, analyze, deduplicate, and notify Telegram."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .dedup import EmailDedup
from .digest_parser import DigestJobCandidate, parse_freelancehunt_digest
from .email_analyzer import JobAnalysis, analyze_candidate, analyze_email
from .email_classifier import EmailType, classify_email
from .gmail_provider import EmailMessage, GmailProvider
from .storage import (
    GmailRepository,
    ProcessedItem,
    ScanRun,
    StoredGmailJob,
)
from .telegram_notifier import send_job_card

logger = logging.getLogger(__name__)


@dataclass
class ProcessorStats:
    emails_fetched: int = 0
    candidates_found: int = 0
    ai_analyzed: int = 0
    duplicates_skipped: int = 0
    relevant: int = 0
    qualified: int = 0
    not_relevant: int = 0
    below_threshold: int = 0
    sent: int = 0
    sent_from_queue: int = 0
    errors: int = 0
    parser_failures: int = 0
    error_details: list[str] = field(default_factory=list)
    sent_analyses: list[JobAnalysis] = field(default_factory=list)
    # First 5 samples for diagnostic display.
    rejected_samples: list[dict] = field(default_factory=list)
    below_score_samples: list[dict] = field(default_factory=list)

    @property
    def duplicates(self) -> int:
        """Short alias used by scan reporting code."""
        return self.duplicates_skipped


@dataclass(frozen=True)
class DigestPreviewItem:
    stable_key: str
    title: str
    is_relevant: bool
    score: float
    reason: str
    platform: str
    budget: str
    url: str
    urgency: str
    why_relevant: str


@dataclass(frozen=True)
class DigestPreviewResult:
    items: list[DigestPreviewItem]
    stats: ProcessorStats


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
        repository: GmailRepository | None = None,
        max_cards_per_scan: int = 10,
        digest_enabled: bool = True,
    ):
        self._provider = provider
        self._bot = bot
        self._chat_id = chat_id
        self._min_score = min_score
        self._dedup = dedup or EmailDedup(
            dedup_path or Path(__file__).parent / "processed_emails.json"
        )
        self._openai_client = openai_client
        self._job_store_path = job_store_path
        self._repository = repository
        self._max_cards_per_scan = max(0, max_cards_per_scan)
        self._digest_enabled = digest_enabled

    async def _mark_processed(self, email_id: str) -> None:
        self._dedup.mark_processed(email_id)
        await self._provider.mark_as_processed(email_id)

    @staticmethod
    def _email_type(email: EmailMessage) -> EmailType:
        return classify_email(
            sender=email.sender,
            subject=email.subject,
            text_body=email.text_body or email.body,
            html_body=email.html_body,
        )

    @staticmethod
    def _is_freelancehunt_digest(email: EmailMessage, email_type: EmailType) -> bool:
        return (
            email_type == EmailType.JOB_DIGEST
            and "freelancehunt" in email.sender.casefold()
        )

    @staticmethod
    def _analysis_from_job(job: StoredGmailJob) -> JobAnalysis:
        return JobAnalysis(
            email_id=job.stable_key,
            is_relevant=True,
            title=job.title,
            platform=job.platform,
            score=job.score,
            reason=job.reason,
            budget=job.budget or "",
            url=job.url or "",
            urgency=job.urgency,
            why_relevant=job.why_relevant,
            red_flags=[],
        )

    @staticmethod
    def _stored_job(
        candidate: DigestJobCandidate,
        analysis: JobAnalysis,
        status: str = "queued",
    ) -> StoredGmailJob:
        return StoredGmailJob(
            stable_key=candidate.stable_key,
            source_email_id=candidate.source_email_id,
            platform=analysis.platform or candidate.platform,
            title=analysis.title or candidate.title,
            score=analysis.score,
            reason=analysis.reason,
            budget=analysis.budget or candidate.budget or None,
            url=candidate.url or analysis.url or None,
            urgency=analysis.urgency,
            why_relevant=analysis.why_relevant,
            status=status,
        )

    @staticmethod
    def _processed_item(
        candidate: DigestJobCandidate,
        decision: str,
        score: float | None,
    ) -> ProcessedItem:
        return ProcessedItem(
            stable_key=candidate.stable_key,
            source_email_id=candidate.source_email_id,
            platform=candidate.platform,
            item_type="digest_job",
            title=candidate.title,
            url=candidate.url,
            decision=decision,
            score=score,
        )

    @staticmethod
    def _candidate_from_job(job: StoredGmailJob) -> DigestJobCandidate:
        """Rebuild the minimum candidate identity needed to deliver a saved job."""
        return DigestJobCandidate(
            source_email_id=job.source_email_id,
            platform=job.platform,
            title=job.title,
            description="",
            budget=job.budget or "",
            url=job.url or "",
            category="",
            received_at=None,
            stable_key=job.stable_key,
        )

    @staticmethod
    def _processed_job_item(
        job: StoredGmailJob,
        decision: str,
    ) -> ProcessedItem:
        return ProcessedItem(
            stable_key=job.stable_key,
            source_email_id=job.source_email_id,
            platform=job.platform,
            item_type=(
                "single_job"
                if job.stable_key == job.source_email_id
                else "digest_job"
            ),
            title=job.title,
            url=job.url,
            decision=decision,
            score=job.score,
        )

    @staticmethod
    def _stored_single_job(
        email: EmailMessage,
        analysis: JobAnalysis,
        status: str = "queued",
    ) -> StoredGmailJob:
        return StoredGmailJob(
            stable_key=email.id,
            source_email_id=email.id,
            platform=analysis.platform,
            title=analysis.title,
            score=analysis.score,
            reason=analysis.reason,
            budget=analysis.budget or None,
            url=analysis.url or None,
            urgency=analysis.urgency,
            why_relevant=analysis.why_relevant,
            status=status,
        )

    @staticmethod
    def _processed_single_item(
        email: EmailMessage,
        analysis: JobAnalysis,
        decision: str,
    ) -> ProcessedItem:
        return ProcessedItem(
            stable_key=email.id,
            source_email_id=email.id,
            platform=analysis.platform,
            item_type="single_job",
            title=analysis.title or email.subject,
            url=analysis.url or None,
            decision=decision,
            score=analysis.score,
        )

    @staticmethod
    def _processed_email_item(
        email: EmailMessage,
        email_type: EmailType,
        decision: str,
    ) -> ProcessedItem:
        return ProcessedItem(
            stable_key=email.id,
            source_email_id=email.id,
            platform="Work.ua" if "work.ua" in email.sender.casefold() else "",
            item_type=email_type.value,
            title=email.subject,
            url=None,
            decision=decision,
            score=None,
        )

    @staticmethod
    def _processed_digest_parent(email: EmailMessage) -> ProcessedItem:
        return ProcessedItem(
            stable_key=f"parent:{email.id}",
            source_email_id=email.id,
            platform="Freelancehunt",
            item_type="digest_parent",
            title=email.subject,
            url=None,
            decision="extracted",
            score=None,
        )

    def _record_rejected_sample(
        self, stats: ProcessorStats, email: EmailMessage, reason: str
    ) -> None:
        if len(stats.rejected_samples) < 5:
            stats.rejected_samples.append(
                {
                    "from": email.sender[:50],
                    "subject": email.subject[:60],
                    "reason": reason,
                }
            )

    @staticmethod
    def _record_below_sample(
        stats: ProcessorStats, title: str, analysis: JobAnalysis
    ) -> None:
        if len(stats.below_score_samples) < 5:
            stats.below_score_samples.append(
                {
                    "subject": title[:60],
                    "score": analysis.score,
                    "reason": analysis.reason,
                }
            )

    def _persist_legacy_job(self, analysis: JobAnalysis, stats: ProcessorStats) -> None:
        """Keep /reply_job's JSON lookup behavior for both pipeline paths."""
        try:
            from .job_store import save_job

            save_job(
                {
                    "email_id": analysis.email_id,
                    "title": analysis.title,
                    "platform": analysis.platform,
                    "score": analysis.score,
                    "reason": analysis.reason,
                    "budget": analysis.budget,
                    "url": analysis.url,
                    "urgency": analysis.urgency,
                    "why_relevant": analysis.why_relevant,
                },
                path=self._job_store_path,
            )
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(
                f"{analysis.email_id}: job store save failed: {exc}"
            )
            logger.exception("Failed to persist Gmail job analysis")

    async def _send_stored_job(
        self,
        candidate: DigestJobCandidate,
        job: StoredGmailJob,
        stats: ProcessorStats,
    ) -> bool:
        """Claim and send a queued job; return whether the child is handled."""
        assert self._repository is not None
        claimed = await self._repository.claim_job(candidate.stable_key)
        if not claimed:
            # Another worker owns it, or it became terminal after our read.
            if await self._repository.is_processed(candidate.stable_key):
                stats.duplicates_skipped += 1
            return False

        analysis = self._analysis_from_job(job)
        try:
            sent_ok = await send_job_card(self._bot, self._chat_id, analysis)
        except Exception as exc:
            await self._repository.update_job_status(candidate.stable_key, "send_failed")
            stats.errors += 1
            stats.error_details.append(f"{candidate.stable_key}: {exc}")
            logger.exception("Digest Telegram send raised for %s", candidate.stable_key)
            return True

        if not sent_ok:
            await self._repository.update_job_status(candidate.stable_key, "send_failed")
            stats.errors += 1
            stats.error_details.append(
                f"{candidate.stable_key}: Telegram send failed"
            )
            return True

        await self._repository.update_job_status(candidate.stable_key, "sent")
        await self._repository.upsert_processed(
            self._processed_job_item(job, "sent")
        )
        stats.sent += 1
        stats.sent_analyses.append(analysis)
        return True

    async def _drain_retry_queue(
        self,
        stats: ProcessorStats,
        cards_sent_this_scan: int = 0,
    ) -> int:
        """Deliver persisted retryable jobs without re-fetching or re-analyzing."""
        if self._repository is None:
            return cards_sent_this_scan

        remaining = self._max_cards_per_scan - cards_sent_this_scan
        if remaining <= 0:
            return cards_sent_this_scan

        try:
            if self._digest_enabled:
                jobs = await self._repository.list_retryable_jobs(limit=remaining)
            else:
                # Digest rows may be older than single-job rows. Grow the
                # read window until it includes enough eligible singles (or
                # the queue is exhausted), so disabled digests cannot starve
                # the established single-job retry flow.
                read_limit = remaining
                while True:
                    retryable = await self._repository.list_retryable_jobs(
                        limit=read_limit
                    )
                    jobs = [
                        job
                        for job in retryable
                        if job.stable_key == job.source_email_id
                    ]
                    if len(jobs) >= remaining or len(retryable) < read_limit:
                        jobs = jobs[:remaining]
                        break
                    read_limit *= 2
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(f"retry queue read failed: {exc}")
            logger.exception("Failed to read Gmail retry queue")
            return cards_sent_this_scan

        for job in jobs:
            if cards_sent_this_scan >= self._max_cards_per_scan:
                break
            try:
                sent_before = stats.sent
                attempted = await self._send_stored_job(
                    self._candidate_from_job(job), job, stats
                )
                if stats.sent > sent_before:
                    stats.sent_from_queue += stats.sent - sent_before
                if attempted:
                    cards_sent_this_scan += 1
            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(f"{job.stable_key}: {exc}")
                logger.exception(
                    "Error draining Gmail job stable_key=%s", job.stable_key
                )
        return cards_sent_this_scan

    async def _process_digest(
        self,
        email: EmailMessage,
        stats: ProcessorStats,
        cards_sent_this_scan: int,
    ) -> int:
        """Process one digest and return the updated per-scan card count."""
        assert self._repository is not None
        try:
            candidates = parse_freelancehunt_digest(email)
            if not candidates:
                raise ValueError("digest parser found no job candidates")
        except Exception as exc:
            stats.errors += 1
            stats.parser_failures += 1
            stats.error_details.append(f"{email.id}: digest parser failed: {exc}")
            logger.exception("Digest parser failed for email_id=%s", email.id)
            return cards_sent_this_scan

        stats.candidates_found += len(candidates)
        all_children_handled = True

        for candidate in candidates:
            try:
                if await self._repository.is_processed(candidate.stable_key):
                    stats.duplicates_skipped += 1
                    continue

                job = await self._repository.get_job(candidate.stable_key)
                if job is None:
                    analysis = await analyze_candidate(
                        candidate, client=self._openai_client
                    )
                    if analysis.analysis_succeeded:
                        stats.ai_analyzed += 1
                    else:
                        stats.errors += 1
                        stats.error_details.append(
                            f"{candidate.stable_key}: AI analysis failed"
                        )
                    if not analysis.is_relevant:
                        await self._repository.upsert_processed(
                            self._processed_item(
                                candidate, "not_relevant", analysis.score
                            )
                        )
                        if analysis.analysis_succeeded:
                            stats.not_relevant += 1
                        continue

                    stats.relevant += 1
                    if analysis.score < self._min_score:
                        await self._repository.upsert_processed(
                            self._processed_item(
                                candidate, "below_threshold", analysis.score
                            )
                        )
                        stats.below_threshold += 1
                        self._record_below_sample(stats, candidate.title, analysis)
                        continue

                    stats.qualified += 1

                    job = await self._repository.save_job(
                        self._stored_job(candidate, analysis)
                    )
                elif job.status in {"sent", "skipped"}:
                    stats.duplicates_skipped += 1
                    continue

                if cards_sent_this_scan >= self._max_cards_per_scan:
                    # Existing send_failed rows stay retryable; fresh rows stay queued.
                    continue

                attempted = await self._send_stored_job(candidate, job, stats)
                if attempted:
                    cards_sent_this_scan += 1
            except Exception as exc:
                all_children_handled = False
                stats.errors += 1
                stats.error_details.append(f"{candidate.stable_key}: {exc}")
                logger.exception(
                    "Error processing digest child stable_key=%s", candidate.stable_key
                )

        # Parent IDs are only a fetch optimization. Child stable keys remain the
        # authoritative dedup keys, so already-marked parents are still parsed.
        if all_children_handled:
            await self._repository.upsert_processed(
                self._processed_digest_parent(email)
            )
            await self._provider.mark_as_processed(email.id)
        return cards_sent_this_scan

    async def _process_single(
        self,
        email: EmailMessage,
        stats: ProcessorStats,
        allow_send: bool = True,
    ) -> bool:
        """Process a single-job email and report whether a card was attempted."""
        if self._repository is not None:
            return await self._process_repository_single(
                email, stats, allow_send=allow_send
            )

        if self._dedup.is_processed(email.id):
            stats.duplicates_skipped += 1
            logger.debug("Duplicate skipped: %s", email.id)
            return False

        analysis = await analyze_email(
            email_id=email.id,
            subject=email.subject,
            sender=email.sender,
            body=email.body,
            client=self._openai_client,
        )
        if analysis.analysis_succeeded:
            stats.ai_analyzed += 1
        else:
            stats.errors += 1
            stats.error_details.append(f"{email.id}: AI analysis failed")

        if not analysis.is_relevant:
            await self._mark_processed(email.id)
            if analysis.analysis_succeeded:
                stats.not_relevant += 1
                self._record_rejected_sample(
                    stats, email, analysis.reason or "not_job_alert"
                )
            return False

        stats.relevant += 1
        if analysis.score < self._min_score:
            await self._mark_processed(email.id)
            stats.below_threshold += 1
            self._record_below_sample(stats, email.subject, analysis)
            return False

        stats.qualified += 1

        # Legacy mode has no durable queued-job store. Leaving the email
        # unmarked makes an above-threshold item retryable on the next scan.
        if not allow_send:
            return False

        sent_ok = await send_job_card(self._bot, self._chat_id, analysis)
        if not sent_ok:
            stats.errors += 1
            stats.error_details.append(f"{email.id}: Telegram send failed")
            return True

        await self._mark_processed(email.id)
        stats.sent += 1
        stats.sent_analyses.append(analysis)
        self._persist_legacy_job(analysis, stats)
        return True

    async def _process_repository_single(
        self,
        email: EmailMessage,
        stats: ProcessorStats,
        allow_send: bool = True,
    ) -> bool:
        """Process one non-digest job with the repository as source of truth."""
        assert self._repository is not None

        if await self._repository.is_processed(email.id):
            stats.duplicates_skipped += 1
            return False

        job = await self._repository.get_job(email.id)
        if job is not None:
            if job.status in {"sent", "skipped"}:
                stats.duplicates_skipped += 1
                return False
            analysis = self._analysis_from_job(job)
        else:
            analysis = await analyze_email(
                email_id=email.id,
                subject=email.subject,
                sender=email.sender,
                body=email.body,
                client=self._openai_client,
            )
            if analysis.analysis_succeeded:
                stats.ai_analyzed += 1
            else:
                stats.errors += 1
                stats.error_details.append(f"{email.id}: AI analysis failed")

            if not analysis.is_relevant:
                await self._repository.upsert_processed(
                    self._processed_single_item(email, analysis, "not_relevant")
                )
                if analysis.analysis_succeeded:
                    stats.not_relevant += 1
                    self._record_rejected_sample(
                        stats, email, analysis.reason or "not_job_alert"
                    )
                return False

            stats.relevant += 1
            if analysis.score < self._min_score:
                await self._repository.upsert_processed(
                    self._processed_single_item(email, analysis, "below_threshold")
                )
                stats.below_threshold += 1
                self._record_below_sample(stats, email.subject, analysis)
                return False

            stats.qualified += 1

            job = await self._repository.save_job(
                self._stored_single_job(email, analysis)
            )
            # Send the persisted representation so the Telegram command key
            # and repository lookup key are guaranteed to be identical.
            analysis = self._analysis_from_job(job)

        if not allow_send:
            return False

        claimed = await self._repository.claim_job(job.stable_key)
        if not claimed:
            if await self._repository.is_processed(job.stable_key):
                stats.duplicates_skipped += 1
            return False

        try:
            sent_ok = await send_job_card(self._bot, self._chat_id, analysis)
        except Exception as exc:
            await self._repository.update_job_status(job.stable_key, "send_failed")
            stats.errors += 1
            stats.error_details.append(f"{job.stable_key}: {exc}")
            logger.exception("Single-job Telegram send raised for %s", job.stable_key)
            return True

        if not sent_ok:
            await self._repository.update_job_status(job.stable_key, "send_failed")
            stats.errors += 1
            stats.error_details.append(f"{job.stable_key}: Telegram send failed")
            return True

        await self._repository.update_job_status(job.stable_key, "sent")
        await self._repository.upsert_processed(
            self._processed_single_item(email, analysis, "sent")
        )
        stats.sent += 1
        stats.sent_analyses.append(analysis)
        return True

    async def _append_scan_run(
        self, trigger: str, started_at: datetime, stats: ProcessorStats
    ) -> None:
        if self._repository is None:
            return
        try:
            await self._repository.append_scan_run(
                ScanRun(
                    trigger=trigger,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    emails_inspected=stats.emails_fetched,
                    candidates_found=stats.candidates_found,
                    ai_analyzed=stats.ai_analyzed,
                    relevant=stats.relevant,
                    qualified=stats.qualified,
                    duplicates=stats.duplicates_skipped,
                    not_relevant=stats.not_relevant,
                    below_threshold=stats.below_threshold,
                    sent=stats.sent,
                    sent_from_queue=stats.sent_from_queue,
                    errors=stats.errors,
                )
            )
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(f"scan run save failed: {exc}")
            logger.exception("Failed to persist Gmail scan run")

    async def _run_emails(
        self,
        emails: list[EmailMessage],
        stats: ProcessorStats,
        cards_sent_this_scan: int = 0,
    ) -> ProcessorStats:
        for email in emails:
            try:
                email_type = self._email_type(email)
                is_freelancehunt_digest = self._is_freelancehunt_digest(
                    email, email_type
                )

                # A recognized digest must never fall through to single-job AI.
                # Leaving both parent and child keys untouched makes the skip
                # retryable when digest processing is enabled later.
                if is_freelancehunt_digest:
                    if not self._digest_enabled or self._repository is None:
                        continue
                    cards_sent_this_scan = await self._process_digest(
                        email, stats, cards_sent_this_scan
                    )
                    continue

                # Deterministic rejection belongs to the repository-backed
                # architecture. With no repository configured, preserve the
                # original analyze_email flow and its diagnostic reasons.
                if self._repository is not None and email_type in {
                    EmailType.INFORMATIONAL_NEWSLETTER,
                    EmailType.ACCOUNT_NOTIFICATION,
                    EmailType.MARKETING,
                }:
                    if await self._repository.is_processed(email.id):
                        stats.duplicates_skipped += 1
                        continue
                    await self._repository.upsert_processed(
                        self._processed_email_item(
                            email, email_type, "not_relevant"
                        )
                    )
                    await self._provider.mark_as_processed(email.id)
                    stats.not_relevant += 1
                    self._record_rejected_sample(stats, email, email_type.value)
                    continue

                attempted = await self._process_single(
                    email,
                    stats,
                    allow_send=(
                        cards_sent_this_scan < self._max_cards_per_scan
                    ),
                )
                if attempted:
                    cards_sent_this_scan += 1
            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(f"{email.id}: {exc}")
                logger.exception("Error processing email_id=%s", email.id)
        return stats

    async def run(self, trigger: str = "manual") -> ProcessorStats:
        stats = ProcessorStats()
        started_at = datetime.now(timezone.utc)
        try:
            cards_sent_this_scan = await self._drain_retry_queue(stats)
            try:
                emails = await self._provider.get_new_emails()
            except Exception as exc:
                logger.exception("GmailJobProcessor: failed to fetch emails")
                stats.errors += 1
                stats.error_details.append(str(exc))
                return stats

            stats.emails_fetched = len(emails)
            logger.info("GmailJobProcessor: fetched %d emails", stats.emails_fetched)
            return await self._run_emails(emails, stats, cards_sent_this_scan)
        finally:
            await self._append_scan_run(trigger, started_at, stats)

    async def run_digest_preview(self, days: int) -> DigestPreviewResult:
        """Parse and score historical digests without any persistent mutation."""
        stats = ProcessorStats()
        items: list[DigestPreviewItem] = []
        try:
            emails = await self._provider.search_freelancehunt_emails(days)
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(str(exc))
            return DigestPreviewResult(items, stats)

        stats.emails_fetched = len(emails)
        for email in emails:
            try:
                candidates = parse_freelancehunt_digest(email)
                if not candidates:
                    raise ValueError("digest parser found no job candidates")
            except Exception as exc:
                stats.errors += 1
                stats.parser_failures += 1
                stats.error_details.append(f"{email.id}: digest parser failed: {exc}")
                continue

            stats.candidates_found += len(candidates)
            for candidate in candidates:
                try:
                    analysis = await analyze_candidate(
                        candidate, client=self._openai_client
                    )
                    if analysis.analysis_succeeded:
                        stats.ai_analyzed += 1
                    else:
                        stats.errors += 1
                        stats.error_details.append(
                            f"{candidate.stable_key}: AI analysis failed"
                        )
                    if analysis.is_relevant:
                        stats.relevant += 1
                    elif analysis.analysis_succeeded:
                        stats.not_relevant += 1
                    if analysis.is_relevant and analysis.score < self._min_score:
                        stats.below_threshold += 1
                    elif analysis.is_relevant:
                        stats.qualified += 1
                    items.append(
                        DigestPreviewItem(
                            stable_key=candidate.stable_key,
                            title=candidate.title,
                            is_relevant=analysis.is_relevant,
                            score=analysis.score,
                            reason=analysis.reason,
                            platform=analysis.platform,
                            budget=analysis.budget,
                            url=candidate.url,
                            urgency=analysis.urgency,
                            why_relevant=analysis.why_relevant,
                        )
                    )
                except Exception as exc:
                    stats.errors += 1
                    stats.error_details.append(f"{candidate.stable_key}: {exc}")
        return DigestPreviewResult(items, stats)

    async def run_digest_backfill(self, days: int) -> ProcessorStats:
        """Persistently process historical Freelancehunt digests."""
        stats = ProcessorStats()
        started_at = datetime.now(timezone.utc)
        try:
            try:
                emails = await self._provider.search_freelancehunt_emails(days)
            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(str(exc))
                return stats
            stats.emails_fetched = len(emails)
            return await self._run_emails(emails, stats, 0)
        finally:
            await self._append_scan_run("backfill", started_at, stats)

    async def run_debug(self, max_emails: int = 20) -> list[dict]:
        """Analyze without Telegram, repository, provider, or dedup mutations."""
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
                "date": email.received_at.strftime("%d.%m.%Y %H:%M")
                if email.received_at
                else "—",
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
                entry["passed"] = (
                    analysis.is_relevant and analysis.score >= self._min_score
                )
            except Exception as exc:
                logger.exception("run_debug: analyze failed for email_id=%s", email.id)
                entry["error"] = str(exc)
            results.append(entry)
        return results
