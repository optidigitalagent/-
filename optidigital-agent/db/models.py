from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
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


_MIGRATIONS = [
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_name TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_url TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS category TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS deadline TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS bid_count INTEGER",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_phone TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_telegram TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS employer_email TEXT",
    # create_all does not add columns to an already existing table. This is an
    # additive, data-preserving migration for early gmail_scan_runs deployments.
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS relevant INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS ai_analyzed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS qualified INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS sent_from_queue INTEGER NOT NULL DEFAULT 0",
    # A lease timestamp lets a later worker safely recover a job if a process
    # exits after claiming it but before recording the Telegram send result.
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
]


async def init_db() -> None:
    from db import engine  # local import avoids circular reference at module level
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))
