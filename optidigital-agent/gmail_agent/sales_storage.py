"""Restart-safe persistence contracts for the Stage 5A sales closer.

The module deliberately contains no platform-send capability.  It stores the
commercial context, dialogue history, owner confirmations and human facts
needed to prepare copy-ready text for an adult account owner.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OpportunityState(StrEnum):
    DISCOVERED = "DISCOVERED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    PROPOSAL_READY = "PROPOSAL_READY"
    BID_SUBMITTED = "BID_SUBMITTED"
    CLIENT_REPLIED = "CLIENT_REPLIED"
    NEEDS_CONTEXT = "NEEDS_CONTEXT"
    NEEDS_HUMAN_INPUT = "NEEDS_HUMAN_INPUT"
    NEGOTIATING = "NEGOTIATING"
    WAITING_CLIENT = "WAITING_CLIENT"
    SELECTION_REVIEW = "SELECTION_REVIEW"
    CONTRACT_REVIEW = "CONTRACT_REVIEW"
    SELECTED = "SELECTED"
    HANDOFF_READY = "HANDOFF_READY"
    LOST = "LOST"
    CLOSED = "CLOSED"


VALID_ACTORS = {"system", "adult_owner", "Artem", "Vadim"}

TERMINAL_STATES = frozenset(
    {
        OpportunityState.LOST.value,
        OpportunityState.CLOSED.value,
        OpportunityState.SELECTED.value,
        OpportunityState.HANDOFF_READY.value,
    }
)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    OpportunityState.DISCOVERED.value: frozenset(
        {OpportunityState.MANUAL_REVIEW.value, OpportunityState.PROPOSAL_READY.value,
         OpportunityState.NEEDS_CONTEXT.value}
    ),
    OpportunityState.MANUAL_REVIEW.value: frozenset(
        {OpportunityState.PROPOSAL_READY.value, OpportunityState.NEEDS_CONTEXT.value,
         OpportunityState.NEEDS_HUMAN_INPUT.value, OpportunityState.NEGOTIATING.value,
         OpportunityState.LOST.value, OpportunityState.CLOSED.value}
    ),
    OpportunityState.PROPOSAL_READY.value: frozenset(
        {OpportunityState.BID_SUBMITTED.value, OpportunityState.MANUAL_REVIEW.value,
         OpportunityState.NEEDS_CONTEXT.value, OpportunityState.CLOSED.value}
    ),
    OpportunityState.BID_SUBMITTED.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.CLIENT_REPLIED.value: frozenset(
        {OpportunityState.NEEDS_CONTEXT.value, OpportunityState.NEEDS_HUMAN_INPUT.value,
         OpportunityState.NEGOTIATING.value, OpportunityState.SELECTION_REVIEW.value,
         OpportunityState.CONTRACT_REVIEW.value, OpportunityState.MANUAL_REVIEW.value,
         OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.NEEDS_CONTEXT.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.NEEDS_HUMAN_INPUT.value,
         OpportunityState.NEGOTIATING.value, OpportunityState.SELECTION_REVIEW.value,
         OpportunityState.CONTRACT_REVIEW.value, OpportunityState.MANUAL_REVIEW.value,
         OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.NEEDS_HUMAN_INPUT.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.NEGOTIATING.value,
         OpportunityState.SELECTION_REVIEW.value, OpportunityState.CONTRACT_REVIEW.value,
         OpportunityState.MANUAL_REVIEW.value, OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.NEGOTIATING.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.NEEDS_CONTEXT.value,
         OpportunityState.NEEDS_HUMAN_INPUT.value, OpportunityState.WAITING_CLIENT.value,
         OpportunityState.SELECTION_REVIEW.value, OpportunityState.CONTRACT_REVIEW.value,
         OpportunityState.MANUAL_REVIEW.value, OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.WAITING_CLIENT.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.SELECTION_REVIEW.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.WAITING_CLIENT.value,
         OpportunityState.CONTRACT_REVIEW.value, OpportunityState.MANUAL_REVIEW.value,
         OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.CONTRACT_REVIEW.value: frozenset(
        {OpportunityState.CLIENT_REPLIED.value, OpportunityState.WAITING_CLIENT.value,
         OpportunityState.MANUAL_REVIEW.value, OpportunityState.LOST.value,
         OpportunityState.CLOSED.value}
    ),
    OpportunityState.SELECTED.value: frozenset(),
    OpportunityState.HANDOFF_READY.value: frozenset(),
    OpportunityState.LOST.value: frozenset(),
    OpportunityState.CLOSED.value: frozenset(),
}


class IllegalTransitionError(RuntimeError):
    pass


class StaleReplyError(RuntimeError):
    def __init__(self, latest_incoming_turn_id: str, opportunity_id: str) -> None:
        self.latest_incoming_turn_id = latest_incoming_turn_id
        self.regeneration_command = f"/regenerate_lead {opportunity_id}"
        super().__init__(
            "reply is stale; latest incoming turn is "
            f"{latest_incoming_turn_id}; regenerate with {self.regeneration_command}"
        )


@dataclass(slots=True)
class SalesOpportunity:
    id: str
    identity_key: str
    title: str
    state: str = OpportunityState.DISCOVERED.value
    source: str = "system"
    gmail_job_key: str = ""
    project_id: str = ""
    thread_id: str = ""
    project_url: str = ""
    thread_url: str = ""
    reply_reference_id: str = ""
    client_name: str = ""
    source_description: str = ""
    description_completeness: str = "PARTIAL"
    decision: str = "REVIEW"
    live_status: str = ""
    score: float | None = None
    fit_score: float | None = None
    competition_signal: str = ""
    recommended_price: str = ""
    recommended_timeline: str = ""
    risks: str = ""
    approved_evidence: str = ""
    evidence_case_id: str = ""
    initial_proposal: str = ""
    proposal_version: str = ""
    proposal_content_sha256: str = ""
    actual_submitted_price: str = ""
    actual_submitted_timeline: str = ""
    actual_submitted_price_raw: str = ""
    actual_submitted_timeline_raw: str = ""
    actual_submitted_money_json: str = ""
    actual_submitted_timeline_json: str = ""
    bid_submitted_at: datetime | None = None
    next_reply_sequence: int = 1
    client_constraints_json: str = "[]"
    decisions_json: str = "[]"
    human_facts_json: str = "{}"
    unresolved_questions_json: str = "[]"
    last_owner_message_at: datetime | None = None
    last_client_message_at: datetime | None = None
    follow_up_count: int = 0
    next_follow_up_at: datetime | None = None
    do_not_follow_up: bool = False
    follow_up_status: str = "DISABLED_5A"
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def human_facts(self) -> dict[str, str]:
        try:
            value = json.loads(self.human_facts_json or "{}")
            return {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}


@dataclass(slots=True)
class OpportunityTransition:
    id: str
    opportunity_id: str
    timestamp: datetime
    source: str
    previous_state: str
    new_state: str
    reason: str
    actor: str
    actor_role: str = "SYSTEM"
    actor_telegram_user_id: int | None = None


@dataclass(slots=True)
class ConversationTurn:
    id: str
    opportunity_id: str
    direction: str
    content: str
    content_sha256: str
    canonical_turn_identity: str
    gmail_message_id: str = ""
    source_reference_id: str = ""
    reply_version: str = ""
    incoming_gmail_message_id: str = ""
    incoming_canonical_identity: str = ""
    source: str = "GMAIL"
    language: str = ""
    intent: str = "UNKNOWN"
    russian_summary: str = ""
    actual_ask: str = ""
    negotiation_strategy: str = ""
    risks: str = ""
    missing_facts: str = ""
    source_received_at: datetime | None = None
    detected_at: datetime | None = None
    response_latency_seconds: float | None = None
    telegram_notified_at: datetime | None = None
    notification_due_at: datetime | None = None
    generated_at: datetime | None = None
    sent_at: datetime | None = None
    imported_at: datetime | None = None
    imported_by_role: str = ""
    imported_by_telegram_user_id: int | None = None
    acknowledged_at: datetime | None = None
    acknowledged_by_role: str = ""
    acknowledged_by_telegram_user_id: int | None = None
    escalation_due_at: datetime | None = None
    escalation_count: int = 0
    alert_state: str = "NOT_SENT"
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class OwnerActionConfirmation:
    id: str
    opportunity_id: str
    action: str
    idempotency_key: str
    actor: str
    actor_role: str
    actor_telegram_user_id: int
    proposal_version: str = ""
    reply_version: str = ""
    content_sha256: str = ""
    actual_price: str = ""
    actual_timeline: str = ""
    actual_price_raw: str = ""
    actual_timeline_raw: str = ""
    money_terms_json: str = ""
    timeline_terms_json: str = ""
    response_latency_seconds: float | None = None
    confirmed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class HumanInformationRequest:
    id: str
    opportunity_id: str
    source_turn_id: str
    fact_key: str
    intent: str
    subject_fingerprint: str
    question: str
    status: str = "OPEN"
    answer: str = ""
    answer_code: str = ""
    answer_text: str = ""
    canonical_money_json: str = ""
    canonical_timeline_json: str = ""
    approved_availability_json: str = ""
    approved_evidence_case_id: str = ""
    resulting_reply_version: str = ""
    asked_at: datetime = field(default_factory=utc_now)
    answered_at: datetime | None = None
    answered_by: str = ""
    answered_by_role: str = ""
    answered_by_telegram_user_id: int | None = None


@dataclass(slots=True)
class LeadContextSync:
    id: str
    opportunity_id: str
    status: str
    requested_at: datetime
    requested_by_role: str
    requested_by_telegram_user_id: int
    imported_at: datetime | None = None
    content_sha256: str = ""
    redaction_applied: bool = False


@dataclass(frozen=True, slots=True)
class OpportunityResolution:
    opportunity: SalesOpportunity | None
    basis: str
    ambiguous: bool = False


class SalesRepository(Protocol):
    async def ensure_opportunity(
        self, opportunity: SalesOpportunity, *, reason: str, actor: str
    ) -> tuple[SalesOpportunity, bool]: ...

    async def get_opportunity(self, opportunity_id: str) -> SalesOpportunity | None: ...

    async def update_opportunity_fields(
        self, opportunity_id: str, fields: dict[str, Any]
    ) -> SalesOpportunity | None: ...

    async def transition(
        self,
        opportunity_id: str,
        new_state: str,
        *,
        source: str,
        reason: str,
        actor: str,
        actor_role: str = "SYSTEM",
        actor_telegram_user_id: int | None = None,
    ) -> SalesOpportunity: ...

    async def confirm_bid(
        self,
        opportunity_id: str,
        confirmation: OwnerActionConfirmation,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]: ...

    async def confirm_reply(
        self,
        opportunity_id: str,
        reply_version: str,
        *,
        actor: str,
        actor_role: str,
        actor_telegram_user_id: int,
        confirmed_at: datetime,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]: ...

    async def allocate_reply_version(self, opportunity_id: str) -> str: ...

    async def resolve_opportunity(
        self,
        *,
        thread_id: str = "",
        project_id: str = "",
        project_url: str = "",
        reply_reference_id: str = "",
        client_name: str = "",
    ) -> OpportunityResolution: ...

    async def add_turn(self, turn: ConversationTurn) -> tuple[ConversationTurn, bool]: ...

    async def add_reply_draft_if_current(
        self, turn: ConversationTurn
    ) -> tuple[ConversationTurn, bool]: ...

    async def get_turn(self, turn_id: str) -> ConversationTurn | None: ...

    async def update_turn_fields(
        self, turn_id: str, fields: dict[str, Any]
    ) -> ConversationTurn | None: ...

    async def list_turns(self, opportunity_id: str) -> list[ConversationTurn]: ...

    async def list_pending_incoming_turns(self, now: datetime) -> list[ConversationTurn]: ...

    async def mark_turn_notified(self, turn_id: str, at: datetime) -> ConversationTurn | None: ...

    async def acknowledge_turn(
        self, turn_id: str, *, at: datetime, actor_role: str,
        actor_telegram_user_id: int,
    ) -> ConversationTurn | None: ...

    async def list_pending_escalations(self, now: datetime) -> list[ConversationTurn]: ...

    async def mark_turn_escalated(self, turn_id: str, at: datetime) -> ConversationTurn | None: ...

    async def add_confirmation(
        self, confirmation: OwnerActionConfirmation
    ) -> tuple[OwnerActionConfirmation, bool]: ...

    async def get_confirmation_by_key(
        self, idempotency_key: str
    ) -> OwnerActionConfirmation | None: ...

    async def create_human_request(
        self, request: HumanInformationRequest
    ) -> tuple[HumanInformationRequest, bool]: ...

    async def get_human_request(self, request_id: str) -> HumanInformationRequest | None: ...

    async def update_human_request(
        self, request_id: str, fields: dict[str, Any]
    ) -> HumanInformationRequest | None: ...

    async def list_human_requests(self, opportunity_id: str) -> list[HumanInformationRequest]: ...

    async def list_transitions(self, opportunity_id: str) -> list[OpportunityTransition]: ...

    async def list_opportunities(self) -> list[SalesOpportunity]: ...

    async def pipeline_counts(self) -> dict[str, int]: ...

    async def create_context_sync(
        self, sync: LeadContextSync
    ) -> tuple[LeadContextSync, bool]: ...

    async def get_pending_context_sync(
        self, actor_telegram_user_id: int
    ) -> LeadContextSync | None: ...

    async def update_context_sync(
        self, sync_id: str, fields: dict[str, Any]
    ) -> LeadContextSync | None: ...


class InMemorySalesRepository:
    """Deterministic repository whose shared state simulates a restart."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state if state is not None else {}
        self.state.setdefault("opportunities", {})
        self.state.setdefault("transitions", {})
        self.state.setdefault("turns", {})
        self.state.setdefault("confirmations", {})
        self.state.setdefault("requests", {})
        self.state.setdefault("context_syncs", {})

    async def ensure_opportunity(
        self, opportunity: SalesOpportunity, *, reason: str, actor: str
    ) -> tuple[SalesOpportunity, bool]:
        _validate_actor(actor)
        for existing in self.state["opportunities"].values():
            if existing.identity_key == opportunity.identity_key:
                return replace(existing), False
        self.state["opportunities"][opportunity.id] = replace(opportunity)
        transition = OpportunityTransition(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            timestamp=opportunity.created_at,
            source=opportunity.source,
            previous_state="",
            new_state=opportunity.state,
            reason=reason,
            actor=actor,
            actor_role=_actor_role(actor),
        )
        self.state["transitions"][transition.id] = transition
        return replace(opportunity), True

    async def get_opportunity(self, opportunity_id: str) -> SalesOpportunity | None:
        item = self.state["opportunities"].get(opportunity_id)
        return replace(item) if item else None

    async def update_opportunity_fields(
        self, opportunity_id: str, fields: dict[str, Any]
    ) -> SalesOpportunity | None:
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            return None
        allowed = set(SalesOpportunity.__dataclass_fields__) - {"id", "identity_key", "created_at"}
        for key, value in fields.items():
            if key in allowed:
                setattr(item, key, value)
        item.updated_at = utc_now()
        return replace(item)

    async def transition(
        self,
        opportunity_id: str,
        new_state: str,
        *,
        source: str,
        reason: str,
        actor: str,
        actor_role: str = "SYSTEM",
        actor_telegram_user_id: int | None = None,
    ) -> SalesOpportunity:
        _validate_actor(actor)
        _validate_state(new_state)
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            raise KeyError(opportunity_id)
        if item.state == new_state:
            return replace(item)
        _validate_transition(item.state, new_state)
        transition = OpportunityTransition(
            id=uuid4().hex,
            opportunity_id=opportunity_id,
            timestamp=utc_now(),
            source=source,
            previous_state=item.state,
            new_state=new_state,
            reason=reason,
            actor=actor,
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        item.state = new_state
        item.updated_at = transition.timestamp
        self.state["transitions"][transition.id] = transition
        return replace(item)

    async def confirm_bid(
        self,
        opportunity_id: str,
        confirmation: OwnerActionConfirmation,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            raise KeyError(opportunity_id)
        existing = await self.get_confirmation_by_key(confirmation.idempotency_key)
        if existing:
            if (
                existing.actual_price != confirmation.actual_price
                or existing.actual_timeline != confirmation.actual_timeline
                or existing.actor_telegram_user_id != confirmation.actor_telegram_user_id
            ):
                raise ValueError("bid confirmation conflicts with the persisted confirmation")
            return replace(item), existing, False
        _verify_bid_confirmation(item, confirmation)
        _validate_transition(item.state, OpportunityState.BID_SUBMITTED.value)
        self.state["confirmations"][confirmation.id] = replace(confirmation)
        item.actual_submitted_price = confirmation.actual_price
        item.actual_submitted_timeline = confirmation.actual_timeline
        item.actual_submitted_price_raw = confirmation.actual_price_raw
        item.actual_submitted_timeline_raw = confirmation.actual_timeline_raw
        item.actual_submitted_money_json = confirmation.money_terms_json
        item.actual_submitted_timeline_json = confirmation.timeline_terms_json
        item.bid_submitted_at = confirmation.confirmed_at
        item.last_owner_message_at = confirmation.confirmed_at
        previous = item.state
        item.state = OpportunityState.BID_SUBMITTED.value
        item.updated_at = confirmation.confirmed_at
        transition = OpportunityTransition(
            id=uuid4().hex,
            opportunity_id=item.id,
            timestamp=confirmation.confirmed_at,
            source="telegram:/mark_bid_sent",
            previous_state=previous,
            new_state=item.state,
            reason=(
                "authorized adult owner confirmed the exact current proposal version/hash "
                "and canonical submitted terms"
            ),
            actor=confirmation.actor,
            actor_role=confirmation.actor_role,
            actor_telegram_user_id=confirmation.actor_telegram_user_id,
        )
        self.state["transitions"][transition.id] = transition
        return replace(item), replace(confirmation), True

    async def confirm_reply(
        self,
        opportunity_id: str,
        reply_version: str,
        *,
        actor: str,
        actor_role: str,
        actor_telegram_user_id: int,
        confirmed_at: datetime,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            raise KeyError(opportunity_id)
        turns = [
            value for value in self.state["turns"].values()
            if value.opportunity_id == opportunity_id
        ]
        turns.sort(key=lambda value: (value.created_at, value.id))
        latest_incoming = next(
            (value for value in reversed(turns) if value.direction == "INCOMING"), None
        )
        draft = next((value for value in turns if value.reply_version == reply_version), None)
        if draft is None:
            raise ValueError("exact reply version not found")
        key = f"REPLY_SENT:{opportunity_id}:{reply_version}:{draft.content_sha256}"
        existing = await self.get_confirmation_by_key(key)
        if existing:
            return replace(item), existing, False
        _verify_current_reply(item, draft, latest_incoming, turns)
        latency = _reply_latency(latest_incoming, confirmed_at)
        confirmation = OwnerActionConfirmation(
            id=uuid4().hex,
            opportunity_id=opportunity_id,
            action="REPLY_SENT",
            idempotency_key=key,
            actor=actor,
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
            reply_version=reply_version,
            content_sha256=draft.content_sha256,
            response_latency_seconds=latency,
            confirmed_at=confirmed_at,
        )
        self.state["confirmations"][confirmation.id] = confirmation
        draft.direction = "OUTGOING_CONFIRMED"
        draft.sent_at = confirmed_at
        draft.response_latency_seconds = latency
        if latest_incoming:
            latest_incoming.acknowledged_at = confirmed_at
            latest_incoming.acknowledged_by_role = actor_role
            latest_incoming.acknowledged_by_telegram_user_id = actor_telegram_user_id
            latest_incoming.alert_state = "RESOLVED"
        _validate_transition(item.state, OpportunityState.WAITING_CLIENT.value)
        previous = item.state
        item.state = OpportunityState.WAITING_CLIENT.value
        item.last_owner_message_at = confirmed_at
        item.updated_at = confirmed_at
        transition = OpportunityTransition(
            id=uuid4().hex,
            opportunity_id=opportunity_id,
            timestamp=confirmed_at,
            source="telegram:/mark_reply_sent",
            previous_state=previous,
            new_state=item.state,
            reason=f"authorized adult owner confirmed exact current reply {reply_version}",
            actor=actor,
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        self.state["transitions"][transition.id] = transition
        return replace(item), replace(confirmation), True

    async def allocate_reply_version(self, opportunity_id: str) -> str:
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            raise KeyError(opportunity_id)
        sequence = item.next_reply_sequence
        item.next_reply_sequence += 1
        item.updated_at = utc_now()
        return f"r{sequence}"

    async def resolve_opportunity(
        self,
        *,
        thread_id: str = "",
        project_id: str = "",
        project_url: str = "",
        reply_reference_id: str = "",
        client_name: str = "",
    ) -> OpportunityResolution:
        items = list(self.state["opportunities"].values())
        return _resolve_items(
            items,
            thread_id=thread_id,
            project_id=project_id,
            project_url=project_url,
            reply_reference_id=reply_reference_id,
            client_name=client_name,
        )

    async def add_turn(self, turn: ConversationTurn) -> tuple[ConversationTurn, bool]:
        for existing in self.state["turns"].values():
            if (
                turn.gmail_message_id
                and existing.gmail_message_id == turn.gmail_message_id
            ) or existing.canonical_turn_identity == turn.canonical_turn_identity:
                return replace(existing), False
        self.state["turns"][turn.id] = replace(turn)
        return replace(turn), True

    async def add_reply_draft_if_current(
        self, turn: ConversationTurn
    ) -> tuple[ConversationTurn, bool]:
        if turn.direction != "OUTGOING_DRAFT":
            raise ValueError("reply draft must start as OUTGOING_DRAFT")
        turns = sorted(
            (
                value
                for value in self.state["turns"].values()
                if value.opportunity_id == turn.opportunity_id
            ),
            key=lambda value: (value.created_at, value.id),
        )
        latest_incoming = next(
            (value for value in reversed(turns) if value.direction == "INCOMING"), None
        )
        current = bool(
            latest_incoming
            and turn.source_reference_id == latest_incoming.id
            and turn.incoming_gmail_message_id == latest_incoming.gmail_message_id
            and turn.incoming_canonical_identity
            == latest_incoming.canonical_turn_identity
        )
        if current:
            for existing in turns:
                if existing.direction == "OUTGOING_DRAFT":
                    existing.direction = "OUTGOING_SUPERSEDED"
        else:
            turn.direction = "OUTGOING_SUPERSEDED"
        return await self.add_turn(turn)

    async def get_turn(self, turn_id: str) -> ConversationTurn | None:
        item = self.state["turns"].get(turn_id)
        return replace(item) if item else None

    async def update_turn_fields(
        self, turn_id: str, fields: dict[str, Any]
    ) -> ConversationTurn | None:
        item = self.state["turns"].get(turn_id)
        if item is None:
            return None
        allowed = set(ConversationTurn.__dataclass_fields__) - {
            "id", "opportunity_id", "created_at", "canonical_turn_identity"
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(item, key, value)
        return replace(item)

    async def list_turns(self, opportunity_id: str) -> list[ConversationTurn]:
        return [
            replace(item)
            for item in sorted(
                (
                    value
                    for value in self.state["turns"].values()
                    if value.opportunity_id == opportunity_id
                ),
                key=lambda value: value.created_at,
            )
        ]

    async def list_pending_incoming_turns(self, now: datetime) -> list[ConversationTurn]:
        return [
            replace(item)
            for item in sorted(self.state["turns"].values(), key=lambda value: value.created_at)
            if item.direction == "INCOMING"
            and item.telegram_notified_at is None
            and (item.notification_due_at is None or item.notification_due_at <= now)
        ]

    async def mark_turn_notified(self, turn_id: str, at: datetime) -> ConversationTurn | None:
        item = self.state["turns"].get(turn_id)
        if item is None:
            return None
        item.telegram_notified_at = at
        if item.acknowledged_at is None:
            item.escalation_due_at = _working_window_due(at + timedelta(minutes=5))
            item.alert_state = "ACK_PENDING"
        return replace(item)

    async def acknowledge_turn(
        self,
        turn_id: str,
        *,
        at: datetime,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> ConversationTurn | None:
        item = self.state["turns"].get(turn_id)
        if item is None or item.direction != "INCOMING":
            return None
        item.acknowledged_at = at
        item.acknowledged_by_role = actor_role
        item.acknowledged_by_telegram_user_id = actor_telegram_user_id
        item.alert_state = "ACKNOWLEDGED"
        return replace(item)

    async def list_pending_escalations(self, now: datetime) -> list[ConversationTurn]:
        return [
            replace(item)
            for item in sorted(self.state["turns"].values(), key=lambda value: value.created_at)
            if item.direction == "INCOMING"
            and item.alert_state == "ACK_PENDING"
            and item.acknowledged_at is None
            and item.escalation_count == 0
            and item.escalation_due_at is not None
            and item.escalation_due_at <= now
        ]

    async def mark_turn_escalated(
        self, turn_id: str, at: datetime
    ) -> ConversationTurn | None:
        item = self.state["turns"].get(turn_id)
        if item is None:
            return None
        if item.acknowledged_at is None and item.escalation_count == 0:
            item.escalation_count = 1
            item.alert_state = "ESCALATED"
        return replace(item)

    async def add_confirmation(
        self, confirmation: OwnerActionConfirmation
    ) -> tuple[OwnerActionConfirmation, bool]:
        existing = await self.get_confirmation_by_key(confirmation.idempotency_key)
        if existing:
            return existing, False
        self.state["confirmations"][confirmation.id] = replace(confirmation)
        return replace(confirmation), True

    async def get_confirmation_by_key(
        self, idempotency_key: str
    ) -> OwnerActionConfirmation | None:
        for item in self.state["confirmations"].values():
            if item.idempotency_key == idempotency_key:
                return replace(item)
        return None

    async def create_human_request(
        self, request: HumanInformationRequest
    ) -> tuple[HumanInformationRequest, bool]:
        for existing in self.state["requests"].values():
            if (
                existing.opportunity_id == request.opportunity_id
                and existing.source_turn_id == request.source_turn_id
                and existing.fact_key == request.fact_key
                and existing.status == "OPEN"
            ):
                return replace(existing), False
        self.state["requests"][request.id] = replace(request)
        return replace(request), True

    async def get_human_request(self, request_id: str) -> HumanInformationRequest | None:
        item = self.state["requests"].get(request_id)
        return replace(item) if item else None

    async def update_human_request(
        self, request_id: str, fields: dict[str, Any]
    ) -> HumanInformationRequest | None:
        item = self.state["requests"].get(request_id)
        if item is None:
            return None
        allowed = set(HumanInformationRequest.__dataclass_fields__) - {"id", "opportunity_id", "asked_at"}
        for key, value in fields.items():
            if key in allowed:
                setattr(item, key, value)
        return replace(item)

    async def list_human_requests(self, opportunity_id: str) -> list[HumanInformationRequest]:
        return [
            replace(item)
            for item in sorted(self.state["requests"].values(), key=lambda value: value.asked_at)
            if item.opportunity_id == opportunity_id
        ]

    async def list_transitions(self, opportunity_id: str) -> list[OpportunityTransition]:
        return [
            replace(item)
            for item in sorted(self.state["transitions"].values(), key=lambda value: value.timestamp)
            if item.opportunity_id == opportunity_id
        ]

    async def list_opportunities(self) -> list[SalesOpportunity]:
        return [
            replace(item)
            for item in sorted(self.state["opportunities"].values(), key=lambda value: value.created_at)
        ]

    async def pipeline_counts(self) -> dict[str, int]:
        counts = {state.value: 0 for state in OpportunityState}
        for item in self.state["opportunities"].values():
            counts[item.state] = counts.get(item.state, 0) + 1
        return counts

    async def create_context_sync(
        self, sync: LeadContextSync
    ) -> tuple[LeadContextSync, bool]:
        for item in self.state["context_syncs"].values():
            if (
                item.requested_by_telegram_user_id == sync.requested_by_telegram_user_id
                and item.status == "PENDING"
            ):
                return replace(item), False
        self.state["context_syncs"][sync.id] = replace(sync)
        return replace(sync), True

    async def get_pending_context_sync(
        self, actor_telegram_user_id: int
    ) -> LeadContextSync | None:
        matches = [
            item for item in self.state["context_syncs"].values()
            if item.requested_by_telegram_user_id == actor_telegram_user_id
            and item.status == "PENDING"
        ]
        matches.sort(key=lambda item: item.requested_at)
        return replace(matches[-1]) if matches else None

    async def update_context_sync(
        self, sync_id: str, fields: dict[str, Any]
    ) -> LeadContextSync | None:
        item = self.state["context_syncs"].get(sync_id)
        if item is None:
            return None
        allowed = set(LeadContextSync.__dataclass_fields__) - {
            "id", "opportunity_id", "requested_at", "requested_by_role",
            "requested_by_telegram_user_id",
        }
        for key, value in fields.items():
            if key in allowed:
                setattr(item, key, value)
        return replace(item)


class PostgresSalesRepository:
    """Additive PostgreSQL implementation used by production entry points."""

    def __init__(self, session_factory: Any) -> None:
        from db.models import (
            ConversationTurn as ConversationTurnModel,
        )
        from db.models import (
            HumanInformationRequest as HumanInformationRequestModel,
        )
        from db.models import LeadContextSync as LeadContextSyncModel
        from db.models import (
            OpportunityStateTransition,
        )
        from db.models import (
            OwnerActionConfirmation as OwnerActionConfirmationModel,
        )
        from db.models import (
            SalesOpportunity as SalesOpportunityModel,
        )

        self._session_factory = session_factory
        self._opportunity_model = SalesOpportunityModel
        self._transition_model = OpportunityStateTransition
        self._turn_model = ConversationTurnModel
        self._confirmation_model = OwnerActionConfirmationModel
        self._request_model = HumanInformationRequestModel
        self._context_sync_model = LeadContextSyncModel

    async def ensure_opportunity(
        self, opportunity: SalesOpportunity, *, reason: str, actor: str
    ) -> tuple[SalesOpportunity, bool]:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert

        _validate_actor(actor)
        values = _model_values(opportunity)
        async with self._session_factory() as session:
            statement = (
                insert(self._opportunity_model)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["identity_key"])
                .returning(self._opportunity_model.id)
            )
            created_id = (await session.execute(statement)).scalar_one_or_none()
            if created_id:
                session.add(
                    self._transition_model(
                        id=uuid4().hex,
                        opportunity_id=opportunity.id,
                        timestamp=opportunity.created_at,
                        source=opportunity.source,
                        previous_state="",
                        new_state=opportunity.state,
                        reason=reason,
                        actor=actor,
                        actor_role=_actor_role(actor),
                    )
                )
            result = await session.execute(
                select(self._opportunity_model).where(
                    self._opportunity_model.identity_key == opportunity.identity_key
                )
            )
            row = result.scalar_one()
            await session.commit()
            return _opportunity_from_row(row), bool(created_id)

    async def get_opportunity(self, opportunity_id: str) -> SalesOpportunity | None:
        async with self._session_factory() as session:
            row = await session.get(self._opportunity_model, opportunity_id)
            return _opportunity_from_row(row) if row else None

    async def update_opportunity_fields(
        self, opportunity_id: str, fields: dict[str, Any]
    ) -> SalesOpportunity | None:
        from sqlalchemy import update

        allowed = set(SalesOpportunity.__dataclass_fields__) - {"id", "identity_key", "created_at"}
        values = {key: value for key, value in fields.items() if key in allowed}
        values["updated_at"] = utc_now()
        async with self._session_factory() as session:
            result = await session.execute(
                update(self._opportunity_model)
                .where(self._opportunity_model.id == opportunity_id)
                .values(**values)
                .returning(self._opportunity_model)
            )
            row = result.scalar_one_or_none()
            await session.commit()
            return _opportunity_from_row(row) if row else None

    async def transition(
        self,
        opportunity_id: str,
        new_state: str,
        *,
        source: str,
        reason: str,
        actor: str,
        actor_role: str = "SYSTEM",
        actor_telegram_user_id: int | None = None,
    ) -> SalesOpportunity:
        from sqlalchemy import select

        _validate_actor(actor)
        _validate_state(new_state)
        async with self._session_factory() as session:
            result = await session.execute(
                select(self._opportunity_model)
                .where(self._opportunity_model.id == opportunity_id)
                .with_for_update()
            )
            row = result.scalar_one_or_none()
            if row is None:
                raise KeyError(opportunity_id)
            if row.state != new_state:
                _validate_transition(row.state, new_state)
                at = utc_now()
                session.add(
                    self._transition_model(
                        id=uuid4().hex,
                        opportunity_id=opportunity_id,
                        timestamp=at,
                        source=source,
                        previous_state=row.state,
                        new_state=new_state,
                        reason=reason,
                        actor=actor,
                        actor_role=actor_role,
                        actor_telegram_user_id=actor_telegram_user_id,
                    )
                )
                row.state = new_state
                row.updated_at = at
            await session.commit()
            return _opportunity_from_row(row)

    async def confirm_bid(
        self,
        opportunity_id: str,
        confirmation: OwnerActionConfirmation,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        from sqlalchemy import select

        _validate_actor(confirmation.actor)
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(self._opportunity_model)
                    .where(self._opportunity_model.id == opportunity_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                raise KeyError(opportunity_id)
            existing_row = (
                await session.execute(
                    select(self._confirmation_model).where(
                        self._confirmation_model.idempotency_key
                        == confirmation.idempotency_key
                    )
                )
            ).scalar_one_or_none()
            if existing_row is not None:
                existing = _confirmation_from_row(existing_row)
                if (
                    existing.actual_price != confirmation.actual_price
                    or existing.actual_timeline != confirmation.actual_timeline
                    or existing.actor_telegram_user_id
                    != confirmation.actor_telegram_user_id
                ):
                    raise ValueError(
                        "bid confirmation conflicts with the persisted confirmation"
                    )
                return _opportunity_from_row(row), existing, False
            opportunity = _opportunity_from_row(row)
            _verify_bid_confirmation(opportunity, confirmation)
            _validate_transition(opportunity.state, OpportunityState.BID_SUBMITTED.value)
            session.add(self._confirmation_model(**_model_values(confirmation)))
            row.actual_submitted_price = confirmation.actual_price
            row.actual_submitted_timeline = confirmation.actual_timeline
            row.actual_submitted_price_raw = confirmation.actual_price_raw
            row.actual_submitted_timeline_raw = confirmation.actual_timeline_raw
            row.actual_submitted_money_json = confirmation.money_terms_json
            row.actual_submitted_timeline_json = confirmation.timeline_terms_json
            row.bid_submitted_at = confirmation.confirmed_at
            row.last_owner_message_at = confirmation.confirmed_at
            previous = row.state
            row.state = OpportunityState.BID_SUBMITTED.value
            row.updated_at = confirmation.confirmed_at
            session.add(
                self._transition_model(
                    id=uuid4().hex,
                    opportunity_id=opportunity_id,
                    timestamp=confirmation.confirmed_at,
                    source="telegram:/mark_bid_sent",
                    previous_state=previous,
                    new_state=row.state,
                    reason=(
                        "authorized adult owner confirmed the exact current proposal "
                        "version/hash and canonical submitted terms"
                    ),
                    actor=confirmation.actor,
                    actor_role=confirmation.actor_role,
                    actor_telegram_user_id=confirmation.actor_telegram_user_id,
                )
            )
            await session.commit()
            return _opportunity_from_row(row), confirmation, True

    async def confirm_reply(
        self,
        opportunity_id: str,
        reply_version: str,
        *,
        actor: str,
        actor_role: str,
        actor_telegram_user_id: int,
        confirmed_at: datetime,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        from sqlalchemy import select

        _validate_actor(actor)
        async with self._session_factory() as session:
            opportunity_row = (
                await session.execute(
                    select(self._opportunity_model)
                    .where(self._opportunity_model.id == opportunity_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if opportunity_row is None:
                raise KeyError(opportunity_id)
            turn_rows = (
                await session.execute(
                    select(self._turn_model)
                    .where(self._turn_model.opportunity_id == opportunity_id)
                    .order_by(self._turn_model.created_at, self._turn_model.id)
                    .with_for_update()
                )
            ).scalars().all()
            turns = [_turn_from_row(row) for row in turn_rows]
            latest_incoming = next(
                (turn for turn in reversed(turns) if turn.direction == "INCOMING"), None
            )
            draft = next(
                (turn for turn in turns if turn.reply_version == reply_version), None
            )
            if draft is None:
                raise ValueError("exact reply version not found")
            key = f"REPLY_SENT:{opportunity_id}:{reply_version}:{draft.content_sha256}"
            existing_row = (
                await session.execute(
                    select(self._confirmation_model).where(
                        self._confirmation_model.idempotency_key == key
                    )
                )
            ).scalar_one_or_none()
            if existing_row is not None:
                return (
                    _opportunity_from_row(opportunity_row),
                    _confirmation_from_row(existing_row),
                    False,
                )
            try:
                _verify_current_reply(
                    _opportunity_from_row(opportunity_row), draft, latest_incoming, turns
                )
            except StaleReplyError:
                stale_row = next(row for row in turn_rows if row.id == draft.id)
                if stale_row.direction == "OUTGOING_DRAFT":
                    stale_row.direction = "OUTGOING_SUPERSEDED"
                await session.commit()
                raise
            latency = _reply_latency(latest_incoming, confirmed_at)
            confirmation = OwnerActionConfirmation(
                id=uuid4().hex,
                opportunity_id=opportunity_id,
                action="REPLY_SENT",
                idempotency_key=key,
                actor=actor,
                actor_role=actor_role,
                actor_telegram_user_id=actor_telegram_user_id,
                reply_version=reply_version,
                content_sha256=draft.content_sha256,
                response_latency_seconds=latency,
                confirmed_at=confirmed_at,
            )
            session.add(self._confirmation_model(**_model_values(confirmation)))
            draft_row = next(row for row in turn_rows if row.id == draft.id)
            draft_row.direction = "OUTGOING_CONFIRMED"
            draft_row.sent_at = confirmed_at
            draft_row.response_latency_seconds = latency
            if latest_incoming is not None:
                incoming_row = next(
                    row for row in turn_rows if row.id == latest_incoming.id
                )
                incoming_row.acknowledged_at = confirmed_at
                incoming_row.acknowledged_by_role = actor_role
                incoming_row.acknowledged_by_telegram_user_id = actor_telegram_user_id
                incoming_row.alert_state = "RESOLVED"
            _validate_transition(
                opportunity_row.state, OpportunityState.WAITING_CLIENT.value
            )
            previous = opportunity_row.state
            opportunity_row.state = OpportunityState.WAITING_CLIENT.value
            opportunity_row.last_owner_message_at = confirmed_at
            opportunity_row.updated_at = confirmed_at
            session.add(
                self._transition_model(
                    id=uuid4().hex,
                    opportunity_id=opportunity_id,
                    timestamp=confirmed_at,
                    source="telegram:/mark_reply_sent",
                    previous_state=previous,
                    new_state=opportunity_row.state,
                    reason=(
                        f"authorized adult owner confirmed exact current reply {reply_version}"
                    ),
                    actor=actor,
                    actor_role=actor_role,
                    actor_telegram_user_id=actor_telegram_user_id,
                )
            )
            await session.commit()
            return _opportunity_from_row(opportunity_row), confirmation, True

    async def allocate_reply_version(self, opportunity_id: str) -> str:
        from sqlalchemy import update

        async with self._session_factory() as session:
            sequence = (
                await session.execute(
                    update(self._opportunity_model)
                    .where(self._opportunity_model.id == opportunity_id)
                    .values(
                        next_reply_sequence=self._opportunity_model.next_reply_sequence + 1,
                        updated_at=utc_now(),
                    )
                    .returning(self._opportunity_model.next_reply_sequence)
                )
            ).scalar_one_or_none()
            if sequence is None:
                raise KeyError(opportunity_id)
            await session.commit()
            return f"r{int(sequence) - 1}"

    async def resolve_opportunity(
        self,
        *,
        thread_id: str = "",
        project_id: str = "",
        project_url: str = "",
        reply_reference_id: str = "",
        client_name: str = "",
    ) -> OpportunityResolution:
        return _resolve_items(
            await self.list_opportunities(),
            thread_id=thread_id,
            project_id=project_id,
            project_url=project_url,
            reply_reference_id=reply_reference_id,
            client_name=client_name,
        )

    async def add_turn(self, turn: ConversationTurn) -> tuple[ConversationTurn, bool]:
        from sqlalchemy import or_, select
        from sqlalchemy.exc import IntegrityError

        async with self._session_factory() as session:
            predicates = [
                self._turn_model.canonical_turn_identity == turn.canonical_turn_identity
            ]
            if turn.gmail_message_id:
                predicates.append(
                    self._turn_model.gmail_message_id == turn.gmail_message_id
                )
            query = select(self._turn_model).where(or_(*predicates))
            existing = (await session.execute(query)).scalars().first()
            if existing:
                return _turn_from_row(existing), False
            row = self._turn_model(**_model_values(turn))
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                existing = (await session.execute(query)).scalars().first()
                if existing:
                    return _turn_from_row(existing), False
                raise
            return _turn_from_row(row), True

    async def add_reply_draft_if_current(
        self, turn: ConversationTurn
    ) -> tuple[ConversationTurn, bool]:
        from sqlalchemy import select

        if turn.direction != "OUTGOING_DRAFT":
            raise ValueError("reply draft must start as OUTGOING_DRAFT")
        async with self._session_factory() as session:
            opportunity = (
                await session.execute(
                    select(self._opportunity_model)
                    .where(self._opportunity_model.id == turn.opportunity_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if opportunity is None:
                raise KeyError(turn.opportunity_id)
            rows = (
                await session.execute(
                    select(self._turn_model)
                    .where(self._turn_model.opportunity_id == turn.opportunity_id)
                    .order_by(self._turn_model.created_at, self._turn_model.id)
                    .with_for_update()
                )
            ).scalars().all()
            latest_incoming = next(
                (row for row in reversed(rows) if row.direction == "INCOMING"), None
            )
            current = bool(
                latest_incoming
                and turn.source_reference_id == latest_incoming.id
                and turn.incoming_gmail_message_id == (latest_incoming.gmail_message_id or "")
                and turn.incoming_canonical_identity
                == latest_incoming.canonical_turn_identity
            )
            if current:
                for row in rows:
                    if row.direction == "OUTGOING_DRAFT":
                        row.direction = "OUTGOING_SUPERSEDED"
            else:
                turn.direction = "OUTGOING_SUPERSEDED"
            row = self._turn_model(**_model_values(turn))
            session.add(row)
            await session.commit()
            return _turn_from_row(row), True

    async def get_turn(self, turn_id: str) -> ConversationTurn | None:
        async with self._session_factory() as session:
            row = await session.get(self._turn_model, turn_id)
            return _turn_from_row(row) if row else None

    async def update_turn_fields(
        self, turn_id: str, fields: dict[str, Any]
    ) -> ConversationTurn | None:
        from sqlalchemy import update

        allowed = set(ConversationTurn.__dataclass_fields__) - {
            "id", "opportunity_id", "created_at", "canonical_turn_identity"
        }
        async with self._session_factory() as session:
            result = await session.execute(
                update(self._turn_model)
                .where(self._turn_model.id == turn_id)
                .values(**{key: value for key, value in fields.items() if key in allowed})
                .returning(self._turn_model)
            )
            row = result.scalar_one_or_none()
            await session.commit()
            return _turn_from_row(row) if row else None

    async def list_turns(self, opportunity_id: str) -> list[ConversationTurn]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._turn_model)
                    .where(self._turn_model.opportunity_id == opportunity_id)
                    .order_by(self._turn_model.created_at, self._turn_model.id)
                )
            ).scalars().all()
            return [_turn_from_row(row) for row in rows]

    async def list_pending_incoming_turns(self, now: datetime) -> list[ConversationTurn]:
        from sqlalchemy import or_, select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._turn_model)
                    .where(
                        self._turn_model.direction == "INCOMING",
                        self._turn_model.telegram_notified_at.is_(None),
                        or_(
                            self._turn_model.notification_due_at.is_(None),
                            self._turn_model.notification_due_at <= now,
                        ),
                    )
                    .order_by(self._turn_model.created_at)
                )
            ).scalars().all()
            return [_turn_from_row(row) for row in rows]

    async def mark_turn_notified(self, turn_id: str, at: datetime) -> ConversationTurn | None:
        from sqlalchemy import select

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(self._turn_model)
                    .where(self._turn_model.id == turn_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.telegram_notified_at = at
            if row.acknowledged_at is None:
                row.escalation_due_at = _working_window_due(at + timedelta(minutes=5))
                row.alert_state = "ACK_PENDING"
            await session.commit()
            return _turn_from_row(row)

    async def acknowledge_turn(
        self,
        turn_id: str,
        *,
        at: datetime,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> ConversationTurn | None:
        from sqlalchemy import update

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    update(self._turn_model)
                    .where(
                        self._turn_model.id == turn_id,
                        self._turn_model.direction == "INCOMING",
                    )
                    .values(
                        acknowledged_at=at,
                        acknowledged_by_role=actor_role,
                        acknowledged_by_telegram_user_id=actor_telegram_user_id,
                        alert_state="ACKNOWLEDGED",
                    )
                    .returning(self._turn_model)
                )
            ).scalar_one_or_none()
            await session.commit()
            return _turn_from_row(row) if row else None

    async def list_pending_escalations(self, now: datetime) -> list[ConversationTurn]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._turn_model)
                    .where(
                        self._turn_model.direction == "INCOMING",
                        self._turn_model.alert_state == "ACK_PENDING",
                        self._turn_model.acknowledged_at.is_(None),
                        self._turn_model.escalation_count == 0,
                        self._turn_model.escalation_due_at.is_not(None),
                        self._turn_model.escalation_due_at <= now,
                    )
                    .order_by(self._turn_model.escalation_due_at)
                )
            ).scalars().all()
            return [_turn_from_row(row) for row in rows]

    async def mark_turn_escalated(
        self, turn_id: str, at: datetime
    ) -> ConversationTurn | None:
        from sqlalchemy import update

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    update(self._turn_model)
                    .where(
                        self._turn_model.id == turn_id,
                        self._turn_model.acknowledged_at.is_(None),
                        self._turn_model.escalation_count == 0,
                    )
                    .values(escalation_count=1, alert_state="ESCALATED")
                    .returning(self._turn_model)
                )
            ).scalar_one_or_none()
            await session.commit()
            return _turn_from_row(row) if row else None

    async def add_confirmation(
        self, confirmation: OwnerActionConfirmation
    ) -> tuple[OwnerActionConfirmation, bool]:
        from sqlalchemy import select
        from sqlalchemy.dialects.postgresql import insert

        async with self._session_factory() as session:
            statement = (
                insert(self._confirmation_model)
                .values(**_model_values(confirmation))
                .on_conflict_do_nothing(index_elements=["idempotency_key"])
                .returning(self._confirmation_model.id)
            )
            created_id = (await session.execute(statement)).scalar_one_or_none()
            row = (
                await session.execute(
                    select(self._confirmation_model).where(
                        self._confirmation_model.idempotency_key == confirmation.idempotency_key
                    )
                )
            ).scalar_one()
            await session.commit()
            return _confirmation_from_row(row), bool(created_id)

    async def get_confirmation_by_key(
        self, idempotency_key: str
    ) -> OwnerActionConfirmation | None:
        from sqlalchemy import select

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(self._confirmation_model).where(
                        self._confirmation_model.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one_or_none()
            return _confirmation_from_row(row) if row else None

    async def create_human_request(
        self, request: HumanInformationRequest
    ) -> tuple[HumanInformationRequest, bool]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(self._request_model).where(
                        self._request_model.opportunity_id == request.opportunity_id,
                        self._request_model.source_turn_id == request.source_turn_id,
                        self._request_model.fact_key == request.fact_key,
                        self._request_model.status == "OPEN",
                    )
                )
            ).scalar_one_or_none()
            if existing:
                return _request_from_row(existing), False
            row = self._request_model(**_model_values(request))
            session.add(row)
            await session.commit()
            return _request_from_row(row), True

    async def get_human_request(self, request_id: str) -> HumanInformationRequest | None:
        async with self._session_factory() as session:
            row = await session.get(self._request_model, request_id)
            return _request_from_row(row) if row else None

    async def update_human_request(
        self, request_id: str, fields: dict[str, Any]
    ) -> HumanInformationRequest | None:
        from sqlalchemy import update

        allowed = set(HumanInformationRequest.__dataclass_fields__) - {"id", "opportunity_id", "asked_at"}
        async with self._session_factory() as session:
            result = await session.execute(
                update(self._request_model)
                .where(self._request_model.id == request_id)
                .values(**{key: value for key, value in fields.items() if key in allowed})
                .returning(self._request_model)
            )
            row = result.scalar_one_or_none()
            await session.commit()
            return _request_from_row(row) if row else None

    async def list_human_requests(self, opportunity_id: str) -> list[HumanInformationRequest]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._request_model)
                    .where(self._request_model.opportunity_id == opportunity_id)
                    .order_by(self._request_model.asked_at)
                )
            ).scalars().all()
            return [_request_from_row(row) for row in rows]

    async def list_transitions(self, opportunity_id: str) -> list[OpportunityTransition]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._transition_model)
                    .where(self._transition_model.opportunity_id == opportunity_id)
                    .order_by(self._transition_model.timestamp, self._transition_model.id)
                )
            ).scalars().all()
            return [_transition_from_row(row) for row in rows]

    async def list_opportunities(self) -> list[SalesOpportunity]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._opportunity_model).order_by(self._opportunity_model.created_at)
                )
            ).scalars().all()
            return [_opportunity_from_row(row) for row in rows]

    async def pipeline_counts(self) -> dict[str, int]:
        from sqlalchemy import func, select

        counts = {state.value: 0 for state in OpportunityState}
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(self._opportunity_model.state, func.count())
                    .group_by(self._opportunity_model.state)
                )
            ).all()
        for state, count in rows:
            counts[str(state)] = int(count)
        return counts

    async def create_context_sync(
        self, sync: LeadContextSync
    ) -> tuple[LeadContextSync, bool]:
        from sqlalchemy import select

        async with self._session_factory() as session:
            existing = (
                await session.execute(
                    select(self._context_sync_model).where(
                        self._context_sync_model.requested_by_telegram_user_id
                        == sync.requested_by_telegram_user_id,
                        self._context_sync_model.status == "PENDING",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return _context_sync_from_row(existing), False
            row = self._context_sync_model(**_model_values(sync))
            session.add(row)
            await session.commit()
            return _context_sync_from_row(row), True

    async def get_pending_context_sync(
        self, actor_telegram_user_id: int
    ) -> LeadContextSync | None:
        from sqlalchemy import select

        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(self._context_sync_model)
                    .where(
                        self._context_sync_model.requested_by_telegram_user_id
                        == actor_telegram_user_id,
                        self._context_sync_model.status == "PENDING",
                    )
                    .order_by(self._context_sync_model.requested_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            return _context_sync_from_row(row) if row else None

    async def update_context_sync(
        self, sync_id: str, fields: dict[str, Any]
    ) -> LeadContextSync | None:
        from sqlalchemy import update

        allowed = set(LeadContextSync.__dataclass_fields__) - {
            "id", "opportunity_id", "requested_at", "requested_by_role",
            "requested_by_telegram_user_id",
        }
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    update(self._context_sync_model)
                    .where(self._context_sync_model.id == sync_id)
                    .values(**{key: value for key, value in fields.items() if key in allowed})
                    .returning(self._context_sync_model)
                )
            ).scalar_one_or_none()
            await session.commit()
            return _context_sync_from_row(row) if row else None


def _validate_actor(actor: str) -> None:
    if actor not in VALID_ACTORS:
        raise ValueError(f"invalid sales actor: {actor}")


def _validate_state(state: str) -> None:
    if state not in {value.value for value in OpportunityState}:
        raise ValueError(f"invalid opportunity state: {state}")


def _validate_transition(previous_state: str, new_state: str) -> None:
    _validate_state(previous_state)
    _validate_state(new_state)
    if previous_state == new_state:
        return
    if new_state not in ALLOWED_TRANSITIONS.get(previous_state, frozenset()):
        raise IllegalTransitionError(
            f"illegal opportunity transition: {previous_state} -> {new_state}"
        )


def _actor_role(actor: str) -> str:
    return {
        "system": "SYSTEM",
        "adult_owner": "ADULT_OWNER",
        "Artem": "ARTEM",
        "Vadim": "VADIM",
    }.get(actor, "SYSTEM")


def _verify_bid_confirmation(
    opportunity: SalesOpportunity, confirmation: OwnerActionConfirmation
) -> None:
    if opportunity.state != OpportunityState.PROPOSAL_READY.value:
        raise ValueError(f"bid cannot be confirmed from state {opportunity.state}")
    if confirmation.actor_role != "ADULT_OWNER":
        raise ValueError("only ADULT_OWNER may confirm a bid")
    if not confirmation.actor_telegram_user_id:
        raise ValueError("actual Telegram actor ID is required")
    if confirmation.proposal_version != opportunity.proposal_version:
        raise ValueError(
            "proposal version is stale; current command: "
            f"/mark_bid_sent {opportunity.id} {opportunity.proposal_version} | "
            "<actual price> | <actual timeline>"
        )
    actual_hash = hashlib.sha256(opportunity.initial_proposal.encode("utf-8")).hexdigest()
    if (
        not opportunity.proposal_content_sha256
        or confirmation.content_sha256 != opportunity.proposal_content_sha256
        or actual_hash != opportunity.proposal_content_sha256
    ):
        raise ValueError("current proposal SHA-256 does not match the stored package")
    if not confirmation.money_terms_json or not confirmation.timeline_terms_json:
        raise ValueError("canonical submitted terms are required")


def _verify_current_reply(
    opportunity: SalesOpportunity,
    draft: ConversationTurn,
    latest_incoming: ConversationTurn | None,
    turns: list[ConversationTurn],
) -> None:
    allowed_states = {
        OpportunityState.NEGOTIATING.value,
        OpportunityState.SELECTION_REVIEW.value,
        OpportunityState.CONTRACT_REVIEW.value,
    }
    if opportunity.state not in allowed_states:
        raise ValueError(f"reply cannot be confirmed from state {opportunity.state}")
    current_drafts = [turn for turn in turns if turn.direction == "OUTGOING_DRAFT"]
    latest_draft = max(
        current_drafts,
        key=lambda turn: int((turn.reply_version or "r0").removeprefix("r") or 0),
        default=None,
    )
    is_stale = (
        latest_incoming is None
        or draft.direction != "OUTGOING_DRAFT"
        or draft.source_reference_id != latest_incoming.id
        or draft.incoming_gmail_message_id != latest_incoming.gmail_message_id
        or draft.incoming_canonical_identity
        != latest_incoming.canonical_turn_identity
        or latest_draft is None
        or latest_draft.id != draft.id
    )
    if is_stale:
        draft.direction = "OUTGOING_SUPERSEDED"
        raise StaleReplyError(
            latest_incoming.id if latest_incoming else "unavailable", opportunity.id
        )
    actual_hash = hashlib.sha256(draft.content.encode("utf-8")).hexdigest()
    if actual_hash != draft.content_sha256:
        raise ValueError("reply content hash changed after validation")


def _reply_latency(
    latest_incoming: ConversationTurn | None, confirmed_at: datetime
) -> float | None:
    if latest_incoming is None or latest_incoming.source_received_at is None:
        return None
    received = latest_incoming.source_received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return max(0.0, (confirmed_at - received).total_seconds())


def _working_window_due(value: datetime) -> datetime:
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    local = aware.astimezone(ZoneInfo("Europe/Kyiv"))
    if time(8, 0) <= local.time() < time(21, 0):
        return aware.astimezone(timezone.utc)
    target_date = local.date() if local.time() < time(8, 0) else local.date() + timedelta(days=1)
    return datetime.combine(
        target_date, time(8, 0), tzinfo=ZoneInfo("Europe/Kyiv")
    ).astimezone(timezone.utc)


def _resolve_items(
    items: list[SalesOpportunity],
    *,
    thread_id: str,
    project_id: str,
    project_url: str,
    reply_reference_id: str,
    client_name: str,
) -> OpportunityResolution:
    authoritative: list[tuple[str, set[str]]] = []
    for basis, value, attribute in (
        ("thread_id", thread_id, "thread_id"),
        ("project_id", project_id, "project_id"),
        ("project_url", project_url, "project_url"),
        ("reply_reference_id", reply_reference_id, "reply_reference_id"),
    ):
        if value:
            matches = {item.id for item in items if getattr(item, attribute) == value}
            if matches:
                authoritative.append((basis, matches))
    if authoritative:
        combined = set().union(*(matches for _basis, matches in authoritative))
        common = set.intersection(*(matches for _basis, matches in authoritative))
        if len(combined) > 1 or len(common) != 1:
            return OpportunityResolution(None, "conflicting_authoritative_identifiers", True)
        selected_id = next(iter(common))
        selected = next(item for item in items if item.id == selected_id)
        basis = "+".join(basis for basis, matches in authoritative if selected_id in matches)
        return OpportunityResolution(replace(selected), basis)
    if client_name:
        matches = [
            item
            for item in items
            if item.client_name.casefold() == client_name.casefold()
            and item.state not in {OpportunityState.LOST.value, OpportunityState.CLOSED.value}
        ]
        if len(matches) == 1:
            return OpportunityResolution(replace(matches[0]), "client_name_hint")
        if len(matches) > 1:
            return OpportunityResolution(None, "ambiguous_client_name_hint", True)
    return OpportunityResolution(None, "unresolved")


def _model_values(value: Any) -> dict[str, Any]:
    values = asdict(value)
    nullable_strings: dict[type[Any], set[str]] = {
        SalesOpportunity: {
            "gmail_job_key",
            "project_id",
            "thread_id",
            "project_url",
            "thread_url",
            "reply_reference_id",
            "client_name",
            "source_description",
            "live_status",
            "competition_signal",
            "recommended_price",
            "recommended_timeline",
            "risks",
            "approved_evidence",
            "evidence_case_id",
            "initial_proposal",
            "proposal_version",
            "proposal_content_sha256",
            "actual_submitted_price",
            "actual_submitted_timeline",
            "actual_submitted_price_raw",
            "actual_submitted_timeline_raw",
            "actual_submitted_money_json",
            "actual_submitted_timeline_json",
        },
        ConversationTurn: {
            "gmail_message_id",
            "source_reference_id",
            "reply_version",
            "incoming_gmail_message_id",
            "incoming_canonical_identity",
            "language",
            "russian_summary",
            "actual_ask",
            "negotiation_strategy",
            "risks",
            "missing_facts",
            "imported_by_role",
            "acknowledged_by_role",
        },
        OwnerActionConfirmation: {
            "proposal_version",
            "reply_version",
            "content_sha256",
            "actual_price",
            "actual_timeline",
            "actual_price_raw",
            "actual_timeline_raw",
            "money_terms_json",
            "timeline_terms_json",
        },
        HumanInformationRequest: {
            "answer",
            "answer_code",
            "answer_text",
            "canonical_money_json",
            "canonical_timeline_json",
            "approved_availability_json",
            "approved_evidence_case_id",
            "resulting_reply_version",
            "answered_by",
            "answered_by_role",
        },
        LeadContextSync: {"content_sha256"},
    }
    for field_name in nullable_strings.get(type(value), set()):
        if values.get(field_name) == "":
            values[field_name] = None
    return values


def _from_row(kind: type[Any], row: Any) -> Any:
    return kind(
        **{
            name: (getattr(row, name) if getattr(row, name) is not None else "")
            for name, field_info in kind.__dataclass_fields__.items()
            if name not in {
                "score",
                "fit_score",
                "bid_submitted_at",
                "last_owner_message_at",
                "last_client_message_at",
                "next_follow_up_at",
                "response_latency_seconds",
                "source_received_at",
                "detected_at",
                "telegram_notified_at",
                "notification_due_at",
                "sent_at",
                "generated_at",
                "imported_at",
                "imported_by_telegram_user_id",
                "acknowledged_at",
                "acknowledged_by_telegram_user_id",
                "escalation_due_at",
                "answered_at",
                "answered_by_telegram_user_id",
                "actor_telegram_user_id",
            }
        }
        | {
            name: getattr(row, name)
            for name in kind.__dataclass_fields__
            if name in {
                "score",
                "fit_score",
                "bid_submitted_at",
                "last_owner_message_at",
                "last_client_message_at",
                "next_follow_up_at",
                "response_latency_seconds",
                "source_received_at",
                "detected_at",
                "telegram_notified_at",
                "notification_due_at",
                "sent_at",
                "generated_at",
                "imported_at",
                "imported_by_telegram_user_id",
                "acknowledged_at",
                "acknowledged_by_telegram_user_id",
                "escalation_due_at",
                "answered_at",
                "answered_by_telegram_user_id",
                "actor_telegram_user_id",
            }
        }
    )


def _opportunity_from_row(row: Any) -> SalesOpportunity:
    return _from_row(SalesOpportunity, row)


def _transition_from_row(row: Any) -> OpportunityTransition:
    return OpportunityTransition(
        **{name: getattr(row, name) for name in OpportunityTransition.__dataclass_fields__}
    )


def _turn_from_row(row: Any) -> ConversationTurn:
    return _from_row(ConversationTurn, row)


def _confirmation_from_row(row: Any) -> OwnerActionConfirmation:
    return _from_row(OwnerActionConfirmation, row)


def _request_from_row(row: Any) -> HumanInformationRequest:
    return _from_row(HumanInformationRequest, row)


def _context_sync_from_row(row: Any) -> LeadContextSync:
    return _from_row(LeadContextSync, row)
