"""Repository boundary for durable Gmail processing state.

Production uses :class:`PostgresGmailRepository`; tests can use the behaviorally
equivalent :class:`InMemoryGmailRepository` without credentials or a database.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import and_, case, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .project_identity import freelancehunt_project_stable_key

TERMINAL_JOB_STATUSES = frozenset(
    {
        "sent",
        "skipped",
        "live_status_terminal",
        "live_status_unknown_exhausted",
        "live_status_active_manual",
        "quality_manual_review",
        "quality_non_executable",
    }
)
DEFAULT_CLAIMABLE_STATUSES = ("queued", "send_failed", "quality_review_pending")
DEFAULT_SENDING_LEASE = timedelta(minutes=15)
_IDENTITY_RECONCILIATION_MARKER = "stage3_freelancehunt_identity_v1"
_LEGACY_CARD_STATUSES = frozenset(
    {
        "notified",
        "sent",
        "skipped",
        "live_status_terminal",
        "live_status_unknown_exhausted",
        "live_status_active_manual",
        "live_status_pending_notified",
    }
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ProcessedItem:
    stable_key: str
    source_email_id: str
    platform: str
    item_type: str
    title: str | None
    url: str | None
    decision: str
    score: float | None
    processed_at: datetime = dataclass_field(default_factory=utc_now)


@dataclass(frozen=True, slots=True)
class StoredGmailJob:
    stable_key: str
    source_email_id: str
    platform: str
    title: str
    score: float
    reason: str
    budget: str | None
    url: str | None
    urgency: str
    why_relevant: str
    created_at: datetime = dataclass_field(default_factory=utc_now)
    status: str = "queued"
    status_updated_at: datetime = dataclass_field(default_factory=utc_now)
    event_type: str = "PROJECT_SINGLE"
    full_description: str = ""
    description_completeness: str = "PARTIAL"
    language: str = "uk"
    category: str = ""
    skills: str = ""
    deadline: str = ""
    bid_count: int | None = None
    client_name: str = ""
    client_profile_url: str = ""
    client_context: str = ""
    project_id: str = ""
    thread_id: str = ""
    service_lane: str = ""
    executable: str = "maybe"
    fit_score: float | None = None
    win_probability_signal: str = ""
    scope_clarity: str = ""
    estimated_effort: str = ""
    delivery_risk: str = ""
    client_payment_risk: str = ""
    project_mode: str = ""
    project_mode_reason: str = ""
    recommended_price: str = ""
    realistic_timeline: str = ""
    selected_evidence: str = ""
    analysis_evidence: str = ""
    proposal_draft: str = ""
    needs_context: bool = False
    next_action: str = ""
    source_mailbox_alias: str = ""
    received_at: datetime | None = None
    sensitive_redacted: bool = False
    live_status: str = ""
    live_status_checked_at: datetime | None = None
    live_status_evidence: str = ""
    biddable: bool | None = None
    live_status_retry_count: int = 0
    live_status_last_error: str = ""
    qualified: bool = False
    tags: str = ""
    budget_currency: str = ""
    discovery_source: str = ""
    discovery_sources: str = ""
    source_publication_at: datetime | None = None
    source_feed_timestamp: datetime | None = None
    feed_fetched_at: datetime | None = None
    first_seen_at: datetime | None = None
    telegram_sent_at: datetime | None = None
    publication_to_telegram_latency_seconds: float | None = None
    analysis_quality_status: str = ""
    quality_checked_at: datetime | None = None
    quality_errors: str = "[]"
    quality_repair_count: int = 0
    proposal_quality_score: float | None = None
    evidence_case_id: str = ""
    analysis_version: str = ""
    proposal_version: str = ""
    original_analysis_snapshot: str = ""
    quality_clarification_question: str = ""
    model_output_json: str = ""


# Short public name for callers; the longer name makes its persistence role
# explicit at call sites that also use the analyzer's JobAnalysis type.
GmailJob = StoredGmailJob


@dataclass(frozen=True, slots=True)
class ScanRun:
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    emails_inspected: int = 0
    candidates_found: int = 0
    ai_analyzed: int = 0
    relevant: int = 0
    qualified: int = 0
    duplicates: int = 0
    not_relevant: int = 0
    below_threshold: int = 0
    sent: int = 0
    sent_from_queue: int = 0
    errors: int = 0
    event_counts: str = "{}"
    mailbox_alias: str | None = None
    max_detection_latency_seconds: float | None = None
    duplicate_source_pairs: str = "{}"
    live_status_active: int = 0
    live_status_non_actionable: int = 0
    live_status_unknown: int = 0
    ai_calls_avoided: int = 0
    max_publication_to_telegram_latency_seconds: float | None = None
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
    id: int | None = None


@runtime_checkable
class GmailRepository(Protocol):
    async def is_processed(self, stable_key: str) -> bool: ...

    async def get_processed(self, stable_key: str) -> ProcessedItem | None: ...

    async def upsert_processed(self, item: ProcessedItem) -> ProcessedItem: ...

    async def save_job(self, job: StoredGmailJob) -> StoredGmailJob: ...

    async def get_job(self, stable_key: str) -> StoredGmailJob | None: ...

    async def update_job_status(
        self, stable_key: str, status: str
    ) -> StoredGmailJob | None: ...

    async def update_job_fields(
        self, stable_key: str, fields: Mapping[str, Any]
    ) -> StoredGmailJob | None: ...

    async def list_jobs_by_status(
        self, statuses: Sequence[str], limit: int = 100
    ) -> list[StoredGmailJob]: ...

    async def claim_job(
        self,
        stable_key: str,
        allowed_statuses: Sequence[str] = DEFAULT_CLAIMABLE_STATUSES,
        new_status: str = "sending",
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> bool: ...

    async def list_retryable_jobs(
        self,
        limit: int = 10,
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> list[StoredGmailJob]: ...

    async def append_scan_run(self, run: ScanRun) -> ScanRun: ...

    async def list_scan_runs(self, limit: int = 20) -> list[ScanRun]: ...

    async def reconcile_freelancehunt_identities(self) -> int: ...

    async def list_quality_backfill_candidates(
        self, limit: int = 20
    ) -> list[StoredGmailJob]: ...


class InMemoryGmailRepository:
    """Concurrency-safe repository for unit tests."""

    def __init__(self, state: dict[str, object] | None = None) -> None:
        state = state if state is not None else {}
        self._processed = state.setdefault("processed", {})
        self._jobs = state.setdefault("jobs", {})
        self._scan_runs = state.setdefault("scan_runs", [])
        state.setdefault("next_scan_id", 1)
        self._state = state
        self._lock = state.setdefault("lock", asyncio.Lock())

    async def reconcile_freelancehunt_identities(self) -> int:
        """One-time test-equivalent aliasing for historical source identities."""

        async with self._lock:
            if self._state.get(_IDENTITY_RECONCILIATION_MARKER):
                return 0
            aliases: dict[str, ProcessedItem] = {}
            for item in list(self._processed.values()):
                if "freelancehunt" not in item.platform.casefold() or not item.url:
                    continue
                canonical_key = freelancehunt_project_stable_key(item.url)
                if canonical_key and canonical_key != item.stable_key:
                    aliases.setdefault(canonical_key, replace(item, stable_key=canonical_key))
            for order in self._state.get("legacy_orders", []):
                if (
                    "freelancehunt" not in str(order.get("platform") or "").casefold()
                    or str(order.get("status") or "") not in _LEGACY_CARD_STATUSES
                ):
                    continue
                canonical_key = freelancehunt_project_stable_key(
                    str(order.get("url") or "")
                )
                if not canonical_key:
                    continue
                aliases.setdefault(
                    canonical_key,
                    ProcessedItem(
                        stable_key=canonical_key,
                        source_email_id=f"legacy-order:{order.get('id', '')}",
                        platform="Freelancehunt",
                        item_type="legacy_parser",
                        title=str(order.get("title") or ""),
                        url=str(order.get("url") or ""),
                        decision=f"legacy_{order.get('status', 'handled')}",
                        score=order.get("score"),
                    ),
                )
            inserted = 0
            for key, item in aliases.items():
                if key not in self._processed:
                    self._processed[key] = replace(item)
                    inserted += 1
            self._state[_IDENTITY_RECONCILIATION_MARKER] = True
            return inserted

    async def is_processed(self, stable_key: str) -> bool:
        async with self._lock:
            return stable_key in self._processed or any(
                item.item_type == "single_job"
                and item.source_email_id == stable_key
                for item in self._processed.values()
            )

    async def get_processed(self, stable_key: str) -> ProcessedItem | None:
        async with self._lock:
            item = self._processed.get(stable_key)
            if item is None:
                item = next(
                    (
                        candidate
                        for candidate in self._processed.values()
                        if candidate.item_type == "single_job"
                        and candidate.source_email_id == stable_key
                    ),
                    None,
                )
            return replace(item) if item is not None else None

    async def upsert_processed(self, item: ProcessedItem) -> ProcessedItem:
        async with self._lock:
            stored = replace(item)
            self._processed[item.stable_key] = stored
            return replace(stored)

    async def save_job(self, job: StoredGmailJob) -> StoredGmailJob:
        async with self._lock:
            current = self._jobs.get(job.stable_key)
            if current is not None:
                explicit_quality = bool(job.analysis_quality_status)
                keep_existing_quality = bool(current.analysis_quality_status) and not explicit_quality
                status = current.status if current.status in TERMINAL_JOB_STATUSES else job.status
                status_updated_at = (
                    current.status_updated_at
                    if current.status in TERMINAL_JOB_STATUSES
                    else job.status_updated_at
                )
                job = replace(
                    job,
                    created_at=current.created_at,
                    status=status,
                    status_updated_at=status_updated_at,
                    # Never lose the source specification or first selected
                    # proposal when a retry/restart saves a thinner payload.
                    full_description=(
                        job.full_description or current.full_description
                    ),
                    client_context=(job.client_context or current.client_context),
                    proposal_draft=(
                        job.proposal_draft
                        if job.analysis_quality_status
                        else (job.proposal_draft or current.proposal_draft)
                    ),
                    selected_evidence=(
                        job.selected_evidence
                        if job.analysis_quality_status
                        else (job.selected_evidence or current.selected_evidence)
                    ),
                    recommended_price=(
                        current.recommended_price
                        if keep_existing_quality
                        else job.recommended_price
                    ),
                    realistic_timeline=(
                        current.realistic_timeline
                        if keep_existing_quality
                        else job.realistic_timeline
                    ),
                    analysis_quality_status=(
                        current.analysis_quality_status
                        if keep_existing_quality
                        else job.analysis_quality_status
                    ),
                    quality_checked_at=(
                        current.quality_checked_at
                        if keep_existing_quality
                        else job.quality_checked_at
                    ),
                    quality_errors=(
                        current.quality_errors
                        if keep_existing_quality
                        else job.quality_errors
                    ),
                    quality_repair_count=(
                        current.quality_repair_count
                        if keep_existing_quality
                        else job.quality_repair_count
                    ),
                    proposal_quality_score=(
                        current.proposal_quality_score
                        if keep_existing_quality
                        else job.proposal_quality_score
                    ),
                    evidence_case_id=(
                        current.evidence_case_id
                        if keep_existing_quality
                        else job.evidence_case_id
                    ),
                    analysis_version=(
                        current.analysis_version
                        if keep_existing_quality
                        else job.analysis_version
                    ),
                    proposal_version=(
                        current.proposal_version
                        if keep_existing_quality
                        else job.proposal_version
                    ),
                    original_analysis_snapshot=(
                        current.original_analysis_snapshot
                        if keep_existing_quality
                        else job.original_analysis_snapshot
                    ),
                    quality_clarification_question=(
                        current.quality_clarification_question
                        if keep_existing_quality
                        else job.quality_clarification_question
                    ),
                    model_output_json=(
                        current.model_output_json
                        if keep_existing_quality
                        else job.model_output_json
                    ),
                    first_seen_at=(current.first_seen_at or job.first_seen_at),
                    discovery_source=(
                        current.discovery_source or job.discovery_source
                    ),
                    discovery_sources=_merge_sources(
                        current.discovery_sources,
                        job.discovery_sources or job.discovery_source,
                    ),
                )
            stored = replace(job)
            self._jobs[job.stable_key] = stored
            return replace(stored)

    async def get_job(self, stable_key: str) -> StoredGmailJob | None:
        async with self._lock:
            job = self._jobs.get(stable_key)
            if job is None:
                job = next(
                    (
                        candidate
                        for candidate in self._jobs.values()
                        if candidate.event_type == "PROJECT_SINGLE"
                        and candidate.source_email_id == stable_key
                    ),
                    None,
                )
            return replace(job) if job is not None else None

    async def update_job_status(
        self, stable_key: str, status: str
    ) -> StoredGmailJob | None:
        async with self._lock:
            job = self._jobs.get(stable_key)
            if job is None:
                return None
            updated = replace(job, status=status, status_updated_at=utc_now())
            self._jobs[stable_key] = updated
            return replace(updated)

    async def update_job_fields(
        self, stable_key: str, fields: Mapping[str, Any]
    ) -> StoredGmailJob | None:
        async with self._lock:
            job = self._jobs.get(stable_key)
            if job is None:
                return None
            allowed = set(StoredGmailJob.__dataclass_fields__) - {
                "stable_key",
                "created_at",
            }
            values = {key: value for key, value in fields.items() if key in allowed}
            if "status" in values and "status_updated_at" not in values:
                values["status_updated_at"] = utc_now()
            updated = replace(job, **values)
            self._jobs[stable_key] = updated
            return replace(updated)

    async def list_jobs_by_status(
        self, statuses: Sequence[str], limit: int = 100
    ) -> list[StoredGmailJob]:
        if limit <= 0 or not statuses:
            return []
        wanted = set(statuses)
        async with self._lock:
            rows = [job for job in self._jobs.values() if job.status in wanted]
            rows.sort(key=lambda job: (job.status_updated_at, job.created_at, job.stable_key))
            return [replace(job) for job in rows[:limit]]

    async def claim_job(
        self,
        stable_key: str,
        allowed_statuses: Sequence[str] = DEFAULT_CLAIMABLE_STATUSES,
        new_status: str = "sending",
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> bool:
        claimed_at = now or utc_now()
        stale_before = claimed_at - lease_timeout
        async with self._lock:
            job = self._jobs.get(stable_key)
            if job is None:
                return False
            is_claimable = job.status in allowed_statuses
            is_stale_sending = (
                job.status == "sending" and job.status_updated_at <= stale_before
            )
            if not (is_claimable or is_stale_sending):
                return False
            self._jobs[stable_key] = replace(
                job, status=new_status, status_updated_at=claimed_at
            )
            return True

    async def list_retryable_jobs(
        self,
        limit: int = 10,
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> list[StoredGmailJob]:
        if limit <= 0:
            return []
        stale_before = (now or utc_now()) - lease_timeout
        async with self._lock:
            retryable = [
                job
                for job in self._jobs.values()
                if job.status in DEFAULT_CLAIMABLE_STATUSES
                or (
                    job.status == "sending"
                    and job.status_updated_at <= stale_before
                )
            ]
            retryable.sort(
                key=lambda job: (
                    job.status_updated_at,
                    job.created_at,
                    job.stable_key,
                )
            )
            return [replace(job) for job in retryable[:limit]]

    async def append_scan_run(self, run: ScanRun) -> ScanRun:
        async with self._lock:
            next_scan_id = self._state["next_scan_id"]
            stored = replace(run, id=next_scan_id)
            self._state["next_scan_id"] = next_scan_id + 1
            self._scan_runs.append(stored)
            return replace(stored)

    async def list_scan_runs(self, limit: int = 20) -> list[ScanRun]:
        if limit <= 0:
            return []
        async with self._lock:
            ordered = sorted(
                self._scan_runs,
                key=lambda run: (run.started_at, run.id or 0),
                reverse=True,
            )
            return [replace(run) for run in ordered[:limit]]

    async def list_quality_backfill_candidates(
        self, limit: int = 20
    ) -> list[StoredGmailJob]:
        if limit <= 0:
            return []
        from .quality_gate import EVIDENCE_REGISTRY, PROPOSAL_READY_QUALITY_STATUSES

        async with self._lock:
            rows = [
                job
                for job in self._jobs.values()
                if job.live_status == "ACTIVE_BIDDABLE"
                and job.biddable is True
                and (
                    job.analysis_quality_status
                    not in PROPOSAL_READY_QUALITY_STATUSES
                    or job.score is None
                    or job.score <= 0
                    or job.fit_score is None
                    or job.fit_score <= 0
                    or not (job.recommended_price or "").strip()
                    or not (job.realistic_timeline or "").strip()
                    or not (job.proposal_draft or "").strip()
                    or (job.evidence_case_id or "").strip().upper()
                    not in EVIDENCE_REGISTRY
                )
            ]
            rows.sort(key=lambda job: (job.created_at, job.stable_key))
            return [replace(job) for job in rows[: min(int(limit), 100)]]


AsyncSessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PostgresGmailRepository:
    """PostgreSQL repository using an injectable SQLAlchemy async session factory."""

    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        from db.models import (
            GmailJob,
            GmailProcessedItem,
            GmailScanRun,
            Order,
            Setting,
        )

        self._session_factory = session_factory
        self._job_model = GmailJob
        self._processed_item_model = GmailProcessedItem
        self._scan_run_model = GmailScanRun
        self._order_model = Order
        self._setting_model = Setting

    async def reconcile_freelancehunt_identities(self) -> int:
        """Alias already-handled Gmail/parser rows to the Stage 3 project key.

        The marker and aliases commit atomically, so a restart either retries the
        reconciliation or observes it complete. Existing rows are never updated
        or deleted; canonical aliases use conflict-safe inserts only.
        """

        async with self._session_factory() as session:
            marker = await session.get(
                self._setting_model, _IDENTITY_RECONCILIATION_MARKER
            )
            if marker is not None and marker.value == "complete":
                return 0

            aliases: dict[str, ProcessedItem] = {}
            historical = await session.scalars(
                select(self._processed_item_model).where(
                    self._processed_item_model.platform.ilike("%freelancehunt%"),
                    self._processed_item_model.url.is_not(None),
                )
            )
            for row in historical.all():
                canonical_key = freelancehunt_project_stable_key(row.url or "")
                if canonical_key and canonical_key != row.stable_key:
                    aliases.setdefault(
                        canonical_key,
                        ProcessedItem(
                            stable_key=canonical_key,
                            source_email_id=row.source_email_id,
                            platform=row.platform,
                            item_type=row.item_type,
                            title=row.title,
                            url=row.url,
                            decision=row.decision,
                            score=row.score,
                        ),
                    )

            legacy_orders = await session.scalars(
                select(self._order_model).where(
                    self._order_model.platform.ilike("%freelancehunt%"),
                    self._order_model.status.in_(_LEGACY_CARD_STATUSES),
                )
            )
            for row in legacy_orders.all():
                canonical_key = freelancehunt_project_stable_key(row.url or "")
                if not canonical_key:
                    continue
                aliases.setdefault(
                    canonical_key,
                    ProcessedItem(
                        stable_key=canonical_key,
                        source_email_id=f"legacy-order:{row.id}",
                        platform="Freelancehunt",
                        item_type="legacy_parser",
                        title=row.title,
                        url=row.url,
                        decision=f"legacy_{row.status}",
                        score=row.score,
                    ),
                )

            terminal_jobs = await session.scalars(
                select(self._job_model).where(
                    self._job_model.platform.ilike("%freelancehunt%"),
                    self._job_model.url.is_not(None),
                    self._job_model.status.in_(TERMINAL_JOB_STATUSES),
                )
            )
            for row in terminal_jobs.all():
                canonical_key = freelancehunt_project_stable_key(row.url or "")
                if not canonical_key or canonical_key == row.stable_key:
                    continue
                aliases.setdefault(
                    canonical_key,
                    ProcessedItem(
                        stable_key=canonical_key,
                        source_email_id=row.source_email_id,
                        platform=row.platform,
                        item_type=(
                            "single_job"
                            if row.event_type == "PROJECT_SINGLE"
                            else "digest_job"
                        ),
                        title=row.title,
                        url=row.url,
                        decision=row.status,
                        score=row.score,
                    ),
                )

            for item in aliases.values():
                statement = postgres_insert(self._processed_item_model).values(
                    **_processed_values(item)
                )
                await session.execute(
                    statement.on_conflict_do_nothing(
                        index_elements=[self._processed_item_model.stable_key]
                    )
                )
            marker_statement = postgres_insert(self._setting_model).values(
                key=_IDENTITY_RECONCILIATION_MARKER,
                value="complete",
            )
            await session.execute(
                marker_statement.on_conflict_do_update(
                    index_elements=[self._setting_model.key],
                    set_={"value": "complete"},
                )
            )
            await session.commit()
            return len(aliases)

    async def is_processed(self, stable_key: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                select(self._processed_item_model.stable_key)
                .where(
                    or_(
                        self._processed_item_model.stable_key == stable_key,
                        and_(
                            self._processed_item_model.item_type == "single_job",
                            self._processed_item_model.source_email_id == stable_key,
                        ),
                    )
                )
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def get_processed(self, stable_key: str) -> ProcessedItem | None:
        async with self._session_factory() as session:
            model = await session.get(self._processed_item_model, stable_key)
            if model is None:
                result = await session.execute(
                    select(self._processed_item_model)
                    .where(
                        self._processed_item_model.item_type == "single_job",
                        self._processed_item_model.source_email_id == stable_key,
                    )
                    .limit(1)
                )
                model = result.scalar_one_or_none()
            return _processed_from_row(model) if model is not None else None

    async def upsert_processed(self, item: ProcessedItem) -> ProcessedItem:
        values = _processed_values(item)
        statement = postgres_insert(self._processed_item_model).values(**values)
        statement = statement.on_conflict_do_update(
            index_elements=[self._processed_item_model.stable_key],
            set_={key: value for key, value in statement.excluded.items() if key != "stable_key"},
        ).returning(*self._processed_item_model.__table__.c)
        async with self._session_factory() as session:
            result = await session.execute(statement)
            stored = _processed_from_row(result.mappings().one())
            await session.commit()
            return stored

    async def save_job(self, job: StoredGmailJob) -> StoredGmailJob:
        values = _job_values(job)
        statement = postgres_insert(self._job_model).values(**values)
        excluded = statement.excluded
        incoming = {
            key: value
            for key, value in excluded.items()
            if key not in {
                "stable_key",
                "created_at",
                "status",
                "status_updated_at",
                # Source truth remains immutable on conflict. Stage 4 may
                # replace or clear a proposal only with an explicit persisted
                # quality state; the prior package is retained in
                # original_analysis_snapshot for audit.
                "full_description",
                "client_context",
                "first_seen_at",
                "discovery_source",
            }
        }
        quality_incoming = and_(
            excluded.analysis_quality_status.is_not(None),
            excluded.analysis_quality_status != "",
        )
        for field_name in (
            "proposal_draft",
            "selected_evidence",
            "analysis_quality_status",
            "quality_checked_at",
            "quality_errors",
            "quality_repair_count",
            "proposal_quality_score",
            "evidence_case_id",
            "analysis_version",
            "proposal_version",
            "original_analysis_snapshot",
            "quality_clarification_question",
            "model_output_json",
        ):
            incoming[field_name] = case(
                (quality_incoming, getattr(excluded, field_name)),
                else_=getattr(self._job_model, field_name),
            )
        quality_or_legacy = or_(
            quality_incoming,
            self._job_model.analysis_quality_status.is_(None),
            self._job_model.analysis_quality_status == "",
        )
        for field_name in ("recommended_price", "realistic_timeline"):
            incoming[field_name] = case(
                (quality_or_legacy, getattr(excluded, field_name)),
                else_=getattr(self._job_model, field_name),
            )
        incoming["status"] = _preserved_job_status(excluded.status, self._job_model)
        incoming["status_updated_at"] = _preserved_job_status_updated_at(
            excluded.status_updated_at, self._job_model
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self._job_model.stable_key], set_=incoming
        ).returning(*self._job_model.__table__.c)
        async with self._session_factory() as session:
            result = await session.execute(statement)
            stored = _job_from_row(result.mappings().one())
            await session.commit()
            return stored

    async def get_job(self, stable_key: str) -> StoredGmailJob | None:
        async with self._session_factory() as session:
            model = await session.get(self._job_model, stable_key)
            if model is None:
                result = await session.scalars(
                    select(self._job_model)
                    .where(
                        self._job_model.event_type == "PROJECT_SINGLE",
                        self._job_model.source_email_id == stable_key,
                    )
                    .order_by(self._job_model.created_at.desc())
                    .limit(1)
                )
                model = result.first()
            return _job_from_row(model) if model is not None else None

    async def update_job_status(
        self, stable_key: str, status: str
    ) -> StoredGmailJob | None:
        status_updated_at = utc_now()
        statement = (
            update(self._job_model)
            .where(self._job_model.stable_key == stable_key)
            .values(status=status, status_updated_at=status_updated_at)
            .returning(*self._job_model.__table__.c)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one_or_none()
            stored = _job_from_row(row) if row is not None else None
            await session.commit()
            return stored

    async def update_job_fields(
        self, stable_key: str, fields: Mapping[str, Any]
    ) -> StoredGmailJob | None:
        allowed = set(StoredGmailJob.__dataclass_fields__) - {
            "stable_key",
            "created_at",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return await self.get_job(stable_key)
        if "status" in values and "status_updated_at" not in values:
            values["status_updated_at"] = utc_now()
        statement = (
            update(self._job_model)
            .where(self._job_model.stable_key == stable_key)
            .values(**values)
            .returning(*self._job_model.__table__.c)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            row = result.mappings().one_or_none()
            stored = _job_from_row(row) if row is not None else None
            await session.commit()
            return stored

    async def list_jobs_by_status(
        self, statuses: Sequence[str], limit: int = 100
    ) -> list[StoredGmailJob]:
        if limit <= 0 or not statuses:
            return []
        statement = (
            select(self._job_model)
            .where(self._job_model.status.in_(tuple(statuses)))
            .order_by(
                self._job_model.status_updated_at.asc(),
                self._job_model.created_at.asc(),
                self._job_model.stable_key.asc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            result = await session.scalars(statement)
            return [_job_from_row(model) for model in result.all()]

    async def claim_job(
        self,
        stable_key: str,
        allowed_statuses: Sequence[str] = DEFAULT_CLAIMABLE_STATUSES,
        new_status: str = "sending",
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> bool:
        statuses = tuple(allowed_statuses)
        claimed_at = now or utc_now()
        stale_before = claimed_at - lease_timeout
        from sqlalchemy import and_, or_

        claimable_predicates = [
            and_(
                self._job_model.status == "sending",
                self._job_model.status_updated_at <= stale_before,
            )
        ]
        if statuses:
            claimable_predicates.append(self._job_model.status.in_(statuses))
        statement = (
            update(self._job_model)
            .where(
                self._job_model.stable_key == stable_key,
                or_(*claimable_predicates),
            )
            .values(status=new_status, status_updated_at=claimed_at)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            claimed = bool(getattr(result, "rowcount", 0))
            await session.commit()
            return claimed

    async def list_retryable_jobs(
        self,
        limit: int = 10,
        *,
        now: datetime | None = None,
        lease_timeout: timedelta = DEFAULT_SENDING_LEASE,
    ) -> list[StoredGmailJob]:
        if limit <= 0:
            return []
        stale_before = (now or utc_now()) - lease_timeout
        from sqlalchemy import and_, or_

        statement = (
            select(self._job_model)
            .where(
                or_(
                    self._job_model.status.in_(DEFAULT_CLAIMABLE_STATUSES),
                    and_(
                        self._job_model.status == "sending",
                        self._job_model.status_updated_at <= stale_before,
                    ),
                )
            )
            .order_by(
                self._job_model.status_updated_at.asc(),
                self._job_model.created_at.asc(),
                self._job_model.stable_key.asc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            result = await session.scalars(statement)
            return [_job_from_row(model) for model in result.all()]

    async def append_scan_run(self, run: ScanRun) -> ScanRun:
        statement = (
            postgres_insert(self._scan_run_model)
            .values(**_scan_run_values(run))
            .returning(*self._scan_run_model.__table__.c)
        )
        async with self._session_factory() as session:
            result = await session.execute(statement)
            stored = _scan_run_from_row(result.mappings().one())
            await session.commit()
            return stored

    async def list_scan_runs(self, limit: int = 20) -> list[ScanRun]:
        if limit <= 0:
            return []
        statement = (
            select(self._scan_run_model)
            .order_by(
                self._scan_run_model.started_at.desc(),
                self._scan_run_model.id.desc(),
            )
            .limit(limit)
        )
        async with self._session_factory() as session:
            result = await session.scalars(statement)
            return [_scan_run_from_row(model) for model in result.all()]

    async def list_quality_backfill_candidates(
        self, limit: int = 20
    ) -> list[StoredGmailJob]:
        if limit <= 0:
            return []
        from .quality_gate import EVIDENCE_REGISTRY, PROPOSAL_READY_QUALITY_STATUSES

        statement = (
            select(self._job_model)
            .where(
                self._job_model.live_status == "ACTIVE_BIDDABLE",
                self._job_model.biddable.is_(True),
                or_(
                    self._job_model.analysis_quality_status.is_(None),
                    self._job_model.analysis_quality_status.not_in(
                        tuple(PROPOSAL_READY_QUALITY_STATUSES)
                    ),
                    self._job_model.score <= 0,
                    self._job_model.fit_score.is_(None),
                    self._job_model.fit_score <= 0,
                    self._job_model.recommended_price.is_(None),
                    self._job_model.recommended_price == "",
                    self._job_model.realistic_timeline.is_(None),
                    self._job_model.realistic_timeline == "",
                    self._job_model.proposal_draft.is_(None),
                    self._job_model.proposal_draft == "",
                    self._job_model.evidence_case_id.is_(None),
                    self._job_model.evidence_case_id == "",
                    self._job_model.evidence_case_id.not_in(
                        tuple(EVIDENCE_REGISTRY)
                    ),
                ),
            )
            .order_by(self._job_model.created_at.asc(), self._job_model.stable_key.asc())
            .limit(min(int(limit), 100))
        )
        async with self._session_factory() as session:
            result = await session.scalars(statement)
            return [_job_from_row(model) for model in result.all()]


def _preserved_job_status(incoming_status: Any, job_model: Any) -> Any:
    from sqlalchemy import case

    return case(
        (job_model.status.in_(tuple(TERMINAL_JOB_STATUSES)), job_model.status),
        else_=incoming_status,
    )


def _preserved_job_status_updated_at(incoming_timestamp: Any, job_model: Any) -> Any:
    from sqlalchemy import case

    return case(
        (
            job_model.status.in_(tuple(TERMINAL_JOB_STATUSES)),
            job_model.status_updated_at,
        ),
        else_=incoming_timestamp,
    )


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, Mapping):
        return row[field]
    return getattr(row, field)


def _merge_sources(*values: str) -> str:
    sources: list[str] = []
    for value in values:
        for source in str(value or "").split(","):
            normalized = source.strip()
            if normalized and normalized not in sources:
                sources.append(normalized)
    return ",".join(sources)


def _processed_values(item: ProcessedItem) -> dict[str, Any]:
    return {field: getattr(item, field) for field in ProcessedItem.__dataclass_fields__}


def _job_values(job: StoredGmailJob) -> dict[str, Any]:
    return {field: getattr(job, field) for field in StoredGmailJob.__dataclass_fields__}


def _scan_run_values(run: ScanRun) -> dict[str, Any]:
    return {
        field: getattr(run, field)
        for field in ScanRun.__dataclass_fields__
        if field != "id"
    }


def _processed_from_row(row: Any) -> ProcessedItem:
    return ProcessedItem(
        **{field: _row_value(row, field) for field in ProcessedItem.__dataclass_fields__}
    )


def _job_from_row(row: Any) -> StoredGmailJob:
    return StoredGmailJob(
        **{field: _row_value(row, field) for field in StoredGmailJob.__dataclass_fields__}
    )


def _scan_run_from_row(row: Any) -> ScanRun:
    return ScanRun(
        **{field: _row_value(row, field) for field in ScanRun.__dataclass_fields__}
    )
