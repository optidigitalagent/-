from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str | None] = mapped_column(String(300), nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(200), nullable=True)
    bid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employer_phone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employer_telegram: Mapped[str | None] = mapped_column(String(200), nullable=True)
    employer_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    live_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    live_status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_status_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    biddable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    live_status_retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    live_status_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    responses: Mapped[list["Response"]] = relationship("Response", back_populates="order")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)

    order: Mapped["Order"] = relationship("Order", back_populates="responses")


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=True)


class GmailProcessedItem(Base):
    """Persistent deduplication decision for an email or extracted job."""

    __tablename__ = "gmail_processed_items"

    stable_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_email_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    decision: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GmailScanRun(Base):
    """One persistent manual, scheduler, or backfill Gmail scan summary."""

    __tablename__ = "gmail_scan_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emails_inspected: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    candidates_found: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_analyzed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    relevant: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    qualified: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    not_relevant: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    below_threshold: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    sent_from_queue: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    event_counts: Mapped[str] = mapped_column(Text, default="{}", server_default="{}", nullable=False)
    mailbox_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_detection_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)


class GmailJob(Base):
    """Persistent payload used by Telegram cards and /reply_job."""

    __tablename__ = "gmail_jobs"

    stable_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_email_id: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    budget: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    urgency: Mapped[str] = mapped_column(String(20), nullable=False)
    why_relevant: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(50), default="queued", server_default="queued", nullable=False
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(50), default="PROJECT_SINGLE", server_default="PROJECT_SINGLE", nullable=False
    )
    full_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_completeness: Mapped[str] = mapped_column(
        String(20), default="PARTIAL", server_default="PARTIAL", nullable=False
    )
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    category: Mapped[str | None] = mapped_column(String(500), nullable=True)
    skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bid_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    client_profile_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    client_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_lane: Mapped[str | None] = mapped_column(String(500), nullable=True)
    executable: Mapped[str | None] = mapped_column(String(30), nullable=True)
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_probability_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_clarity: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_effort: Mapped[str | None] = mapped_column(String(500), nullable=True)
    delivery_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_payment_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    project_mode_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_price: Mapped[str | None] = mapped_column(String(500), nullable=True)
    realistic_timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selected_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_context: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mailbox_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sensitive_redacted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    live_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    live_status_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    live_status_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    biddable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    live_status_retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    live_status_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)


_MIGRATIONS = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_name TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_url TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS category TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS deadline TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS bid_count INTEGER",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_phone TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_telegram TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_email TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_checked_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_evidence TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS biddable BOOLEAN",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_last_error TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS qualified BOOLEAN NOT NULL DEFAULT FALSE",
    # create_all does not add columns to an already existing table. This is an
    # additive, data-preserving migration for early gmail_scan_runs deployments.
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS relevant INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS ai_analyzed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS qualified INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS sent_from_queue INTEGER NOT NULL DEFAULT 0",
    # A lease timestamp lets a later worker safely recover a job if a process
    # exits after claiming it but before recording the Telegram send result.
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'PROJECT_SINGLE'",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS full_description TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS description_completeness TEXT NOT NULL DEFAULT 'PARTIAL'",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS language TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS category TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS skills TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS deadline TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS bid_count INTEGER",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS client_name TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS client_profile_url TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS client_context TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS project_id TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS thread_id TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS service_lane TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS executable TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS fit_score DOUBLE PRECISION",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS win_probability_signal TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS scope_clarity TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS estimated_effort TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS delivery_risk TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS client_payment_risk TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS project_mode TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS project_mode_reason TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS recommended_price TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS realistic_timeline TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS selected_evidence TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS analysis_evidence TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS proposal_draft TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS needs_context BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS next_action TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS source_mailbox_alias TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS sensitive_redacted BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS live_status TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS live_status_checked_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS live_status_evidence TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS biddable BOOLEAN",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS live_status_retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS live_status_last_error TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS qualified BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS event_counts TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS mailbox_alias TEXT",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS max_detection_latency_seconds DOUBLE PRECISION",
]


async def init_db() -> None:
    from db import engine  # local import avoids circular reference at module level
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))
