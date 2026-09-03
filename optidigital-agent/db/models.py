from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    analysis_quality_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_repair_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    proposal_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    executable: Mapped[str | None] = mapped_column(String(30), nullable=True)

    responses: Mapped[list["Response"]] = relationship("Response", back_populates="order")


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_quality_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_job_identity: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validated_live_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    duplicate_source_pairs: Mapped[str] = mapped_column(
        Text, default="{}", server_default="{}", nullable=False
    )
    live_status_active: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    live_status_non_actionable: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    live_status_unknown: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    ai_calls_avoided: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_publication_to_telegram_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_valid: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quality_repaired: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quality_manual_review: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quality_non_executable: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    quality_failed: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    zero_score_blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    missing_price_blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    missing_proposal_blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    invalid_evidence_blocked: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    repair_calls: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    repair_successes: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    proposal_versions_sent: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)


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
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(20), nullable=True)
    discovery_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    discovery_sources: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_publication_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_feed_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feed_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publication_to_telegram_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    analysis_quality_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quality_errors: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_repair_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    proposal_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    analysis_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    money_terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline_terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_analysis_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_clarification_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_output_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_valid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    score_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_state: Mapped[str] = mapped_column(String(20), default="MISSING", server_default="MISSING", nullable=False)
    fit_score_valid: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    fit_score_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    fit_score_state: Mapped[str] = mapped_column(String(20), default="MISSING", server_default="MISSING", nullable=False)


class SalesOpportunity(Base):
    """One commercial workflow for one exact project/thread identity."""

    __tablename__ = "sales_opportunities"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    gmail_job_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    thread_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    reply_reference_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    client_name: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    source_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_completeness: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PARTIAL", server_default="PARTIAL"
    )
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, default="REVIEW", server_default="REVIEW"
    )
    live_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    competition_signal: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_price: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recommended_timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_case_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    initial_proposal: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposal_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    proposal_content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_submitted_price: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actual_submitted_timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bid_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_constraints_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    decisions_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    human_facts_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
    unresolved_questions_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    last_owner_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_client_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    follow_up_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    do_not_follow_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    follow_up_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="DISABLED_5A", server_default="DISABLED_5A"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_sales_opportunity_project_id"),
        UniqueConstraint("thread_id", name="uq_sales_opportunity_thread_id"),
    )


class OpportunityStateTransition(Base):
    __tablename__ = "opportunity_state_transitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    previous_state: Mapped[str] = mapped_column(String(50), nullable=False)
    new_state: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        Index("ix_opportunity_transitions_timeline", "opportunity_id", "timestamp"),
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(String(30), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_turn_identity: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    source_reference_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reply_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    intent: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    russian_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_ask: Mapped[str | None] = mapped_column(Text, nullable=True)
    negotiation_strategy: Mapped[str | None] = mapped_column(Text, nullable=True)
    risks: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_facts: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    telegram_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notification_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_conversation_turns_timeline", "opportunity_id", "created_at"),
        UniqueConstraint(
            "opportunity_id", "reply_version", name="uq_conversation_turn_reply_version"
        ),
    )


class OwnerActionConfirmation(Base):
    __tablename__ = "owner_action_confirmations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    actor: Mapped[str] = mapped_column(String(20), nullable=False)
    proposal_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reply_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    actual_price: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actual_timeline: Mapped[str | None] = mapped_column(String(500), nullable=True)
    response_latency_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_owner_confirmations_timeline", "opportunity_id", "confirmed_at"),
    )


class HumanInformationRequest(Base):
    __tablename__ = "human_information_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sales_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    source_turn_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversation_turns.id", ondelete="CASCADE"), nullable=False
    )
    fact_key: Mapped[str] = mapped_column(String(255), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN", server_default="OPEN")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    resulting_reply_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    answered_by: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        Index("ix_human_requests_open", "opportunity_id", "status"),
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
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_checked_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_evidence TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS biddable BOOLEAN",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS live_status_last_error TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS qualified BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS analysis_quality_status TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quality_checked_at TIMESTAMPTZ",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quality_errors TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS quality_repair_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS proposal_quality_score DOUBLE PRECISION",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS evidence_case_id TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS analysis_version TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS proposal_version TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS fit_score DOUBLE PRECISION",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS executable TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS proposal_version TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS proposal_content_sha256 TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS analysis_quality_status TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS quality_checked_at TIMESTAMPTZ",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS quality_errors TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS source_job_identity TEXT",
    "ALTER TABLE responses ADD COLUMN IF NOT EXISTS validated_live_status_at TIMESTAMPTZ",
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
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS tags TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS budget_currency TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS discovery_source TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS discovery_sources TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS source_publication_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS source_feed_timestamp TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS feed_fetched_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS telegram_sent_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS publication_to_telegram_latency_seconds DOUBLE PRECISION",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS analysis_quality_status TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS quality_checked_at TIMESTAMPTZ",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS quality_errors TEXT NOT NULL DEFAULT '[]'",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS quality_repair_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS proposal_quality_score DOUBLE PRECISION",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS evidence_case_id TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS analysis_version TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS proposal_version TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS proposal_content_sha256 TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS money_terms_json TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS timeline_terms_json TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS original_analysis_snapshot TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS quality_clarification_question TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS model_output_json TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS score_valid BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS score_raw TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS score_state TEXT NOT NULL DEFAULT 'MISSING'",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS fit_score_valid BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS fit_score_raw TEXT",
    "ALTER TABLE gmail_jobs ADD COLUMN IF NOT EXISTS fit_score_state TEXT NOT NULL DEFAULT 'MISSING'",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS duplicate_source_pairs TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS live_status_active INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS live_status_non_actionable INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS live_status_unknown INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS ai_calls_avoided INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS max_publication_to_telegram_latency_seconds DOUBLE PRECISION",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS quality_valid INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS quality_repaired INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS quality_manual_review INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS quality_non_executable INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS quality_failed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS zero_score_blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS missing_price_blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS missing_proposal_blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS invalid_evidence_blocked INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS repair_calls INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS repair_successes INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE gmail_scan_runs ADD COLUMN IF NOT EXISTS proposal_versions_sent INTEGER NOT NULL DEFAULT 0",
    # Stage 5A is additive. create_all creates the new sales tables; these
    # guards also make repeat deploys and an early/partial schema restart-safe.
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS last_owner_message_at TIMESTAMPTZ",
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS last_client_message_at TIMESTAMPTZ",
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS follow_up_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS next_follow_up_at TIMESTAMPTZ",
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS do_not_follow_up BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE sales_opportunities ADD COLUMN IF NOT EXISTS follow_up_status TEXT NOT NULL DEFAULT 'DISABLED_5A'",
    "ALTER TABLE conversation_turns ADD COLUMN IF NOT EXISTS telegram_notified_at TIMESTAMPTZ",
    "ALTER TABLE conversation_turns ADD COLUMN IF NOT EXISTS notification_due_at TIMESTAMPTZ",
    "CREATE INDEX IF NOT EXISTS ix_sales_opportunities_project_id ON sales_opportunities (project_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_opportunities_thread_id ON sales_opportunities (thread_id)",
    "CREATE INDEX IF NOT EXISTS ix_sales_opportunities_state ON sales_opportunities (state)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_opportunity_project_id ON sales_opportunities (project_id) WHERE project_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_opportunity_thread_id ON sales_opportunities (thread_id) WHERE thread_id IS NOT NULL",
]


async def init_db() -> None:
    from db import engine  # local import avoids circular reference at module level
    from sqlalchemy import text

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in _MIGRATIONS:
            await conn.execute(text(stmt))
