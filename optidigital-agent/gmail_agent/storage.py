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

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

TERMINAL_JOB_STATUSES = frozenset({"sent", "skipped"})
DEFAULT_CLAIMABLE_STATUSES = ("queued", "send_failed")
DEFAULT_SENDING_LEASE = timedelta(minutes=15)


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

    async def is_processed(self, stable_key: str) -> bool:
        async with self._lock:
            return stable_key in self._processed

    async def get_processed(self, stable_key: str) -> ProcessedItem | None:
        async with self._lock:
            item = self._processed.get(stable_key)
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
                )
            stored = replace(job)
            self._jobs[job.stable_key] = stored
            return replace(stored)

    async def get_job(self, stable_key: str) -> StoredGmailJob | None:
        async with self._lock:
            job = self._jobs.get(stable_key)
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


AsyncSessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class PostgresGmailRepository:
    """PostgreSQL repository using an injectable SQLAlchemy async session factory."""

    def __init__(self, session_factory: AsyncSessionFactory) -> None:
        from db.models import GmailJob, GmailProcessedItem, GmailScanRun

        self._session_factory = session_factory
        self._job_model = GmailJob
        self._processed_item_model = GmailProcessedItem
        self._scan_run_model = GmailScanRun

    async def is_processed(self, stable_key: str) -> bool:
        async with self._session_factory() as session:
            result = await session.execute(
                select(self._processed_item_model.stable_key)
                .where(self._processed_item_model.stable_key == stable_key)
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def get_processed(self, stable_key: str) -> ProcessedItem | None:
        async with self._session_factory() as session:
            model = await session.get(self._processed_item_model, stable_key)
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
            if key not in {"stable_key", "created_at", "status", "status_updated_at"}
        }
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
