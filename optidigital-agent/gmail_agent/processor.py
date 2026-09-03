"""Main Gmail pipeline: classify, analyze, deduplicate, and notify Telegram."""

from __future__ import annotations

import json
import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from .dedup import EmailDedup
from .digest_parser import DigestJobCandidate, parse_freelancehunt_digest
from .email_analyzer import (
    JobAnalysis,
    analyze_candidate,
    analyze_email,
    detect_language,
    repair_analysis,
)
from .email_classifier import EmailType, classify_email
from .gmail_provider import EmailMessage, GmailProvider
from .live_status import (
    FreelancehuntLiveStatusChecker,
    LiveStatus,
    LiveStatusResult,
    retry_due,
)
from .project_identity import (
    freelancehunt_project_id,
    freelancehunt_project_stable_key,
    source_family,
)
from .quality_gate import (
    ANALYSIS_VERSION,
    SCORE_INVALID,
    SCORE_MISSING,
    SCORE_VALID,
    QualityStatus,
    apply_validation,
    is_proposal_ready,
    normalize_score_metadata,
    quality_errors,
    validate_analysis,
)
from .security import redact_security_event, redact_sensitive_content
from .sales_closer import (
    SalesCloserService,
    SalesProcessResult,
    safe_freelancehunt_url,
)
from .sales_storage import PostgresSalesRepository
from .storage import (
    GmailRepository,
    ProcessedItem,
    ScanRun,
    StoredGmailJob,
)
from .telegram_notifier import (
    send_job_card,
    send_live_status_card,
    send_sales_escalation_card,
    send_sales_fallback_card,
    send_sales_response_card,
)

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
    event_counts: dict[str, int] = field(default_factory=dict)
    mailbox_alias: str = ""
    max_detection_latency_seconds: float = 0.0
    live_status_non_actionable: int = 0
    live_status_unknown: int = 0
    live_status_diagnostics_sent: int = 0
    live_status_active: int = 0
    ai_calls_avoided: int = 0
    duplicate_source_pairs: dict[str, int] = field(default_factory=dict)
    max_publication_to_telegram_latency_seconds: float = 0.0
    quality_valid: int = 0
    quality_repaired: int = 0
    quality_manual_review: int = 0
    quality_non_executable: int = 0
    quality_failed: int = 0
    zero_score_blocked: int = 0
    missing_price_blocked: int = 0
    missing_proposal_blocked: int = 0
    invalid_evidence_blocked: int = 0
    repair_calls: int = 0
    repair_successes: int = 0
    proposal_versions_sent: int = 0

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
    live_status: str = ""
    biddable: bool | None = None


@dataclass(frozen=True)
class DigestPreviewResult:
    items: list[DigestPreviewItem]
    stats: ProcessorStats


@dataclass(frozen=True)
class QualityBackfillPreview:
    limit: int
    candidates: int
    zero_score: int
    missing_fit: int
    missing_price: int
    missing_timeline: int
    missing_proposal: int
    missing_or_invalid_evidence: int
    missing_score: int = 0
    invalid_score: int = 0
    actual_zero_score: int = 0
    missing_fit_state: int = 0
    invalid_fit_state: int = 0
    actual_zero_fit: int = 0


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
        live_status_checker: FreelancehuntLiveStatusChecker | None = None,
        live_status_retry_base_seconds: int = 60,
        live_status_max_retries: int = 3,
        sales_closer: SalesCloserService | None = None,
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
        # Production entry points pass the shared checker explicitly. Keeping
        # this injection optional preserves isolated legacy/unit callers.
        self._live_status_checker = live_status_checker
        self._live_status_retry_base_seconds = max(1, live_status_retry_base_seconds)
        self._live_status_max_retries = max(1, live_status_max_retries)
        self._sales_closer = sales_closer
        if (
            self._sales_closer is None
            and repository is not None
            and repository.__class__.__name__ == "PostgresGmailRepository"
        ):
            session_factory = getattr(repository, "session_factory", None)
            if session_factory is not None:
                self._sales_closer = SalesCloserService(
                    PostgresSalesRepository(session_factory),
                    openai_client=openai_client,
                )

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
            email_type == EmailType.PROJECT_DIGEST
            and "freelancehunt" in email.sender.casefold()
        )

    @staticmethod
    def _source_url(email: EmailMessage, email_type: EmailType) -> str:
        """Select only a normal public Freelancehunt URL for the event."""

        if email_type == EmailType.ACCOUNT_OR_SECURITY_EVENT:
            return ""
        preferred_markers = {
            EmailType.CLIENT_PRIVATE_MESSAGE: ("/messages", "/mailbox", "/dialog"),
            EmailType.WORKSPACE_OR_CONTRACT_EVENT: ("/workspace", "/safe"),
            EmailType.PROJECT_STATUS_EVENT: ("/project/", "/ua/project/", "/job/"),
            EmailType.PROJECT_SINGLE: ("/project/", "/ua/project/", "/job/", "/ua/job/"),
        }.get(email_type, ())
        safe_links: list[str] = []
        for link in email.links:
            safe_link = GmailJobProcessor._clean_freelancehunt_url(link)
            if safe_link:
                safe_links.append(safe_link)
        for marker in preferred_markers:
            for link in safe_links:
                if marker in link.casefold():
                    return link
        return safe_links[0] if safe_links else ""

    @staticmethod
    def _clean_freelancehunt_url(value: str) -> str:
        """Return a canonical public HTTPS URL or fail closed."""

        try:
            parsed = urlsplit(value or "")
            port = parsed.port
        except (TypeError, ValueError):
            return ""
        if (
            parsed.scheme.casefold() != "https"
            or (parsed.hostname or "").casefold()
            not in {"freelancehunt.com", "www.freelancehunt.com"}
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
        ):
            return ""
        return urlunsplit(("https", "freelancehunt.com", parsed.path or "/", "", ""))

    @staticmethod
    def _client_name_from_subject(subject: str) -> str:
        match = re.search(
            r"(?:нове\s+особисте\s+повідомлення\s+від|"
            r"новое\s+личное\s+сообщение\s+от|"
            r"new\s+private\s+message\s+from|"
            r"(?:nowa\s+)?wiadomo(?:ś|s)ć\s+prywatna\s+od)\s+(.+)$",
            subject or "",
            re.IGNORECASE,
        )
        return match.group(1).strip(" :—-\"'") if match else ""

    @staticmethod
    def _detection_latency(received_at: datetime | None) -> float:
        if received_at is None:
            return 0.0
        value = received_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds())

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
            event_type=job.event_type,
            source_email_id=job.source_email_id,
            full_description=job.full_description,
            description_completeness=job.description_completeness,
            language=job.language,
            category=job.category,
            skills=job.skills,
            deadline=job.deadline,
            bid_count=job.bid_count,
            client_name=job.client_name,
            client_profile_url=job.client_profile_url,
            client_context=job.client_context,
            project_id=job.project_id,
            thread_id=job.thread_id,
            service_lane=job.service_lane,
            executable=job.executable,
            fit_score=job.fit_score,
            win_probability_signal=job.win_probability_signal,
            scope_clarity=job.scope_clarity,
            estimated_effort=job.estimated_effort,
            delivery_risk=job.delivery_risk,
            client_payment_risk=job.client_payment_risk,
            project_mode=job.project_mode,
            project_mode_reason=job.project_mode_reason,
            recommended_price=job.recommended_price,
            realistic_timeline=job.realistic_timeline,
            selected_evidence=job.selected_evidence,
            evidence=job.analysis_evidence,
            proposal_draft=job.proposal_draft,
            needs_context=job.needs_context,
            next_action=job.next_action,
            received_at=job.received_at,
            sensitive_redacted=job.sensitive_redacted,
            source_mailbox_alias=job.source_mailbox_alias,
            live_status=job.live_status,
            live_status_checked_at=job.live_status_checked_at,
            live_status_evidence=job.live_status_evidence,
            biddable=job.biddable,
            live_status_retry_count=job.live_status_retry_count,
            live_status_last_error=job.live_status_last_error,
            qualified=job.qualified,
            tags=job.tags,
            budget_currency=job.budget_currency,
            discovery_source=job.discovery_source,
            discovery_sources=job.discovery_sources,
            source_publication_at=job.source_publication_at,
            source_feed_timestamp=job.source_feed_timestamp,
            feed_fetched_at=job.feed_fetched_at,
            first_seen_at=job.first_seen_at,
            telegram_sent_at=job.telegram_sent_at,
            publication_to_telegram_latency_seconds=(
                job.publication_to_telegram_latency_seconds
            ),
            analysis_quality_status=job.analysis_quality_status,
            quality_checked_at=job.quality_checked_at,
            quality_errors=job.quality_errors,
            quality_repair_count=job.quality_repair_count,
            proposal_quality_score=job.proposal_quality_score,
            evidence_case_id=job.evidence_case_id,
            analysis_version=job.analysis_version,
            proposal_version=job.proposal_version,
            proposal_content_sha256=job.proposal_content_sha256,
            money_terms_json=job.money_terms_json,
            timeline_terms_json=job.timeline_terms_json,
            original_analysis_snapshot=job.original_analysis_snapshot,
            quality_clarification_question=job.quality_clarification_question,
            model_output_json=job.model_output_json,
            score_valid=job.score_valid,
            score_raw=job.score_raw,
            score_state=job.score_state,
            fit_score_valid=job.fit_score_valid,
            fit_score_raw=job.fit_score_raw,
            fit_score_state=job.fit_score_state,
        )

    @staticmethod
    def _analysis_fields(analysis: JobAnalysis) -> dict[str, Any]:
        fields = {
            "event_type": analysis.event_type,
            "full_description": analysis.full_description,
            "description_completeness": analysis.description_completeness,
            "language": analysis.language,
            "category": analysis.category,
            "skills": analysis.skills,
            "deadline": analysis.deadline,
            "bid_count": analysis.bid_count,
            "client_name": analysis.client_name,
            "client_profile_url": analysis.client_profile_url,
            "client_context": analysis.client_context,
            "project_id": analysis.project_id,
            "thread_id": analysis.thread_id,
            "service_lane": analysis.service_lane,
            "executable": analysis.executable,
            "win_probability_signal": analysis.win_probability_signal,
            "scope_clarity": analysis.scope_clarity,
            "estimated_effort": analysis.estimated_effort,
            "delivery_risk": analysis.delivery_risk,
            "client_payment_risk": analysis.client_payment_risk,
            "project_mode": analysis.project_mode,
            "project_mode_reason": analysis.project_mode_reason,
            "recommended_price": analysis.recommended_price,
            "realistic_timeline": analysis.realistic_timeline,
            "selected_evidence": analysis.selected_evidence,
            "analysis_evidence": analysis.evidence,
            "proposal_draft": analysis.proposal_draft,
            "needs_context": analysis.needs_context,
            "next_action": analysis.next_action,
            "received_at": analysis.received_at,
            "sensitive_redacted": analysis.sensitive_redacted,
            "source_mailbox_alias": analysis.source_mailbox_alias,
            "live_status": analysis.live_status,
            "live_status_checked_at": analysis.live_status_checked_at,
            "live_status_evidence": analysis.live_status_evidence,
            "biddable": analysis.biddable,
            "live_status_retry_count": analysis.live_status_retry_count,
            "live_status_last_error": analysis.live_status_last_error,
            "qualified": analysis.qualified,
            "tags": analysis.tags,
            "budget_currency": analysis.budget_currency,
            "discovery_source": analysis.discovery_source,
            "discovery_sources": analysis.discovery_sources,
            "source_publication_at": analysis.source_publication_at,
            "source_feed_timestamp": analysis.source_feed_timestamp,
            "feed_fetched_at": analysis.feed_fetched_at,
            "first_seen_at": analysis.first_seen_at,
            "telegram_sent_at": analysis.telegram_sent_at,
            "publication_to_telegram_latency_seconds": (
                analysis.publication_to_telegram_latency_seconds
            ),
            "analysis_quality_status": analysis.analysis_quality_status,
            "quality_checked_at": analysis.quality_checked_at,
            "quality_errors": analysis.quality_errors,
            "quality_repair_count": analysis.quality_repair_count,
            "proposal_quality_score": analysis.proposal_quality_score,
            "evidence_case_id": analysis.evidence_case_id,
            "analysis_version": analysis.analysis_version,
            "proposal_version": analysis.proposal_version,
            "proposal_content_sha256": analysis.proposal_content_sha256,
            "money_terms_json": analysis.money_terms_json,
            "timeline_terms_json": analysis.timeline_terms_json,
            "original_analysis_snapshot": analysis.original_analysis_snapshot,
            "quality_clarification_question": analysis.quality_clarification_question,
            "model_output_json": analysis.model_output_json,
        }
        fields.update(GmailJobProcessor._score_storage_fields(analysis, "score"))
        fields.update(GmailJobProcessor._score_storage_fields(analysis, "fit_score"))
        return fields

    @staticmethod
    def _score_storage_fields(analysis: JobAnalysis, field_name: str) -> dict[str, Any]:
        metadata = normalize_score_metadata(
            getattr(analysis, field_name),
            raw=getattr(analysis, f"{field_name}_raw", None),
            explicit_state=getattr(analysis, f"{field_name}_state", ""),
            explicit_valid=getattr(analysis, f"{field_name}_valid", None),
            analysis_succeeded=analysis.analysis_succeeded,
        )
        return {
            field_name: metadata.value,
            f"{field_name}_valid": metadata.valid,
            f"{field_name}_raw": metadata.raw,
            f"{field_name}_state": metadata.state,
        }

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
            **GmailJobProcessor._score_storage_fields(analysis, "score"),
            **GmailJobProcessor._score_storage_fields(analysis, "fit_score"),
            reason=analysis.reason,
            budget=analysis.budget or candidate.budget or None,
            url=candidate.url or analysis.url or None,
            urgency=analysis.urgency,
            why_relevant=analysis.why_relevant,
            status=status,
            **{
                key: value
                for key, value in GmailJobProcessor._analysis_fields(analysis).items()
                if not key.startswith("score") and not key.startswith("fit_score")
            },
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
            item_type=(
                "rss_project"
                if candidate.event_type == EmailType.PROJECT_FEED.value
                else "digest_job"
            ),
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
            received_at=job.received_at,
            stable_key=job.stable_key,
            project_id=job.project_id,
            tags=job.tags,
            budget_currency=job.budget_currency,
            source_publication_at=job.source_publication_at,
            source_feed_timestamp=job.source_feed_timestamp,
            feed_fetched_at=job.feed_fetched_at,
            first_seen_at=job.first_seen_at,
            discovery_source=job.discovery_source,
            event_type=job.event_type,
            description_completeness=job.description_completeness,
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
                if job.event_type == EmailType.PROJECT_SINGLE.value
                else "digest_job"
                if job.event_type == EmailType.PROJECT_DIGEST.value
                else "rss_project"
                if job.event_type == EmailType.PROJECT_FEED.value
                else job.event_type
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
        *,
        stable_key: str | None = None,
    ) -> StoredGmailJob:
        return StoredGmailJob(
            stable_key=stable_key or email.id,
            source_email_id=email.id,
            platform=analysis.platform,
            title=analysis.title,
            **GmailJobProcessor._score_storage_fields(analysis, "score"),
            **GmailJobProcessor._score_storage_fields(analysis, "fit_score"),
            reason=analysis.reason,
            budget=analysis.budget or None,
            url=analysis.url or None,
            urgency=analysis.urgency,
            why_relevant=analysis.why_relevant,
            status=status,
            **{
                key: value
                for key, value in GmailJobProcessor._analysis_fields(analysis).items()
                if not key.startswith("score") and not key.startswith("fit_score")
            },
        )

    @staticmethod
    def _processed_single_item(
        email: EmailMessage,
        analysis: JobAnalysis,
        decision: str,
        *,
        stable_key: str | None = None,
    ) -> ProcessedItem:
        return ProcessedItem(
            stable_key=stable_key or email.id,
            source_email_id=email.id,
            platform=analysis.platform,
            item_type=(
                "single_job"
                if analysis.event_type == EmailType.PROJECT_SINGLE.value
                else analysis.event_type
            ),
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
            platform=(
                "Freelancehunt"
                if "freelancehunt" in email.sender.casefold()
                else "Work.ua" if "work.ua" in email.sender.casefold() else ""
            ),
            item_type=(
                "informational_newsletter"
                if email_type == EmailType.MARKETING
                and "work.ua" in email.sender.casefold()
                else email_type.value
            ),
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

    @staticmethod
    def _merge_discovery_sources(*values: str) -> str:
        sources: list[str] = []
        for value in values:
            for source in str(value or "").split(","):
                normalized = source.strip()
                if normalized and normalized not in sources:
                    sources.append(normalized)
        return ",".join(sources)

    async def _record_duplicate(
        self,
        stable_key: str,
        incoming_source: str,
        stats: ProcessorStats,
    ) -> None:
        stats.duplicates_skipped += 1
        stats.ai_calls_avoided += 1
        if self._repository is None:
            return
        previous = await self._repository.get_processed(stable_key)
        previous_source = source_family(previous.item_type if previous else "unknown")
        incoming_family = source_family(incoming_source)
        pair = f"{previous_source}->{incoming_family}"
        stats.duplicate_source_pairs[pair] = (
            stats.duplicate_source_pairs.get(pair, 0) + 1
        )
        job = await self._repository.get_job(stable_key)
        if job is not None:
            sources = self._merge_discovery_sources(
                job.discovery_sources or job.discovery_source,
                incoming_family,
            )
            await self._repository.update_job_fields(
                stable_key, {"discovery_sources": sources}
            )

    async def _record_source_reuse(
        self,
        job: StoredGmailJob,
        incoming_source: str,
        stats: ProcessorStats,
    ) -> StoredGmailJob:
        previous_family = source_family(job.discovery_source)
        incoming_family = source_family(incoming_source)
        if previous_family == incoming_family:
            return job
        pair = f"{previous_family}->{incoming_family}"
        stats.duplicate_source_pairs[pair] = (
            stats.duplicate_source_pairs.get(pair, 0) + 1
        )
        stats.ai_calls_avoided += 1
        sources = self._merge_discovery_sources(
            job.discovery_sources or previous_family,
            incoming_family,
        )
        if self._repository is None:
            return job
        return (
            await self._repository.update_job_fields(
                job.stable_key, {"discovery_sources": sources}
            )
            or job
        )

    @staticmethod
    def _is_guarded_project(event_type: str, platform: str, url: str) -> bool:
        return (
            event_type
            in {
                EmailType.PROJECT_SINGLE.value,
                EmailType.PROJECT_DIGEST.value,
                EmailType.PROJECT_FEED.value,
            }
            and "freelancehunt" in (platform or "").casefold()
            and bool(url)
        )

    @staticmethod
    def _quality_required(analysis: JobAnalysis) -> bool:
        return (
            GmailJobProcessor._is_guarded_project(
                analysis.event_type, analysis.platform, analysis.url
            )
            and analysis.live_status == LiveStatus.ACTIVE_BIDDABLE.value
            and analysis.biddable is True
        )

    @staticmethod
    def _quality_snapshot(analysis: JobAnalysis) -> str:
        safe = asdict(analysis)
        # The source task is already stored in full_description.  The snapshot
        # preserves the previous model package for an auditable backfill while
        # remaining internal to PostgreSQL.
        return json.dumps(safe, ensure_ascii=False, default=str, sort_keys=True)

    @staticmethod
    def _record_quality_errors(stats: ProcessorStats, errors: list[str]) -> None:
        if any(code in errors for code in (
            "score_missing",
            "score_invalid",
            "score_provider_failed",
            "score_zero_not_proposal_ready",
            "fit_score_missing",
            "fit_score_invalid",
            "fit_score_provider_failed",
            "fit_score_zero_not_proposal_ready",
        )):
            stats.zero_score_blocked += 1
        if "recommended_price_missing_amount_or_currency" in errors:
            stats.missing_price_blocked += 1
        if "missing_proposal" in errors:
            stats.missing_proposal_blocked += 1
        if any(code in errors for code in (
            "invalid_evidence_case_id",
            "evidence_text_not_registry_exact",
        )):
            stats.invalid_evidence_blocked += 1

    @staticmethod
    def _record_quality_status(stats: ProcessorStats, status: str) -> None:
        if status == QualityStatus.VALID.value:
            stats.quality_valid += 1
        elif status == QualityStatus.REPAIRED.value:
            stats.quality_repaired += 1
        elif status == QualityStatus.MANUAL_REVIEW.value:
            stats.quality_manual_review += 1
        elif status == QualityStatus.NON_EXECUTABLE.value:
            stats.quality_non_executable += 1
        elif status == QualityStatus.FAILED.value:
            stats.quality_failed += 1

    async def _validate_and_repair_quality(
        self,
        analysis: JobAnalysis,
        stats: ProcessorStats,
        *,
        allow_repair: bool = True,
    ) -> tuple[JobAnalysis, bool]:
        """Return (analysis, provider_failed); execute at most one repair call."""

        initial = validate_analysis(analysis)
        initial_errors = list(initial.errors)
        self._record_quality_errors(stats, initial_errors)
        if initial.proposal_ready or initial.status == QualityStatus.NON_EXECUTABLE.value:
            apply_validation(analysis, initial)
            self._record_quality_status(stats, initial.status)
            return analysis, False

        if not allow_repair or not analysis.analysis_succeeded:
            apply_validation(analysis, initial)
            self._record_quality_status(stats, initial.status)
            stats.ai_calls_avoided += 1
            return analysis, not analysis.analysis_succeeded

        original_snapshot = (
            analysis.original_analysis_snapshot or self._quality_snapshot(analysis)
        )
        stats.repair_calls += 1
        repaired = await repair_analysis(
            analysis,
            initial_errors,
            client=self._openai_client,
        )
        repaired.original_analysis_snapshot = original_snapshot
        if not repaired.analysis_succeeded:
            failed = validate_analysis(repaired, repaired=True)
            apply_validation(repaired, failed, repair_count=1)
            self._record_quality_status(stats, QualityStatus.FAILED.value)
            return repaired, True

        second = validate_analysis(repaired, repaired=True)
        self._record_quality_errors(stats, list(second.errors))
        apply_validation(repaired, second, repair_count=1)
        self._record_quality_status(stats, second.status)
        if second.proposal_ready:
            stats.repair_successes += 1
        else:
            # The deterministic terminal check prevents any further model loop
            # or downstream proposal-generation call.
            stats.ai_calls_avoided += 1
        return repaired, False

    @staticmethod
    def _proposal_version_key(analysis: JobAnalysis) -> str:
        digest = hashlib.sha256(analysis.email_id.encode("utf-8")).hexdigest()
        return f"proposal-version:{digest}:{analysis.proposal_version}"

    @staticmethod
    def _apply_live_result(
        analysis: JobAnalysis,
        result: LiveStatusResult,
        retry_count: int,
    ) -> JobAnalysis:
        analysis.live_status = result.status.value
        analysis.live_status_checked_at = result.checked_at
        analysis.live_status_evidence = result.evidence
        analysis.biddable = result.biddable
        analysis.live_status_retry_count = retry_count
        analysis.live_status_last_error = result.last_error
        if result.status != LiveStatus.ACTIVE_BIDDABLE:
            analysis.is_relevant = False
            analysis.qualified = False
            analysis.recommended_price = ""
            analysis.realistic_timeline = ""
            analysis.money_terms_json = ""
            analysis.timeline_terms_json = ""
            analysis.proposal_draft = ""
            analysis.proposal_content_sha256 = ""
            analysis.proposal_version = ""
            analysis.next_action = (
                "Дочекатися автоматичної повторної перевірки або виконати read-only /recheck_live."
                if (
                    result.status == LiveStatus.LIVE_STATUS_UNKNOWN
                    and retry_count < 3
                )
                else "Виконати лише read-only /recheck_live; нічого не надсилати."
                if result.status == LiveStatus.LIVE_STATUS_UNKNOWN
                else "Нічого не надсилати."
            )
            analysis.analysis_quality_status = QualityStatus.FAILED.value
            analysis.quality_checked_at = result.checked_at
            analysis.quality_errors = json.dumps(
                ["live_status_not_active_biddable"], ensure_ascii=False
            )
            analysis.proposal_quality_score = 0.0
            analysis.analysis_version = analysis.analysis_version or ANALYSIS_VERSION
        return analysis

    @staticmethod
    def _status_only_analysis(
        *,
        stable_key: str,
        source_email_id: str,
        title: str,
        description: str,
        url: str,
        event_type: str,
        platform: str,
        project_id: str,
        received_at: datetime | None,
        mailbox_alias: str,
        result: LiveStatusResult,
        retry_count: int,
        tags: str = "",
        budget_currency: str = "",
        discovery_source: str = "",
        source_publication_at: datetime | None = None,
        source_feed_timestamp: datetime | None = None,
        feed_fetched_at: datetime | None = None,
        first_seen_at: datetime | None = None,
        description_completeness: str = "PARTIAL",
    ) -> JobAnalysis:
        analysis = JobAnalysis(
            email_id=stable_key,
            is_relevant=False,
            title=title,
            platform=platform or "Freelancehunt",
            score=None,
            reason=result.evidence,
            budget="",
            url=url,
            urgency="low",
            why_relevant="",
            event_type=event_type,
            source_email_id=source_email_id,
            full_description=description,
            description_completeness=description_completeness,
            project_id=project_id,
            received_at=received_at,
            source_mailbox_alias=mailbox_alias,
            tags=tags,
            budget_currency=budget_currency,
            discovery_source=discovery_source,
            discovery_sources=discovery_source,
            source_publication_at=source_publication_at,
            source_feed_timestamp=source_feed_timestamp,
            feed_fetched_at=feed_fetched_at,
            first_seen_at=first_seen_at,
        )
        return GmailJobProcessor._apply_live_result(analysis, result, retry_count)

    async def _check_live_status(
        self,
        url: str,
        previous: StoredGmailJob | None = None,
        *,
        force: bool = False,
    ) -> tuple[LiveStatusResult, int] | None:
        if self._live_status_checker is None:
            return None
        previous_count = previous.live_status_retry_count if previous else 0
        if (
            not force
            and previous is not None
            and previous.live_status == LiveStatus.LIVE_STATUS_UNKNOWN.value
            and previous_count >= self._live_status_max_retries
        ):
            return (
                LiveStatusResult(
                    status=LiveStatus.LIVE_STATUS_UNKNOWN,
                    checked_at=previous.live_status_checked_at or datetime.now(timezone.utc),
                    evidence=previous.live_status_evidence or "LIVE STATUS NOT VERIFIED",
                    biddable=False,
                    last_error=previous.live_status_last_error or "retry limit exhausted",
                ),
                previous_count,
            )
        if (
            not force
            and previous is not None
            and previous.live_status == LiveStatus.LIVE_STATUS_UNKNOWN.value
            and not retry_due(
                previous.live_status_checked_at,
                previous_count,
                base_seconds=self._live_status_retry_base_seconds,
                max_retries=self._live_status_max_retries,
            )
        ):
            return None
        result = await self._live_status_checker.check(url)
        if (
            result.status == LiveStatus.ACTIVE_BIDDABLE
            and result.biddable is not True
        ):
            result = LiveStatusResult(
                status=LiveStatus.LIVE_STATUS_UNKNOWN,
                checked_at=result.checked_at,
                evidence="LIVE STATUS NOT VERIFIED",
                biddable=False,
                last_error="inconsistent ACTIVE_BIDDABLE result without biddable=true",
            )
        retry_count = (
            previous_count + 1
            if result.status == LiveStatus.LIVE_STATUS_UNKNOWN
            else previous_count
        )
        return result, retry_count

    async def generate_validate_and_persist_proposal(
        self,
        stable_key: str,
        *,
        rewrite: bool = False,
    ):
        """Use the current quality-gate contract for manual regeneration."""

        if self._repository is None:
            raise RuntimeError("proposal generation requires PostgreSQL repository")
        job = await self._repository.get_job(stable_key)
        if job is None:
            raise LookupError(stable_key)

        from .proposal_service import generate_validate_and_persist_proposal
        from .quality_gate import approved_evidence_text, proposal_body
        from .reply_generator import generate_reply

        async def refresh_live(analysis: JobAnalysis) -> JobAnalysis | None:
            checked = await self._check_live_status(job.url or "", job, force=True)
            if checked is None:
                return None
            result, retry_count = checked
            snapshot = analysis.original_analysis_snapshot or self._quality_snapshot(analysis)
            self._apply_live_result(analysis, result, retry_count)
            if result.status != LiveStatus.ACTIVE_BIDDABLE:
                status, _settled = self._nonactive_state(result, retry_count)
                await self._repository.apply_backfill_live_result(
                    stable_key,
                    snapshot,
                    {"status": status, **self._analysis_fields(analysis)},
                )
                return None
            analysis.is_relevant = True
            analysis.biddable = True
            await self._repository.update_job_fields(
                stable_key,
                {
                    "live_status": analysis.live_status,
                    "live_status_checked_at": analysis.live_status_checked_at,
                    "live_status_evidence": analysis.live_status_evidence,
                    "biddable": True,
                    "live_status_retry_count": retry_count,
                    "live_status_last_error": analysis.live_status_last_error,
                },
            )
            return analysis

        async def generate(
            analysis: JobAnalysis,
            errors: tuple[str, ...],
            original_candidate: str,
        ) -> str:
            return await generate_reply(
                title=analysis.title,
                description=analysis.full_description,
                platform=analysis.platform,
                budget=analysis.budget,
                url=analysis.url,
                client=self._openai_client,
                language=analysis.language,
                client_context=analysis.client_context,
                # Evidence and commercial clauses are deliberately not model-owned.
                selected_evidence="",
                recommended_price="",
                recommended_timeline="",
                existing_proposal=(
                    proposal_body(analysis.proposal_draft) if rewrite else ""
                ),
                rewrite=True,
                validation_errors=errors,
                original_candidate=original_candidate,
                repair_context=(
                    {
                        "model_output_json": analysis.model_output_json,
                        "normalized_analysis": asdict(analysis),
                        "approved_evidence": approved_evidence_text(
                            analysis.evidence_case_id, analysis.language
                        ),
                    }
                    if errors
                    else None
                ),
            )

        async def persist(analysis: JobAnalysis, status: str) -> None:
            fields = {
                **self._analysis_fields(analysis),
                "status": status,
                "qualified": is_proposal_ready(analysis),
            }
            stored = await self._repository.update_job_fields(stable_key, fields)
            if stored is None:
                raise RuntimeError("proposal source row disappeared")

        # Resolve the registry text before the model call so the selected ID,
        # not model prose, owns the final proof point.
        analysis = self._analysis_from_job(job)
        analysis.selected_evidence = approved_evidence_text(
            analysis.evidence_case_id, analysis.language
        )
        return await generate_validate_and_persist_proposal(
            analysis,
            refresh_live_status=refresh_live,
            generate_candidate=generate,
            persist=persist,
        )

    async def recheck_quality_and_deliver(
        self,
        stable_key: str,
        stats: ProcessorStats | None = None,
    ) -> tuple[JobAnalysis, bool]:
        """One live refresh, one full reanalysis, then unified delivery."""

        if self._repository is None:
            raise RuntimeError("quality recheck requires PostgreSQL repository")
        stats = stats or ProcessorStats()
        job = await self._repository.get_job(stable_key)
        if job is None:
            raise LookupError(stable_key)
        original = self._analysis_from_job(job)
        snapshot = original.original_analysis_snapshot or self._quality_snapshot(original)
        checked = await self._check_live_status(job.url or "", job, force=True)
        if checked is None:
            return original, False
        live_result, retry_count = checked
        self._apply_live_result(original, live_result, retry_count)
        if live_result.status != LiveStatus.ACTIVE_BIDDABLE:
            status, _settled = self._nonactive_state(live_result, retry_count)
            stored = await self._repository.apply_backfill_live_result(
                stable_key,
                snapshot,
                {"status": status, **self._analysis_fields(original)},
            )
            return (self._analysis_from_job(stored) if stored else original), False

        errors = tuple(quality_errors(original)) or (
            "admin_requested_bounded_quality_recheck",
        )
        reanalyzed = await repair_analysis(
            original,
            errors,
            client=self._openai_client,
        )
        reanalyzed.original_analysis_snapshot = snapshot
        self._apply_live_result(reanalyzed, live_result, retry_count)
        if not reanalyzed.analysis_succeeded:
            validation = validate_analysis(reanalyzed, repaired=True)
            apply_validation(reanalyzed, validation, repair_count=1)
            stored = await self._repository.update_job_fields(
                stable_key,
                {
                    "status": "quality_retryable",
                    **self._analysis_fields(reanalyzed),
                    "qualified": False,
                },
            )
            return (self._analysis_from_job(stored) if stored else reanalyzed), False

        stats.ai_analyzed += 1
        validation = validate_analysis(reanalyzed, repaired=True)
        self._record_quality_errors(stats, list(validation.errors))
        apply_validation(reanalyzed, validation, repair_count=1)
        self._record_quality_status(stats, validation.status)
        ready = is_proposal_ready(reanalyzed)
        reanalyzed.qualified = ready
        status = (
            "queued"
            if ready
            else "quality_non_executable"
            if validation.status == QualityStatus.NON_EXECUTABLE.value
            else "quality_review_pending"
        )
        stored = await self._repository.update_job_fields(
            stable_key,
            {"status": status, **self._analysis_fields(reanalyzed)},
        )
        if stored is None:
            raise RuntimeError("quality recheck row disappeared")
        if validation.status == QualityStatus.NON_EXECUTABLE.value:
            return reanalyzed, False
        delivered = await self.deliver_validated_proposal_version(
            self._candidate_from_job(stored),
            stored,
            stats,
            live_status_already_checked=True,
        )
        return reanalyzed, delivered

    def _nonactive_state(
        self, result: LiveStatusResult, retry_count: int
    ) -> tuple[str, bool]:
        """Return durable internal state and whether automatic work is settled."""

        if result.status != LiveStatus.LIVE_STATUS_UNKNOWN:
            return "live_status_terminal", True
        if retry_count >= self._live_status_max_retries:
            return "live_status_unknown_exhausted", True
        return "live_status_pending", False

    @staticmethod
    def _active_check_is_fresh(job: StoredGmailJob, seconds: int = 60) -> bool:
        checked_at = job.live_status_checked_at
        if (
            job.live_status != LiveStatus.ACTIVE_BIDDABLE.value
            or job.biddable is not True
            or checked_at is None
        ):
            return False
        value = checked_at
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - value <= timedelta(seconds=seconds)

    async def _send_live_status_notice_once(
        self,
        analysis: JobAnalysis,
        stats: ProcessorStats,
    ) -> bool:
        if self._repository is None:
            return False
        digest = hashlib.sha256(analysis.email_id.encode("utf-8")).hexdigest()
        notice_key = f"live-status-notice:{digest}"
        if await self._repository.is_processed(notice_key):
            return True
        sent = await send_live_status_card(self._bot, self._chat_id, analysis)
        if sent:
            await self._repository.upsert_processed(
                ProcessedItem(
                    stable_key=notice_key,
                    source_email_id=analysis.source_email_id or analysis.email_id,
                    platform=analysis.platform,
                    item_type="live_status_diagnostic",
                    title=analysis.title,
                    url=analysis.url,
                    decision=analysis.live_status,
                    score=None,
                )
            )
            stats.live_status_diagnostics_sent += 1
        return sent

    async def _drain_live_status_notices(self, stats: ProcessorStats) -> None:
        """Retry diagnostics independently from processed email/project keys."""

        if self._repository is None:
            return
        jobs = await self._repository.list_jobs_by_status(
            ["live_status_notice_pending"], limit=100
        )
        for job in jobs:
            analysis = self._analysis_from_job(job)
            if not await self._send_live_status_notice_once(analysis, stats):
                continue
            if job.live_status == LiveStatus.LIVE_STATUS_UNKNOWN.value:
                logical_status = (
                    "live_status_unknown_exhausted"
                    if job.live_status_retry_count >= self._live_status_max_retries
                    else "live_status_pending"
                )
            else:
                logical_status = "live_status_terminal"
            await self._repository.update_job_status(job.stable_key, logical_status)

    @staticmethod
    def _live_status_decision(status: LiveStatus) -> str:
        return f"live_status_{status.value.casefold()}"

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
                    "event_type": analysis.event_type,
                    "source_email_id": analysis.source_email_id,
                    "full_description": analysis.full_description,
                    "description_completeness": analysis.description_completeness,
                    "language": analysis.language,
                    "client_context": analysis.client_context,
                    "selected_evidence": analysis.selected_evidence,
                    "recommended_price": analysis.recommended_price,
                    "realistic_timeline": analysis.realistic_timeline,
                    "proposal_draft": analysis.proposal_draft,
                    "needs_context": analysis.needs_context,
                    "next_action": analysis.next_action,
                    "live_status": analysis.live_status,
                    "live_status_checked_at": (
                        analysis.live_status_checked_at.isoformat()
                        if analysis.live_status_checked_at
                        else None
                    ),
                    "live_status_evidence": analysis.live_status_evidence,
                    "biddable": analysis.biddable,
                    "live_status_retry_count": analysis.live_status_retry_count,
                    "live_status_last_error": analysis.live_status_last_error,
                    "qualified": analysis.qualified,
                },
                path=self._job_store_path,
            )
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(
                f"{analysis.email_id}: job store save failed: {exc}"
            )
            logger.exception("Failed to persist Gmail job analysis")

    async def deliver_validated_proposal_version(
        self,
        candidate: DigestJobCandidate,
        job: StoredGmailJob,
        stats: ProcessorStats,
        *,
        live_status_already_checked: bool = False,
    ) -> bool:
        """The one version-aware path for every proposal-ready Telegram delivery."""
        assert self._repository is not None
        analysis = self._analysis_from_job(job)
        if (
            not live_status_already_checked
            and self._live_status_checker is not None
            and self._is_guarded_project(job.event_type, job.platform, job.url or "")
        ):
            if not self._active_check_is_fresh(job):
                checked = await self._check_live_status(job.url or "", job)
                if checked is None:
                    return False
                result, retry_count = checked
                analysis = self._apply_live_result(analysis, result, retry_count)
                settled = False
                if result.status == LiveStatus.ACTIVE_BIDDABLE:
                    analysis.is_relevant = True
                    analysis.qualified = True
                    stats.live_status_active += 1
                    status = job.status
                else:
                    status, settled = self._nonactive_state(result, retry_count)
                    if result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                        stats.live_status_unknown += 1
                    else:
                        stats.live_status_non_actionable += 1
                job = await self._repository.save_job(
                    replace(job, status=status, **self._analysis_fields(analysis))
                )
                if result.status != LiveStatus.ACTIVE_BIDDABLE:
                    notice_sent = await self._send_live_status_notice_once(analysis, stats)
                    if not notice_sent:
                        await self._repository.update_job_status(
                            job.stable_key, "live_status_notice_pending"
                        )
                    if settled:
                        await self._repository.upsert_processed(
                            self._processed_job_item(
                                job,
                                (
                                    "live_status_unknown_exhausted"
                                    if result.status == LiveStatus.LIVE_STATUS_UNKNOWN
                                    else self._live_status_decision(result.status)
                                ),
                            )
                        )
                    return settled

        analysis = self._analysis_from_job(job)
        quality_required = self._quality_required(analysis)
        manual_review = (
            analysis.analysis_quality_status == QualityStatus.MANUAL_REVIEW.value
        )
        sales_tracking_failed = False
        if self._sales_closer is not None and (
            is_proposal_ready(analysis) or manual_review
        ):
            try:
                await self._sales_closer.ensure_from_validated_job(job)
            except Exception as exc:
                stats.errors += 1
                stats.error_details.append(
                    f"{job.stable_key}: sales opportunity persistence failed: {exc}"
                )
                logger.exception(
                    "Sales opportunity persistence failed for %s", job.stable_key
                )
                sales_tracking_failed = True
                analysis.sales_tracking_unavailable = True
        if quality_required and not is_proposal_ready(analysis):
            if not manual_review:
                # Legacy/invalid persisted rows cannot escape via restart queue.
                errors = quality_errors(analysis) or ["quality_state_not_proposal_ready"]
                await self._repository.update_job_fields(
                    job.stable_key,
                    {
                        "status": "quality_manual_review",
                        "analysis_quality_status": QualityStatus.MANUAL_REVIEW.value,
                        "quality_checked_at": datetime.now(timezone.utc),
                        "quality_errors": json.dumps(errors, ensure_ascii=False),
                        "qualified": False,
                        "recommended_price": "",
                        "realistic_timeline": "",
                        "money_terms_json": "",
                        "timeline_terms_json": "",
                        "proposal_draft": "",
                        "proposal_content_sha256": "",
                        "proposal_version": "",
                    },
                )
                return False

        if quality_required and is_proposal_ready(analysis):
            version_key = self._proposal_version_key(analysis)
            if await self._repository.is_processed(version_key):
                await self._repository.update_job_status(
                    job.stable_key,
                    "sales_tracking_pending" if sales_tracking_failed else "sent",
                )
                stats.duplicates_skipped += 1
                stats.ai_calls_avoided += 1
                return False

        claimed = await self._repository.claim_job(candidate.stable_key)
        if not claimed:
            # Another worker owns it, or it became terminal after our read.
            if await self._repository.is_processed(candidate.stable_key):
                await self._record_duplicate(
                    candidate.stable_key,
                    candidate.discovery_source or job.discovery_source,
                    stats,
                )
            return False

        analysis = self._analysis_from_job(job)
        analysis.sales_tracking_unavailable = sales_tracking_failed
        send_started_at = datetime.now(timezone.utc)
        analysis.telegram_sent_at = send_started_at
        if analysis.source_publication_at is not None:
            published = analysis.source_publication_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            analysis.publication_to_telegram_latency_seconds = max(
                0.0, (send_started_at - published).total_seconds()
            )
        try:
            sent_ok = await send_job_card(self._bot, self._chat_id, analysis)
        except Exception as exc:
            await self._repository.update_job_status(
                candidate.stable_key,
                "quality_review_pending" if manual_review else "send_failed",
            )
            stats.errors += 1
            stats.error_details.append(f"{candidate.stable_key}: {exc}")
            logger.exception("Digest Telegram send raised for %s", candidate.stable_key)
            return True

        if not sent_ok:
            await self._repository.update_job_status(
                candidate.stable_key,
                "quality_review_pending" if manual_review else "send_failed",
            )
            stats.errors += 1
            stats.error_details.append(
                f"{candidate.stable_key}: Telegram send failed"
            )
            return True

        telegram_sent_at = datetime.now(timezone.utc)
        latency = analysis.publication_to_telegram_latency_seconds
        if analysis.source_publication_at is not None:
            published = analysis.source_publication_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            latency = max(0.0, (telegram_sent_at - published).total_seconds())
        final_status = (
            "quality_manual_review"
            if manual_review
            else "sales_tracking_pending"
            if sales_tracking_failed
            else "sent"
        )
        await self._repository.update_job_fields(
            candidate.stable_key,
            {
                "status": final_status,
                "telegram_sent_at": telegram_sent_at,
                "publication_to_telegram_latency_seconds": latency,
            },
        )
        await self._repository.upsert_processed(
            self._processed_job_item(job, final_status)
        )
        if quality_required and not manual_review:
            await self._repository.upsert_processed(
                ProcessedItem(
                    stable_key=self._proposal_version_key(analysis),
                    source_email_id=analysis.source_email_id or analysis.email_id,
                    platform=analysis.platform,
                    item_type="proposal_version",
                    title=analysis.title,
                    url=analysis.url,
                    decision="sent",
                    score=analysis.score,
                )
            )
            stats.proposal_versions_sent += 1
        stats.sent += 1
        stats.sent_analyses.append(analysis)
        if latency is not None:
            stats.max_publication_to_telegram_latency_seconds = max(
                stats.max_publication_to_telegram_latency_seconds,
                latency,
            )
        return True

    async def _send_stored_job(
        self,
        candidate: DigestJobCandidate,
        job: StoredGmailJob,
        stats: ProcessorStats,
        *,
        live_status_already_checked: bool = False,
    ) -> bool:
        """Compatibility alias; new code must use the public delivery contract."""

        return await self.deliver_validated_proposal_version(
            candidate,
            job,
            stats,
            live_status_already_checked=live_status_already_checked,
        )

    async def deliver_validated_proposal_text_version(
        self,
        stable_key: str,
        send_text: Any,
        *,
        live_status_already_checked: bool = False,
    ) -> bool:
        """Explicit repeatable retrieval of one already validated exact version."""

        if self._repository is None:
            raise RuntimeError("proposal delivery requires PostgreSQL repository")
        job = await self._repository.get_job(stable_key)
        if job is None:
            return False
        analysis = self._analysis_from_job(job)
        if not live_status_already_checked:
            checked = await self._check_live_status(job.url or "", job, force=True)
            if checked is None:
                return False
            result, retry_count = checked
            snapshot = analysis.original_analysis_snapshot or self._quality_snapshot(analysis)
            self._apply_live_result(analysis, result, retry_count)
            if result.status != LiveStatus.ACTIVE_BIDDABLE:
                status, _settled = self._nonactive_state(result, retry_count)
                await self._repository.apply_backfill_live_result(
                    stable_key,
                    snapshot,
                    {"status": status, **self._analysis_fields(analysis)},
                )
                return False
            await self._repository.update_job_fields(
                stable_key, self._analysis_fields(analysis)
            )
        if not is_proposal_ready(analysis):
            return False
        if self._sales_closer is not None:
            try:
                await self._sales_closer.ensure_from_validated_job(job)
            except Exception:
                logger.exception(
                    "Sales opportunity persistence failed during explicit retrieval: %s",
                    stable_key,
                )
                analysis.sales_tracking_unavailable = True

        digest = hashlib.sha256(stable_key.encode("utf-8")).hexdigest()
        sent = await send_text(analysis)
        if not sent:
            return False
        # Manual retrieval is an explicit owner request, not an unsolicited
        # delivery. Every successful repeat is recorded as its own event and
        # never consumes the proposal-version card dedup key.
        await self._repository.upsert_processed(
            ProcessedItem(
                stable_key=(
                    f"proposal-retrieval:{digest}:{analysis.proposal_version}:"
                    f"{uuid4().hex}"
                ),
                source_email_id=analysis.source_email_id or stable_key,
                platform=analysis.platform,
                item_type="proposal_retrieval",
                title=analysis.title,
                url=analysis.url,
                decision="sent",
                score=analysis.score,
            )
        )
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
                attempted = await self.deliver_validated_proposal_version(
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
        email: EmailMessage | None,
        stats: ProcessorStats,
        cards_sent_this_scan: int,
        *,
        candidates_override: list[DigestJobCandidate] | None = None,
    ) -> int:
        """Process one digest and return the updated per-scan card count."""
        assert self._repository is not None
        if candidates_override is None:
            assert email is not None
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
        else:
            candidates = candidates_override

        stats.candidates_found += len(candidates)
        all_children_handled = True

        # Resolve every due public URL as one controlled concurrent batch. The
        # later per-child logic consumes the checker's per-scan cache, so no
        # database transaction is held while HTTP/Chromium is running.
        if self._live_status_checker is not None:
            due_urls: list[str] = []
            for candidate in candidates:
                if await self._repository.is_processed(candidate.stable_key):
                    continue
                previous = await self._repository.get_job(candidate.stable_key)
                if previous is None:
                    due_urls.append(candidate.url)
                elif previous.status == "live_status_pending" and retry_due(
                    previous.live_status_checked_at,
                    previous.live_status_retry_count,
                    base_seconds=self._live_status_retry_base_seconds,
                    max_retries=self._live_status_max_retries,
                ):
                    due_urls.append(candidate.url)
            if due_urls:
                if hasattr(self._live_status_checker, "batch_check"):
                    await self._live_status_checker.batch_check(due_urls)

        for candidate in candidates:
            try:
                active_checked_this_call = False
                if await self._repository.is_processed(candidate.stable_key):
                    await self._record_duplicate(
                        candidate.stable_key,
                        candidate.discovery_source,
                        stats,
                    )
                    continue

                job = await self._repository.get_job(candidate.stable_key)
                if job is not None:
                    job = await self._record_source_reuse(
                        job, candidate.discovery_source, stats
                    )
                if job is None or job.status in {"live_status_pending", "quality_retryable"}:
                    live_result: LiveStatusResult | None = None
                    live_retry_count = 0
                    if self._live_status_checker is not None:
                        checked = await self._check_live_status(candidate.url, job)
                        if checked is None:
                            all_children_handled = False
                            continue
                        live_result, live_retry_count = checked
                        if live_result.status != LiveStatus.ACTIVE_BIDDABLE:
                            analysis = self._status_only_analysis(
                                stable_key=candidate.stable_key,
                                source_email_id=candidate.source_email_id,
                                title=candidate.title,
                                description=candidate.description,
                                url=candidate.url,
                                event_type=candidate.event_type,
                                platform=candidate.platform,
                                project_id=candidate.project_id,
                                received_at=candidate.received_at,
                                mailbox_alias=stats.mailbox_alias,
                                result=live_result,
                                retry_count=live_retry_count,
                                tags=candidate.tags,
                                budget_currency=candidate.budget_currency,
                                discovery_source=candidate.discovery_source,
                                source_publication_at=candidate.source_publication_at,
                                source_feed_timestamp=candidate.source_feed_timestamp,
                                feed_fetched_at=candidate.feed_fetched_at,
                                first_seen_at=candidate.first_seen_at,
                                description_completeness=(
                                    candidate.description_completeness
                                ),
                            )
                            stats.ai_calls_avoided += 1
                            status, settled = self._nonactive_state(
                                live_result, live_retry_count
                            )
                            if live_result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                                stats.live_status_unknown += 1
                            else:
                                stats.live_status_non_actionable += 1
                            job = await self._repository.save_job(
                                self._stored_job(
                                    candidate,
                                    analysis,
                                    status=status,
                                )
                            )
                            notice_sent = await self._send_live_status_notice_once(
                                analysis, stats
                            )
                            if not notice_sent:
                                await self._repository.update_job_status(
                                    job.stable_key, "live_status_notice_pending"
                                )
                            if settled:
                                await self._repository.upsert_processed(
                                    self._processed_item(
                                        candidate,
                                        (
                                            "live_status_unknown_exhausted"
                                            if live_result.status
                                            == LiveStatus.LIVE_STATUS_UNKNOWN
                                            else self._live_status_decision(
                                                live_result.status
                                            )
                                        ),
                                        None,
                                    )
                                )
                            else:
                                all_children_handled = False
                            continue

                        stats.live_status_active += 1
                        active_checked_this_call = True

                    analysis = await analyze_candidate(
                        candidate, client=self._openai_client
                    )
                    analysis.source_mailbox_alias = stats.mailbox_alias
                    if live_result is not None:
                        self._apply_live_result(
                            analysis, live_result, live_retry_count
                        )
                    if analysis.analysis_succeeded:
                        stats.ai_analyzed += 1
                    else:
                        stats.errors += 1
                        stats.error_details.append(
                            f"{candidate.stable_key}: AI analysis failed"
                        )
                        all_children_handled = False
                        # A transient AI failure must remain retryable. Never
                        # persist it as a not-relevant decision.
                        continue
                    if self._quality_required(analysis):
                        analysis, quality_provider_failed = (
                            await self._validate_and_repair_quality(analysis, stats)
                        )
                        if quality_provider_failed:
                            await self._repository.save_job(
                                self._stored_job(
                                    candidate, analysis, status="quality_retryable"
                                )
                            )
                            all_children_handled = False
                            stats.errors += 1
                            stats.error_details.append(
                                f"{candidate.stable_key}: quality repair provider failed"
                            )
                            continue
                        if (
                            analysis.analysis_quality_status
                            == QualityStatus.NON_EXECUTABLE.value
                        ):
                            await self._repository.save_job(
                                self._stored_job(
                                    candidate, analysis, status="quality_non_executable"
                                )
                            )
                            await self._repository.upsert_processed(
                                self._processed_item(
                                    candidate, "quality_non_executable", analysis.score
                                )
                            )
                            stats.not_relevant += 1
                            continue
                        if (
                            analysis.analysis_quality_status
                            == QualityStatus.MANUAL_REVIEW.value
                        ):
                            stats.relevant += 1
                            job = await self._repository.save_job(
                                self._stored_job(
                                    candidate, analysis, status="quality_review_pending"
                                )
                            )
                            if cards_sent_this_scan < self._max_cards_per_scan:
                                attempted = await self.deliver_validated_proposal_version(
                                    candidate,
                                    job,
                                    stats,
                                    live_status_already_checked=True,
                                )
                                if attempted:
                                    cards_sent_this_scan += 1
                            continue

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
                    if analysis.score is None or analysis.score < self._min_score:
                        await self._repository.upsert_processed(
                            self._processed_item(
                                candidate, "below_threshold", analysis.score
                            )
                        )
                        stats.below_threshold += 1
                        self._record_below_sample(stats, candidate.title, analysis)
                        continue

                    stats.qualified += 1
                    analysis.qualified = True

                    job = await self._repository.save_job(
                        self._stored_job(candidate, analysis)
                    )
                elif job.status in {
                    "sent",
                    "skipped",
                    "live_status_terminal",
                    "live_status_unknown_exhausted",
                    "live_status_active_manual",
                }:
                    await self._record_duplicate(
                        candidate.stable_key,
                        candidate.discovery_source,
                        stats,
                    )
                    continue
                elif job.status == "live_status_notice_pending":
                    # The dedicated delivery queue owns this row. A terminal or
                    # exhausted decision is settled even while its notice retries.
                    if (
                        job.live_status == LiveStatus.LIVE_STATUS_UNKNOWN.value
                        and job.live_status_retry_count < self._live_status_max_retries
                    ):
                        all_children_handled = False
                    continue

                if cards_sent_this_scan >= self._max_cards_per_scan:
                    # Existing send_failed rows stay retryable; fresh rows stay queued.
                    continue

                attempted = await self.deliver_validated_proposal_version(
                    candidate,
                    job,
                    stats,
                    live_status_already_checked=active_checked_this_call,
                )
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
        if all_children_handled and email is not None:
            await self._repository.upsert_processed(
                self._processed_digest_parent(email)
            )
            await self._provider.mark_as_processed(email.id)
        return cards_sent_this_scan

    async def _send_sales_result(
        self, result: SalesProcessResult, stats: ProcessorStats
    ) -> bool:
        """Deliver one stored sales card; the card never performs a platform action."""

        if self._sales_closer is None or result.notification_deferred:
            return False
        sent = await send_sales_response_card(self._bot, self._chat_id, result)
        if not sent:
            stats.errors += 1
            stats.error_details.append(
                f"{result.incoming_turn.gmail_message_id}: sales Telegram send failed"
            )
            return True
        await self._sales_closer.mark_notified(result.incoming_turn.id)
        stats.sent += 1
        return True

    async def _drain_sales_notifications(self, stats: ProcessorStats) -> int:
        if self._sales_closer is None:
            return 0
        attempted = 0
        try:
            pending = await self._sales_closer.pending_cards()
            for result in pending[: self._max_cards_per_scan]:
                if await self._send_sales_result(result, stats):
                    attempted += 1
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(f"sales notification drain failed: {exc}")
            logger.exception("Failed to drain pending sales notifications")
        return attempted

    async def _drain_sales_escalations(self, stats: ProcessorStats) -> int:
        if self._sales_closer is None:
            return 0
        sent_count = 0
        try:
            for turn in await self._sales_closer.pending_escalations():
                if not await send_sales_escalation_card(
                    self._bot, self._chat_id, turn
                ):
                    stats.errors += 1
                    stats.error_details.append(
                        f"{turn.gmail_message_id}: sales escalation Telegram send failed"
                    )
                    continue
                await self._sales_closer.mark_escalated(turn.id)
                stats.sent += 1
                sent_count += 1
        except Exception as exc:
            stats.errors += 1
            stats.error_details.append(f"sales escalation drain failed: {exc}")
            logger.exception("Failed to drain sales escalations")
        return sent_count

    async def _send_sales_fallback_once(
        self, email: EmailMessage, stats: ProcessorStats, error: Exception
    ) -> bool:
        safe_body, _redacted = redact_sensitive_content(
            email.text_body or email.body or ""
        )
        digest = hashlib.sha256(email.id.encode("utf-8")).hexdigest()
        key = f"sales-fallback-notified:{digest}"
        stats.errors += 1
        stats.error_details.append(
            f"{email.id}: sales dialogue persistence failed: {error}"
        )
        if self._repository is not None and await self._repository.is_processed(key):
            return False
        thread_url = next(
            (
                safe
                for value in email.links
                if (safe := safe_freelancehunt_url(value))
            ),
            "",
        )
        sent = await send_sales_fallback_card(
            self._bot,
            self._chat_id,
            email_id=email.id,
            subject=email.subject,
            safe_excerpt=safe_body,
            thread_url=thread_url,
        )
        if sent and self._repository is not None:
            await self._repository.upsert_processed(
                ProcessedItem(
                    stable_key=key,
                    source_email_id=email.id,
                    platform="Freelancehunt",
                    item_type="sales_dialogue_fallback",
                    title=email.subject,
                    url=thread_url,
                    decision="durable_retry_pending",
                    score=None,
                )
            )
        return sent

    async def _process_sales_private_message(
        self,
        email: EmailMessage,
        stats: ProcessorStats,
        *,
        allow_send: bool,
    ) -> bool:
        assert self._sales_closer is not None
        try:
            result = await self._sales_closer.process_client_message(email)
        except Exception as exc:
            logger.exception(
                "Sales dialogue persistence failed; Gmail message remains retryable: %s",
                email.id,
            )
            if not allow_send:
                stats.errors += 1
                stats.error_details.append(
                    f"{email.id}: sales dialogue persistence failed: {exc}"
                )
                return False
            return await self._send_sales_fallback_once(email, stats, exc)
        if result.duplicate:
            stats.duplicates_skipped += 1
        else:
            stats.relevant += 1
            stats.qualified += 1
            if result.reply_turn is not None or result.validation_errors:
                stats.ai_analyzed += 1
        if self._repository is not None:
            await self._repository.upsert_processed(
                ProcessedItem(
                    stable_key=email.id,
                    source_email_id=email.id,
                    platform="Freelancehunt",
                    item_type="sales_dialogue",
                    title=result.opportunity.title,
                    url=result.opportunity.thread_url or result.opportunity.project_url,
                    decision=(
                        "duplicate"
                        if result.duplicate
                        else result.opportunity.state.casefold()
                    ),
                    score=None,
                )
            )
        await self._provider.mark_as_processed(email.id)
        if not allow_send or result.duplicate and result.incoming_turn.telegram_notified_at:
            return False
        return await self._send_sales_result(result, stats)

    async def _process_single(
        self,
        email: EmailMessage,
        stats: ProcessorStats,
        allow_send: bool = True,
    ) -> bool:
        """Process a single-job email and report whether a card was attempted."""
        if (
            self._sales_closer is not None
            and self._email_type(email) == EmailType.CLIENT_PRIVATE_MESSAGE
        ):
            return await self._process_sales_private_message(
                email, stats, allow_send=allow_send
            )
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
        if analysis.score is None or analysis.score < self._min_score:
            await self._mark_processed(email.id)
            stats.below_threshold += 1
            self._record_below_sample(stats, email.subject, analysis)
            return False

        stats.qualified += 1

        if self._is_guarded_project(
            analysis.event_type, analysis.platform, analysis.url
        ) and analysis.analysis_version == ANALYSIS_VERSION:
            # A Freelancehunt proposal cannot be safely delivered without the
            # PostgreSQL package that owns quality state and version dedup.
            stats.errors += 1
            stats.error_details.append(
                f"{email.id}: proposal delivery requires PostgreSQL repository"
            )
            return False

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
        """Process one actionable non-digest event with durable source context."""
        assert self._repository is not None

        email_type = self._email_type(email)
        source_url = self._source_url(email, email_type)
        stable_key = email.id
        if (
            email_type == EmailType.PROJECT_SINGLE
            and "freelancehunt" in email.sender.casefold()
        ):
            stable_key = (
                freelancehunt_project_stable_key(source_url) or email.id
            )

        if await self._repository.is_processed(stable_key):
            await self._record_duplicate(stable_key, "gmail_single", stats)
            return False

        job = await self._repository.get_job(stable_key)
        if job is not None:
            job = await self._record_source_reuse(
                job, "gmail_single", stats
            )
        pending_live_result: LiveStatusResult | None = None
        pending_live_retry_count = 0
        active_checked_this_call = False
        if job is not None and job.status in {
            "sent",
            "skipped",
            "live_status_terminal",
            "live_status_unknown_exhausted",
            "live_status_active_manual",
        }:
            await self._record_duplicate(stable_key, "gmail_single", stats)
            return False
        if job is not None and job.status == "live_status_notice_pending":
            return False
        if job is not None and job.status in {"live_status_pending", "quality_retryable"}:
            checked = await self._check_live_status(job.url or "", job)
            if checked is None:
                return False
            pending_live_result, pending_live_retry_count = checked
            if pending_live_result.status != LiveStatus.ACTIVE_BIDDABLE:
                analysis = self._apply_live_result(
                    self._analysis_from_job(job),
                    pending_live_result,
                    pending_live_retry_count,
                )
                status, settled = self._nonactive_state(
                    pending_live_result, pending_live_retry_count
                )
                if pending_live_result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                    stats.live_status_unknown += 1
                else:
                    stats.live_status_non_actionable += 1
                job = await self._repository.save_job(
                    replace(
                        job,
                        status=status,
                        **self._analysis_fields(analysis),
                    )
                )
                notice_sent = await self._send_live_status_notice_once(analysis, stats)
                if not notice_sent:
                    await self._repository.update_job_status(
                        job.stable_key, "live_status_notice_pending"
                    )
                if settled:
                    await self._repository.upsert_processed(
                        self._processed_single_item(
                            email,
                            analysis,
                            (
                                "live_status_unknown_exhausted"
                                if pending_live_result.status
                                == LiveStatus.LIVE_STATUS_UNKNOWN
                                else self._live_status_decision(
                                    pending_live_result.status
                                )
                            ),
                            stable_key=stable_key,
                        )
                    )
                return False
            # A recovered ACTIVE page must be analyzed for the first time.
            active_checked_this_call = True
            job = None

        if job is not None:
            analysis = self._analysis_from_job(job)
        else:
            security_event = email_type == EmailType.ACCOUNT_OR_SECURITY_EVENT
            if security_event:
                safe_body, redacted = redact_security_event(email.body)
            else:
                safe_body, redacted = redact_sensitive_content(email.body)
            live_result = pending_live_result
            live_retry_count = pending_live_retry_count
            if (
                live_result is None
                and self._live_status_checker is not None
                and email_type == EmailType.PROJECT_SINGLE
                and "freelancehunt" in email.sender.casefold()
            ):
                checked = await self._check_live_status(source_url)
                if checked is None:
                    return False
                live_result, live_retry_count = checked
                if live_result.status != LiveStatus.ACTIVE_BIDDABLE:
                    analysis = self._status_only_analysis(
                        stable_key=stable_key,
                        source_email_id=email.id,
                        title=email.subject,
                        description=safe_body,
                        url=source_url,
                        event_type=email_type.value,
                        platform="Freelancehunt",
                        project_id=freelancehunt_project_id(source_url),
                        received_at=email.received_at,
                        mailbox_alias=stats.mailbox_alias,
                        result=live_result,
                        retry_count=live_retry_count,
                        discovery_source="gmail_single",
                        source_publication_at=email.received_at,
                        first_seen_at=datetime.now(timezone.utc),
                    )
                    stats.ai_calls_avoided += 1
                    status, settled = self._nonactive_state(
                        live_result, live_retry_count
                    )
                    if live_result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                        stats.live_status_unknown += 1
                    else:
                        stats.live_status_non_actionable += 1
                    job = await self._repository.save_job(
                        self._stored_single_job(
                            email,
                            analysis,
                            status=status,
                            stable_key=stable_key,
                        )
                    )
                    notice_sent = await self._send_live_status_notice_once(analysis, stats)
                    if not notice_sent:
                        await self._repository.update_job_status(
                            job.stable_key, "live_status_notice_pending"
                        )
                    if settled:
                        await self._repository.upsert_processed(
                            self._processed_single_item(
                                email,
                                analysis,
                                (
                                    "live_status_unknown_exhausted"
                                    if live_result.status
                                    == LiveStatus.LIVE_STATUS_UNKNOWN
                                    else self._live_status_decision(
                                        live_result.status
                                    )
                                ),
                                stable_key=stable_key,
                            )
                        )
                    return False

            if security_event:
                # Security alerts do not need AI and must never let a model
                # reconstruct or echo credentials removed by redaction.
                analysis = JobAnalysis(
                    email_id=email.id,
                    is_relevant=True,
                    title=email.subject,
                    platform="Freelancehunt",
                    score=10.0,
                    reason="Actionable account/security notification.",
                    budget="",
                    url="",
                    urgency="high",
                    why_relevant="Protects account access and funds.",
                    event_type=email_type.value,
                    source_email_id=email.id,
                    full_description=safe_body,
                    description_completeness="FULL" if safe_body else "PARTIAL",
                    language=detect_language(f"{email.subject}\n{safe_body}"),
                    executable="yes",
                    next_action=(
                        "Відкрити Gmail або Freelancehunt напряму й особисто "
                        "перевірити сповіщення."
                    ),
                    received_at=email.received_at,
                    sensitive_redacted=redacted,
                )
            else:
                analysis = await analyze_email(
                    email_id=stable_key,
                    subject=email.subject,
                    sender=email.sender,
                    body=safe_body,
                    client=self._openai_client,
                    event_type=email_type.value,
                    source_url=source_url,
                )
                analysis.received_at = email.received_at
                analysis.source_email_id = email.id
                analysis.full_description = safe_body
                analysis.sensitive_redacted = redacted

            if live_result is not None:
                self._apply_live_result(analysis, live_result, live_retry_count)
                stats.live_status_active += 1
                active_checked_this_call = True

            analysis.event_type = email_type.value
            analysis.source_mailbox_alias = stats.mailbox_alias
            if email_type == EmailType.PROJECT_SINGLE and stable_key != email.id:
                analysis.discovery_source = "gmail_single"
                analysis.discovery_sources = "gmail"
                analysis.first_seen_at = datetime.now(timezone.utc)
                analysis.source_publication_at = email.received_at
            if security_event:
                analysis.url = ""
            elif "freelancehunt" in email.sender.casefold():
                # Prefer links extracted directly from the message. A model URL
                # is accepted only after the same strict host/scheme cleanup.
                analysis.url = source_url or self._clean_freelancehunt_url(
                    analysis.url
                )
            else:
                analysis.url = source_url or analysis.url
            if source_url and not analysis.project_id:
                analysis.project_id = freelancehunt_project_id(source_url)
            if source_url and not analysis.thread_id and email_type == EmailType.CLIENT_PRIVATE_MESSAGE:
                thread_match = re.search(r"/(?:thread|dialog)/(\d+)$", source_url)
                if thread_match:
                    analysis.thread_id = thread_match.group(1)

            if email_type == EmailType.CLIENT_PRIVATE_MESSAGE:
                analysis.is_relevant = True
                analysis.urgency = "high"
                analysis.score = 10.0
                analysis.fit_score = 10.0
                analysis.client_name = (
                    self._client_name_from_subject(email.subject)
                    or analysis.client_name
                )
                has_prior_context = any(
                    marker in safe_body.casefold()
                    for marker in (
                        "previous message",
                        "попереднє повідомлення",
                        "предыдущее сообщение",
                        "poprzednia wiadomość",
                    )
                ) or "\n>" in safe_body
                analysis.needs_context = analysis.needs_context or not has_prior_context
                analysis.next_action = analysis.next_action or (
                    "Відкрити гілку Freelancehunt, звірити попередній контекст "
                    "і особисто надіслати підготовлену відповідь."
                )
            elif email_type in {
                EmailType.PROJECT_STATUS_EVENT,
                EmailType.WORKSPACE_OR_CONTRACT_EVENT,
            }:
                analysis.is_relevant = True
                analysis.urgency = "high"
                analysis.next_action = analysis.next_action or (
                    "Відкрити подію на Freelancehunt і особисто перевірити потрібну дію."
                )

            if analysis.analysis_succeeded:
                if not security_event:
                    stats.ai_analyzed += 1
            else:
                stats.errors += 1
                stats.error_details.append(f"{email.id}: AI analysis failed")
                # Never turn a transient AI error into a terminal decision.
                return False

            if self._quality_required(analysis):
                analysis, quality_provider_failed = (
                    await self._validate_and_repair_quality(analysis, stats)
                )
                if quality_provider_failed:
                    await self._repository.save_job(
                        self._stored_single_job(
                            email,
                            analysis,
                            status="quality_retryable",
                            stable_key=stable_key,
                        )
                    )
                    stats.errors += 1
                    stats.error_details.append(
                        f"{stable_key}: quality repair provider failed"
                    )
                    return False
                if (
                    analysis.analysis_quality_status
                    == QualityStatus.NON_EXECUTABLE.value
                ):
                    await self._repository.save_job(
                        self._stored_single_job(
                            email,
                            analysis,
                            status="quality_non_executable",
                            stable_key=stable_key,
                        )
                    )
                    await self._repository.upsert_processed(
                        self._processed_single_item(
                            email,
                            analysis,
                            "quality_non_executable",
                            stable_key=stable_key,
                        )
                    )
                    stats.not_relevant += 1
                    return False
                if (
                    analysis.analysis_quality_status
                    == QualityStatus.MANUAL_REVIEW.value
                ):
                    stats.relevant += 1
                    job = await self._repository.save_job(
                        self._stored_single_job(
                            email,
                            analysis,
                            status="quality_review_pending",
                            stable_key=stable_key,
                        )
                    )
                    if not allow_send:
                        return False
                    return await self.deliver_validated_proposal_version(
                        self._candidate_from_job(job),
                        job,
                        stats,
                        live_status_already_checked=True,
                    )

            if not analysis.is_relevant:
                await self._repository.upsert_processed(
                    self._processed_single_item(
                        email,
                        analysis,
                        "not_relevant",
                        stable_key=stable_key,
                    )
                )
                if analysis.analysis_succeeded:
                    stats.not_relevant += 1
                    self._record_rejected_sample(
                        stats, email, analysis.reason or "not_job_alert"
                    )
                return False

            stats.relevant += 1
            score_filtered = email_type in {
                EmailType.PROJECT_SINGLE,
                EmailType.PROJECT_DIGEST,
            }
            if score_filtered and (
                analysis.score is None or analysis.score < self._min_score
            ):
                await self._repository.upsert_processed(
                    self._processed_single_item(
                        email,
                        analysis,
                        "below_threshold",
                        stable_key=stable_key,
                    )
                )
                stats.below_threshold += 1
                self._record_below_sample(stats, email.subject, analysis)
                return False

            stats.qualified += 1
            analysis.qualified = True

            job = await self._repository.save_job(
                self._stored_single_job(email, analysis, stable_key=stable_key)
            )
            # Send the persisted representation so the Telegram command key
            # and repository lookup key are guaranteed to be identical.
            analysis = self._analysis_from_job(job)

        if not allow_send:
            return False
        return await self.deliver_validated_proposal_version(
            self._candidate_from_job(job),
            job,
            stats,
            live_status_already_checked=active_checked_this_call,
        )

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
                    event_counts=json.dumps(stats.event_counts, sort_keys=True),
                    mailbox_alias=stats.mailbox_alias or None,
                    max_detection_latency_seconds=(
                        stats.max_detection_latency_seconds or None
                    ),
                    duplicate_source_pairs=json.dumps(
                        stats.duplicate_source_pairs, sort_keys=True
                    ),
                    live_status_active=stats.live_status_active,
                    live_status_non_actionable=stats.live_status_non_actionable,
                    live_status_unknown=stats.live_status_unknown,
                    ai_calls_avoided=stats.ai_calls_avoided,
                    max_publication_to_telegram_latency_seconds=(
                        stats.max_publication_to_telegram_latency_seconds or None
                    ),
                    quality_valid=stats.quality_valid,
                    quality_repaired=stats.quality_repaired,
                    quality_manual_review=stats.quality_manual_review,
                    quality_non_executable=stats.quality_non_executable,
                    quality_failed=stats.quality_failed,
                    zero_score_blocked=stats.zero_score_blocked,
                    missing_price_blocked=stats.missing_price_blocked,
                    missing_proposal_blocked=stats.missing_proposal_blocked,
                    invalid_evidence_blocked=stats.invalid_evidence_blocked,
                    repair_calls=stats.repair_calls,
                    repair_successes=stats.repair_successes,
                    proposal_versions_sent=stats.proposal_versions_sent,
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
                stats.event_counts[email_type.value] = (
                    stats.event_counts.get(email_type.value, 0) + 1
                )
                stats.max_detection_latency_seconds = max(
                    stats.max_detection_latency_seconds,
                    self._detection_latency(email.received_at),
                )
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
                    EmailType.MARKETING,
                    EmailType.UNKNOWN,
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

        async def execute() -> ProcessorStats:
            sales_cards = await self._drain_sales_notifications(stats)
            await self._drain_sales_escalations(stats)
            await self._drain_live_status_notices(stats)
            cards_sent_this_scan = sales_cards + await self._drain_retry_queue(stats)
            try:
                emails = await self._provider.get_new_emails()
            except Exception as exc:
                logger.exception("GmailJobProcessor: failed to fetch emails")
                stats.errors += 1
                stats.error_details.append(str(exc))
                return stats

            stats.emails_fetched = len(emails)
            stats.mailbox_alias = str(
                getattr(self._provider, "identity_alias", "mock") or "mock"
            )
            logger.info("GmailJobProcessor: fetched %d emails", stats.emails_fetched)
            return await self._run_emails(emails, stats, cards_sent_this_scan)

        try:
            if (
                self._live_status_checker is not None
                and hasattr(self._live_status_checker, "scan")
            ):
                async with self._live_status_checker.scan():
                    return await execute()
            return await execute()
        finally:
            await self._append_scan_run(trigger, started_at, stats)

    async def run_candidates(
        self,
        candidates: list[DigestJobCandidate],
        *,
        trigger: str,
        source_alias: str,
        source_candidates_found: int | None = None,
    ) -> ProcessorStats:
        """Process normalized external candidates through the shared safe path."""

        if self._repository is None:
            raise RuntimeError("external candidate processing requires PostgreSQL repository")
        stats = ProcessorStats(mailbox_alias=source_alias)
        started_at = datetime.now(timezone.utc)
        stats.event_counts[EmailType.PROJECT_FEED.value] = len(candidates)
        for candidate in candidates:
            if candidate.source_publication_at is None:
                continue
            first_seen = candidate.first_seen_at or started_at
            published = candidate.source_publication_at
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=timezone.utc)
            stats.max_detection_latency_seconds = max(
                stats.max_detection_latency_seconds,
                max(0.0, (first_seen - published).total_seconds()),
            )
        try:
            if (
                self._live_status_checker is not None
                and hasattr(self._live_status_checker, "scan")
            ):
                async with self._live_status_checker.scan():
                    await self._process_digest(
                        None,
                        stats,
                        0,
                        candidates_override=candidates,
                    )
            else:
                await self._process_digest(
                    None,
                    stats,
                    0,
                    candidates_override=candidates,
                )
            return stats
        finally:
            if source_candidates_found is not None:
                stats.candidates_found = max(
                    stats.candidates_found, int(source_candidates_found)
                )
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
                    live_result: LiveStatusResult | None = None
                    if self._live_status_checker is not None:
                        checked = await self._check_live_status(candidate.url)
                        if checked is None:
                            continue
                        live_result, live_retry_count = checked
                        if live_result.status != LiveStatus.ACTIVE_BIDDABLE:
                            if live_result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                                stats.live_status_unknown += 1
                            else:
                                stats.live_status_non_actionable += 1
                            items.append(
                                DigestPreviewItem(
                                    stable_key=candidate.stable_key,
                                    title=candidate.title,
                                    is_relevant=False,
                                    score=0.0,
                                    reason=live_result.evidence,
                                    platform=candidate.platform,
                                    budget=candidate.budget,
                                    url=candidate.url,
                                    urgency="low",
                                    why_relevant="",
                                    live_status=live_result.status.value,
                                    biddable=False,
                                )
                            )
                            continue
                    analysis = await analyze_candidate(
                        candidate, client=self._openai_client
                    )
                    if live_result is not None:
                        self._apply_live_result(
                            analysis, live_result, live_retry_count
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
                    if analysis.is_relevant and (
                        analysis.score is None or analysis.score < self._min_score
                    ):
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
                            live_status=analysis.live_status,
                            biddable=analysis.biddable,
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

    async def run_quality_backfill_preview(
        self, limit: int = 20
    ) -> QualityBackfillPreview:
        """Counts-only, side-effect-free preview for active legacy quality rows."""

        if self._repository is None:
            raise RuntimeError("quality backfill requires PostgreSQL repository")
        bounded = min(max(int(limit), 1), 100)
        jobs = await self._repository.list_quality_backfill_candidates(bounded)
        from .quality_gate import EVIDENCE_REGISTRY, finite_score

        score_states = [str(job.score_state or SCORE_MISSING).upper() for job in jobs]
        fit_states = [str(job.fit_score_state or SCORE_MISSING).upper() for job in jobs]

        return QualityBackfillPreview(
            limit=bounded,
            candidates=len(jobs),
            zero_score=sum(
                state != SCORE_VALID or finite_score(job.score) == 0.0
                for state, job in zip(score_states, jobs)
            ),
            missing_fit=sum(
                state != SCORE_VALID or finite_score(job.fit_score) == 0.0
                for state, job in zip(fit_states, jobs)
            ),
            missing_price=sum(not (job.recommended_price or "").strip() for job in jobs),
            missing_timeline=sum(not (job.realistic_timeline or "").strip() for job in jobs),
            missing_proposal=sum(not (job.proposal_draft or "").strip() for job in jobs),
            missing_or_invalid_evidence=sum(
                (job.evidence_case_id or "").strip().upper() not in EVIDENCE_REGISTRY
                for job in jobs
            ),
            missing_score=score_states.count(SCORE_MISSING),
            invalid_score=score_states.count(SCORE_INVALID),
            actual_zero_score=sum(
                state == SCORE_VALID and finite_score(job.score) == 0.0
                for state, job in zip(score_states, jobs)
            ),
            missing_fit_state=fit_states.count(SCORE_MISSING),
            invalid_fit_state=fit_states.count(SCORE_INVALID),
            actual_zero_fit=sum(
                state == SCORE_VALID and finite_score(job.fit_score) == 0.0
                for state, job in zip(fit_states, jobs)
            ),
        )

    async def run_quality_backfill(
        self,
        limit: int = 20,
        *,
        send_replacements: bool = False,
    ) -> ProcessorStats:
        """Bounded active-row reanalysis with opt-in versioned replacement sends."""

        if self._repository is None:
            raise RuntimeError("quality backfill requires PostgreSQL repository")
        bounded = min(max(int(limit), 1), 100)
        stats = ProcessorStats()
        started_at = datetime.now(timezone.utc)
        jobs = await self._repository.list_quality_backfill_candidates(bounded)
        try:
            for job in jobs:
                try:
                    original = self._analysis_from_job(job)
                    original_snapshot = self._quality_snapshot(original)
                    checked = await self._check_live_status(job.url or "", job, force=True)
                    if checked is None:
                        stats.errors += 1
                        continue
                    live_result, retry_count = checked
                    if live_result.status != LiveStatus.ACTIVE_BIDDABLE:
                        analysis = self._apply_live_result(
                            original, live_result, retry_count
                        )
                        status, _settled = self._nonactive_state(
                            live_result, retry_count
                        )
                        stored_nonactive = await self._repository.apply_backfill_live_result(
                            job.stable_key,
                            original_snapshot,
                            {"status": status, **self._analysis_fields(analysis)},
                        )
                        if stored_nonactive is None:
                            raise RuntimeError("quality backfill row disappeared")
                        if live_result.status == LiveStatus.LIVE_STATUS_UNKNOWN:
                            stats.live_status_unknown += 1
                        else:
                            stats.live_status_non_actionable += 1
                        continue
                    stats.live_status_active += 1
                    self._apply_live_result(original, live_result, retry_count)
                    initial_errors = list(validate_analysis(original).errors)
                    reanalyzed = await repair_analysis(
                        original,
                        initial_errors or ["legacy_quality_version_missing"],
                        client=self._openai_client,
                    )
                    reanalyzed.original_analysis_snapshot = original_snapshot
                    self._apply_live_result(reanalyzed, live_result, retry_count)
                    if not reanalyzed.analysis_succeeded:
                        stats.errors += 1
                        await self._repository.update_job_fields(
                            job.stable_key,
                            {
                                "status": "quality_retryable",
                                "original_analysis_snapshot": original_snapshot,
                                "analysis_quality_status": QualityStatus.FAILED.value,
                                "quality_errors": '["analysis_provider_failed"]',
                                "qualified": False,
                            },
                        )
                        continue
                    stats.ai_analyzed += 1
                    validation = validate_analysis(reanalyzed, repaired=True)
                    self._record_quality_errors(stats, list(validation.errors))
                    apply_validation(reanalyzed, validation, repair_count=1)
                    self._record_quality_status(stats, validation.status)
                    if is_proposal_ready(reanalyzed):
                        status = "queued" if send_replacements else "quality_validated_backfill"
                        reanalyzed.qualified = True
                    elif reanalyzed.analysis_quality_status == QualityStatus.NON_EXECUTABLE.value:
                        status = "quality_non_executable"
                    else:
                        status = "quality_manual_review"
                    stored = await self._repository.update_job_fields(
                        job.stable_key,
                        {"status": status, **self._analysis_fields(reanalyzed)},
                    )
                    if stored is None:
                        raise RuntimeError("quality backfill row disappeared")
                    if send_replacements and is_proposal_ready(reanalyzed):
                        await self.deliver_validated_proposal_version(
                            self._candidate_from_job(stored),
                            stored,
                            stats,
                            live_status_already_checked=True,
                        )
                except Exception as exc:
                    stats.errors += 1
                    stats.error_details.append(
                        f"quality backfill row failed: {type(exc).__name__}"
                    )
                    logger.exception("Quality backfill row failed")
            return stats
        finally:
            await self._append_scan_run("quality_backfill", started_at, stats)

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
                    analysis.is_relevant
                    and analysis.score is not None
                    and analysis.score >= self._min_score
                )
            except Exception as exc:
                logger.exception("run_debug: analyze failed for email_id=%s", email.id)
                entry["error"] = str(exc)
            results.append(entry)
        return results
