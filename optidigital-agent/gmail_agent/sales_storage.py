"""Restart-safe persistence contracts for the Stage 5A sales closer.

The module deliberately contains no platform-send capability.  It stores the
commercial context, dialogue history, owner confirmations and human facts
needed to prepare copy-ready text for an adult account owner.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4


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
    SELECTED = "SELECTED"
    HANDOFF_READY = "HANDOFF_READY"
    LOST = "LOST"
    CLOSED = "CLOSED"


VALID_ACTORS = {"system", "adult_owner", "Artem"}


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
    bid_submitted_at: datetime | None = None
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
    sent_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class OwnerActionConfirmation:
    id: str
    opportunity_id: str
    action: str
    idempotency_key: str
    actor: str
    proposal_version: str = ""
    reply_version: str = ""
    content_sha256: str = ""
    actual_price: str = ""
    actual_timeline: str = ""
    response_latency_seconds: float | None = None
    confirmed_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class HumanInformationRequest:
    id: str
    opportunity_id: str
    source_turn_id: str
    fact_key: str
    question: str
    status: str = "OPEN"
    answer: str = ""
    resulting_reply_version: str = ""
    asked_at: datetime = field(default_factory=utc_now)
    answered_at: datetime | None = None
    answered_by: str = ""


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
    ) -> SalesOpportunity: ...

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

    async def get_turn(self, turn_id: str) -> ConversationTurn | None: ...

    async def update_turn_fields(
        self, turn_id: str, fields: dict[str, Any]
    ) -> ConversationTurn | None: ...

    async def list_turns(self, opportunity_id: str) -> list[ConversationTurn]: ...

    async def list_pending_incoming_turns(self, now: datetime) -> list[ConversationTurn]: ...

    async def mark_turn_notified(self, turn_id: str, at: datetime) -> ConversationTurn | None: ...

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


class InMemorySalesRepository:
    """Deterministic repository whose shared state simulates a restart."""

    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.state = state if state is not None else {}
        self.state.setdefault("opportunities", {})
        self.state.setdefault("transitions", {})
        self.state.setdefault("turns", {})
        self.state.setdefault("confirmations", {})
        self.state.setdefault("requests", {})

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
    ) -> SalesOpportunity:
        _validate_actor(actor)
        _validate_state(new_state)
        item = self.state["opportunities"].get(opportunity_id)
        if item is None:
            raise KeyError(opportunity_id)
        if item.state == new_state:
            return replace(item)
        transition = OpportunityTransition(
            id=uuid4().hex,
            opportunity_id=opportunity_id,
            timestamp=utc_now(),
            source=source,
            previous_state=item.state,
            new_state=new_state,
            reason=reason,
            actor=actor,
        )
        item.state = new_state
        item.updated_at = transition.timestamp
        self.state["transitions"][transition.id] = transition
        return replace(item)

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


class PostgresSalesRepository:
    """Additive PostgreSQL implementation used by production entry points."""

    def __init__(self, session_factory: Any) -> None:
        from db.models import (
            ConversationTurn as ConversationTurnModel,
        )
        from db.models import (
            HumanInformationRequest as HumanInformationRequestModel,
        )
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
                    )
                )
                row.state = new_state
                row.updated_at = at
            await session.commit()
            return _opportunity_from_row(row)

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
        from sqlalchemy import update

        async with self._session_factory() as session:
            result = await session.execute(
                update(self._turn_model)
                .where(self._turn_model.id == turn_id)
                .values(telegram_notified_at=at)
                .returning(self._turn_model)
            )
            row = result.scalar_one_or_none()
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


def _validate_actor(actor: str) -> None:
    if actor not in VALID_ACTORS:
        raise ValueError(f"invalid sales actor: {actor}")


def _validate_state(state: str) -> None:
    if state not in {value.value for value in OpportunityState}:
        raise ValueError(f"invalid opportunity state: {state}")


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
        },
        ConversationTurn: {
            "gmail_message_id",
            "source_reference_id",
            "reply_version",
            "language",
            "russian_summary",
            "actual_ask",
            "negotiation_strategy",
            "risks",
            "missing_facts",
        },
        OwnerActionConfirmation: {
            "proposal_version",
            "reply_version",
            "content_sha256",
            "actual_price",
            "actual_timeline",
        },
        HumanInformationRequest: {
            "answer",
            "resulting_reply_version",
            "answered_by",
        },
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
                "answered_at",
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
                "answered_at",
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
