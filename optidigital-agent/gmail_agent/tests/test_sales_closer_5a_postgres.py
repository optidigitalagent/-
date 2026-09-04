"""Production-like Stage 5A loop against an isolated real PostgreSQL schema.

Set SALES_CLOSER_TEST_DATABASE_URL to a disposable PostgreSQL database.  The
test creates and drops one random schema.  Telegram and AI are mocked; Gmail
and Freelancehunt are never mutated.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gmail_agent.gmail_provider import EmailMessage
from gmail_agent.sales_closer import (
    SalesCloserError,
    SalesCloserService,
    SalesReplyCandidate,
)
from gmail_agent.sales_storage import (
    HumanInformationRequest,
    IllegalTransitionError,
    OpportunityMergeEvidence,
    OpportunityState,
    PostgresSalesRepository,
)
from gmail_agent.telegram_notifier import send_sales_response_card

TEST_DATABASE_URL = os.environ.get("SALES_CLOSER_TEST_DATABASE_URL", "").strip()
NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


async def _generator(context, _client, _errors):
    assert context["source_project_description"]
    assert context["initial_submitted_proposal"]
    assert context["actual_submitted_price"] == "1200 USD"
    assert context["actual_submitted_timeline"] == "5 days"
    assert any(
        item["direction"] == "INCOMING"
        for item in context["confirmed_conversation"]
    )
    return SalesReplyCandidate(
        reply="Regarding authentication, we will keep the confirmed scope. Please confirm the endpoint list.",
        russian_summary="Клиент просит уточнить авторизацию.",
        actual_ask="authentication details",
        strategy="Ответить по согласованному объёму.",
        risks="Не расширять объём.",
    )


@unittest.skipUnless(TEST_DATABASE_URL, "SALES_CLOSER_TEST_DATABASE_URL is not configured")
class TestSalesCloserPostgresE2E(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.environ.setdefault("TELEGRAM_TOKEN", "synthetic-test-token")
        os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
        os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
        from db.models import _MIGRATIONS, Base

        self.schema = f"sales_5a_{uuid4().hex}"
        bootstrap = create_async_engine(TEST_DATABASE_URL)
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        await bootstrap.dispose()
        self.engine = create_async_engine(
            TEST_DATABASE_URL,
            connect_args={"server_settings": {"search_path": self.schema}},
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            for statement in _MIGRATIONS:
                await connection.execute(text(statement))
            # Every migration statement must be restart-safe.
            for statement in _MIGRATIONS:
                await connection.execute(text(statement))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()
        cleanup = create_async_engine(TEST_DATABASE_URL)
        async with cleanup.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await cleanup.dispose()

    @staticmethod
    def _job(project_id: str) -> SimpleNamespace:
        proposal = "We can deliver the confirmed API integration scope."
        return SimpleNamespace(
            stable_key=f"freelancehunt:project:{project_id}",
            analysis_quality_status="QUALITY_VALID",
            title=f"Synthetic PostgreSQL Stage 5A project {project_id}",
            project_id=project_id,
            thread_id="",
            url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
            discovery_source="synthetic_test",
            client_name="Synthetic Client",
            full_description="Build a synthetic API integration with authentication and tests.",
            description_completeness="FULL",
            score=8.0,
            fit_score=9.0,
            bid_count=2,
            win_probability_signal="medium",
            recommended_price="1200 USD",
            realistic_timeline="5 days",
            delivery_risk="controlled",
            client_payment_risk="unknown",
            selected_evidence="Approved evidence: Gmail Job Agent used API integration and PostgreSQL.",
            evidence_case_id="GMAIL_JOB_AGENT",
            proposal_draft=proposal,
            proposal_version=f"pqg-v3-{project_id}",
            proposal_content_sha256=hashlib.sha256(proposal.encode()).hexdigest(),
            live_status="ACTIVE_BIDDABLE",
        )

    @staticmethod
    def _email(project_id: str, body: str, email_id: str) -> EmailMessage:
        url = f"https://freelancehunt.com/project/synthetic/{project_id}.html"
        return EmailMessage(
            id=email_id,
            subject="New private message from Synthetic Client",
            sender="Freelancehunt <notify@freelancehunt.com>",
            body=f"{body}\n{url}",
            text_body=f"{body}\n{url}",
            links=[url],
            received_at=NOW - timedelta(seconds=60),
            raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
        )

    @staticmethod
    def _title_email(title: str, thread_id: str, email_id: str) -> EmailMessage:
        thread_url = (
            f"https://freelancehunt.com/en/mailbox/read/thread/{thread_id}"
            "?tracking=removed#last-message"
        )
        html_body = (
            "<html><body><p>You received a new private message</p>"
            '<a href="https://freelancehunt.com/freelancer/synthetic_client.html">'
            "Synthetic Client</a>"
            '<div class="message-text">Please clarify the authentication endpoint list.</div>'
            f'<a href="{thread_url}">Reply</a>'
            '<a href="https://freelancehunt.com/unsubscribe?token=removed">Unsubscribe</a>'
            "</body></html>"
        )
        return EmailMessage(
            id=email_id,
            subject=f"New private message from Synthetic Client : {title}",
            sender="Freelancehunt <notify@freelancehunt.com>",
            body="",
            text_body="",
            html_body=html_body,
            links=[],
            received_at=NOW - timedelta(seconds=30),
            raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
        )

    async def test_validated_bid_dialogue_confirmation_restart(self):
        repository = PostgresSalesRepository(self.sessions)
        service = SalesCloserService(repository, reply_generator=_generator, now=lambda: NOW)
        job = self._job("990005001")
        opportunity = await service.ensure_from_validated_job(job)
        opportunity, bid_confirmation, created = await service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW - timedelta(minutes=3),
        )
        self.assertTrue(created)
        self.assertEqual(bid_confirmation.proposal_version, job.proposal_version)

        email = self._email(
            "990005001",
            "Can you support the HubSpot API integration?",
            "synthetic-gmail-private-1",
        )
        waiting = await service.process_client_message(email)
        self.assertIsNotNone(waiting.human_request)
        result = await service.answer_human_request(
            waiting.human_request.id,
            "YES",
            actor_role="VADIM",
            actor_telegram_user_id=303,
        )
        self.assertEqual(result.reply_turn.reply_version, "r1")
        telegram = SimpleNamespace(send_message=AsyncMock())
        self.assertTrue(await send_sales_response_card(telegram, 1, result))
        telegram.send_message.assert_awaited()
        await service.mark_notified(result.incoming_turn.id)

        newer = await service.process_client_message(
            self._email(
                "990005001",
                "Please clarify the authentication endpoint list.",
                "synthetic-gmail-private-newer",
            )
        )
        self.assertEqual(newer.reply_turn.reply_version, "r2")
        await repository.update_opportunity_fields(
            opportunity.id,
            {"state": OpportunityState.CLIENT_REPLIED.value},
        )
        with self.assertRaisesRegex(
            SalesCloserError, rf"{newer.incoming_turn.id}.*?/regenerate_lead"
        ):
            await service.mark_reply_sent(
                opportunity.id,
                "r1",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=101,
                confirmed_at=NOW,
            )
        restarted_after_stale = SalesCloserService(
            PostgresSalesRepository(self.sessions),
            reply_generator=_generator,
            now=lambda: NOW,
        )
        stale_opportunity, _transitions, stale_turns, _requests = (
            await restarted_after_stale.lead_timeline(opportunity.id)
        )
        stale_r1 = next(turn for turn in stale_turns if turn.reply_version == "r1")
        latest_incoming = next(
            turn for turn in reversed(stale_turns) if turn.direction == "INCOMING"
        )
        self.assertEqual(stale_r1.direction, "OUTGOING_SUPERSEDED")
        self.assertEqual(stale_opportunity.state, OpportunityState.CLIENT_REPLIED.value)
        self.assertIsNone(latest_incoming.acknowledged_at)
        async with self.engine.connect() as connection:
            reply_confirmation_count = (
                await connection.execute(
                    text(
                        "SELECT count(*) FROM owner_action_confirmations "
                        "WHERE action = 'REPLY_SENT'"
                    )
                )
            ).scalar_one()
        self.assertEqual(reply_confirmation_count, 0)

        await PostgresSalesRepository(self.sessions).update_opportunity_fields(
            opportunity.id,
            {"state": OpportunityState.NEGOTIATING.value},
        )
        opportunity, sent_confirmation, sent_created = (
            await restarted_after_stale.mark_reply_sent(
            opportunity.id,
            "r2",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
            )
        )
        self.assertTrue(sent_created)
        self.assertEqual(sent_confirmation.content_sha256, newer.reply_turn.content_sha256)
        self.assertEqual(opportunity.state, OpportunityState.WAITING_CLIENT.value)

        restarted = SalesCloserService(
            PostgresSalesRepository(self.sessions), reply_generator=_generator, now=lambda: NOW
        )
        persisted, transitions, turns, requests = await restarted.lead_timeline(opportunity.id)
        self.assertEqual(persisted.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual(
            [turn.direction for turn in turns],
            ["INCOMING", "OUTGOING_SUPERSEDED", "INCOMING", "OUTGOING_CONFIRMED"],
        )
        self.assertEqual(len(requests), 1)
        self.assertTrue(
            any(
                transition.new_state == OpportunityState.WAITING_CLIENT.value
                and transition.actor_role == "ADULT_OWNER"
                for transition in transitions
            )
        )

        # Nullable unique identifiers must not collide across opportunities.
        second = await restarted.ensure_from_validated_job(self._job("990005002"))
        second, _confirmation, _created = await restarted.mark_bid_sent(
            second.id,
            second.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        second_email = self._email(
            "990005002",
            "Please clarify the authentication details.",
            "synthetic-gmail-private-2",
        )
        second_result = await restarted.process_client_message(second_email)
        self.assertEqual(second_result.opportunity.id, second.id)
        self.assertEqual(second_result.reply_turn.reply_version, "r1")

    async def test_concurrent_turns_allocate_unique_versions(self):
        repository = PostgresSalesRepository(self.sessions)

        async def yielding_generator(context, client, errors):
            await asyncio.sleep(0)
            return await _generator(context, client, errors)

        service = SalesCloserService(
            repository, reply_generator=yielding_generator, now=lambda: NOW
        )
        opportunity = await service.ensure_from_validated_job(self._job("990005010"))
        opportunity, _confirmation, _created = await service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        results = await asyncio.gather(
            service.process_client_message(
                self._email(
                    "990005010", "Please clarify authentication A.", "pg-race-a"
                )
            ),
            service.process_client_message(
                self._email(
                    "990005010", "Please clarify authentication B.", "pg-race-b"
                )
            ),
        )
        turns = await repository.list_turns(opportunity.id)
        self.assertEqual(
            {turn.reply_version for turn in turns if turn.reply_version}, {"r1", "r2"}
        )
        self.assertEqual(sum(turn.direction == "OUTGOING_DRAFT" for turn in turns), 1)
        self.assertEqual(
            sum(turn.direction == "OUTGOING_SUPERSEDED" for turn in turns), 1
        )
        self.assertEqual({result.opportunity.id for result in results}, {opportunity.id})

    async def test_concurrent_terminal_transitions_fail_closed(self):
        repository = PostgresSalesRepository(self.sessions)
        service = SalesCloserService(repository, now=lambda: NOW)
        opportunity = await service.ensure_from_validated_job(self._job("990005020"))
        await repository.transition(
            opportunity.id,
            OpportunityState.CLOSED.value,
            source="synthetic",
            reason="terminal",
            actor="system",
        )
        outcomes = await asyncio.gather(
            repository.transition(
                opportunity.id,
                OpportunityState.NEGOTIATING.value,
                source="synthetic",
                reason="illegal concurrent reopen A",
                actor="system",
            ),
            repository.transition(
                opportunity.id,
                OpportunityState.WAITING_CLIENT.value,
                source="synthetic",
                reason="illegal concurrent reopen B",
                actor="system",
            ),
            return_exceptions=True,
        )
        self.assertTrue(all(isinstance(item, IllegalTransitionError) for item in outcomes))
        persisted = await repository.get_opportunity(opportunity.id)
        self.assertEqual(persisted.state, OpportunityState.CLOSED.value)

    async def test_real_shape_title_binding_is_atomic_restart_safe_and_deduplicated(self):
        repository = PostgresSalesRepository(self.sessions)
        service = SalesCloserService(
            repository, reply_generator=_generator, now=lambda: NOW
        )
        project_id = "990005030"
        job = self._job(project_id)
        job.title = 'PostgreSQL — Exact “Title”'
        opportunity = await service.ensure_from_validated_job(job)
        opportunity, _confirmation, _created = await service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        first_email = self._title_email(
            'PostgreSQL - Exact "Title"', "88005030", "pg-title-a"
        )
        second_email = self._title_email(
            'PostgreSQL - Exact "Title"', "88005030", "pg-title-b"
        )
        first, second = await asyncio.gather(
            service.process_client_message(first_email),
            service.process_client_message(second_email),
        )
        self.assertEqual({first.opportunity.id, second.opportunity.id}, {opportunity.id})
        persisted = await repository.get_opportunity(opportunity.id)
        self.assertEqual(persisted.thread_id, "88005030")
        self.assertTrue(persisted.normalized_title)

        turns_before_confirmation = await repository.list_turns(opportunity.id)
        current_draft = next(
            turn
            for turn in turns_before_confirmation
            if turn.direction == "OUTGOING_DRAFT"
        )
        persisted, _sent_confirmation, sent_created = await service.mark_reply_sent(
            opportunity.id,
            current_draft.reply_version,
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
        )
        self.assertTrue(sent_created)
        self.assertEqual(persisted.state, OpportunityState.WAITING_CLIENT.value)

        restarted_repository = PostgresSalesRepository(self.sessions)
        restarted = SalesCloserService(
            restarted_repository, reply_generator=_generator, now=lambda: NOW
        )
        duplicate = await restarted.process_client_message(first_email)
        self.assertTrue(duplicate.duplicate)
        restarted_opportunity = await restarted_repository.get_opportunity(opportunity.id)
        self.assertEqual(restarted_opportunity.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual(restarted_opportunity.thread_id, "88005030")
        turns = await restarted_repository.list_turns(opportunity.id)
        incoming = [turn for turn in turns if turn.direction == "INCOMING"]
        self.assertEqual(len(incoming), 2)
        self.assertTrue(all(turn.wrapper_language == "en" for turn in incoming))
        self.assertTrue(all(turn.resolution_basis for turn in incoming))

    async def test_orphan_merge_is_atomic_concurrent_restart_safe_and_audited(self):
        repository = PostgresSalesRepository(self.sessions)
        generator = AsyncMock(side_effect=_generator)
        service = SalesCloserService(
            repository, reply_generator=generator, now=lambda: NOW
        )
        project_id = "990005040"
        job = self._job(project_id)
        job.title = "Canonical PostgreSQL merge target"
        canonical = await service.ensure_from_validated_job(job)
        canonical, _confirmation, _created = await service.mark_bid_sent(
            canonical.id,
            canonical.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        orphan_result = await service.process_client_message(
            self._title_email(
                "Unknown PostgreSQL orphan title", "88005040", "pg-orphan-v4"
            )
        )
        orphan = orphan_result.opportunity
        self.assertTrue(orphan.is_orphan)
        self.assertEqual(orphan.state, OpportunityState.NEEDS_CONTEXT.value)
        await repository.update_turn_fields(
            orphan_result.incoming_turn.id,
            {
                "acknowledged_at": NOW,
                "acknowledged_by_role": "ARTEM",
                "acknowledged_by_telegram_user_id": 202,
                "escalation_count": 1,
                "alert_state": "ESCALATED",
            },
        )
        request, _created = await repository.create_human_request(
            HumanInformationRequest(
                id="hir_pg_v4_rehome",
                opportunity_id=orphan.id,
                source_turn_id=orphan_result.incoming_turn.id,
                fact_key="synthetic_audit_fact",
                intent="CLARIFICATION",
                subject_fingerprint="pg-v4",
                question="Synthetic audit-only question",
                asked_at=NOW,
            )
        )
        sync, _ = await service.begin_context_sync(
            orphan.id, actor_role="ARTEM", actor_telegram_user_id=202
        )
        copied = (
            f"Project ID: {project_id}\n"
            "Thread ID: 88005040\n"
            f"{canonical.project_url}\n"
            "https://freelancehunt.com/en/mailbox/read/thread/88005040#last-message\n"
            "Confirmed conversation history only."
        )
        evidence = OpportunityMergeEvidence(
            project_id=project_id,
            project_url=canonical.project_url,
            thread_id="88005040",
            thread_url="https://freelancehunt.com/en/mailbox/read/thread/88005040",
            content_sha256=hashlib.sha256(copied.encode()).hexdigest(),
        )
        first, second = await asyncio.gather(
            repository.merge_orphan_into_canonical(
                orphan.id,
                canonical.id,
                evidence=evidence,
                actor_role="ARTEM",
                actor_telegram_user_id=202,
                merged_at=NOW,
            ),
            PostgresSalesRepository(self.sessions).merge_orphan_into_canonical(
                orphan.id,
                canonical.id,
                evidence=evidence,
                actor_role="ARTEM",
                actor_telegram_user_id=202,
                merged_at=NOW,
            ),
        )
        self.assertEqual(sum(result.created for result in (first, second)), 1)

        result = await service.import_context(
            copied, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertEqual(result.opportunity.id, canonical.id)
        self.assertIsNotNone(result.reply_turn)
        generator.assert_awaited_once()
        telegram = SimpleNamespace(send_message=AsyncMock(return_value=True))
        self.assertTrue(await send_sales_response_card(telegram, 1, result))
        telegram.send_message.assert_awaited_once()

        saved_orphan = await repository.get_opportunity(orphan.id)
        saved_canonical = await repository.get_opportunity(canonical.id)
        self.assertEqual(saved_orphan.state, OpportunityState.MERGED.value)
        self.assertEqual(saved_orphan.merged_into_opportunity_id, canonical.id)
        self.assertTrue(saved_orphan.merge_evidence_json)
        self.assertEqual(saved_canonical.thread_id, "88005040")
        self.assertEqual(saved_canonical.initial_proposal, canonical.initial_proposal)
        self.assertEqual(saved_canonical.actual_submitted_price, "1200 USD")
        self.assertEqual(saved_canonical.actual_submitted_timeline, "5 days")
        turns = await repository.list_turns(canonical.id)
        moved = next(turn for turn in turns if turn.id == orphan_result.incoming_turn.id)
        self.assertEqual(moved.gmail_message_id, "pg-orphan-v4")
        self.assertEqual(moved.acknowledged_by_role, "ARTEM")
        self.assertEqual(moved.escalation_count, 1)
        self.assertEqual(
            (await repository.get_human_request(request.id)).opportunity_id,
            canonical.id,
        )
        counts = await repository.pipeline_counts()
        self.assertEqual(counts[OpportunityState.MERGED.value], 0)
        self.assertEqual(sum(counts.values()), 1)
        orphan_audit = await repository.list_transitions(orphan.id)
        canonical_audit = await repository.list_transitions(canonical.id)
        self.assertTrue(any(item.new_state == "MERGED" for item in orphan_audit))
        self.assertTrue(any("accepted audited orphan history" in item.reason for item in canonical_audit))

        restarted_repository = PostgresSalesRepository(self.sessions)
        restarted = SalesCloserService(
            restarted_repository, reply_generator=generator, now=lambda: NOW
        )
        repeated_sync, redirected = await restarted.begin_context_sync(
            orphan.id, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertEqual(redirected.id, canonical.id)
        repeated = await restarted.import_context(
            copied, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertTrue(repeated.duplicate)
        generator.assert_awaited_once()
        async with self.sessions() as session:
            from db.models import LeadContextSync

            sync_row = await session.get(LeadContextSync, sync.id)
            repeated_sync_row = await session.get(LeadContextSync, repeated_sync.id)
            self.assertEqual(sync_row.opportunity_id, canonical.id)
            self.assertEqual(repeated_sync_row.opportunity_id, canonical.id)

        future = await restarted.process_client_message(
            self._title_email(
                "A different future title", "88005040", "pg-future-thread-v4"
            )
        )
        self.assertEqual(future.opportunity.id, canonical.id)
        self.assertEqual(len(await restarted_repository.list_opportunities()), 2)

    async def test_shared_operator_audit_survives_postgres_restart(self):
        repository = PostgresSalesRepository(self.sessions)
        service = SalesCloserService(
            repository, reply_generator=_generator, now=lambda: NOW
        )
        opportunity = await service.ensure_from_validated_job(self._job("880060"))
        opportunity, confirmation, created = await service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=909090,
            confirmed_at=NOW,
            operator_mode="SINGLE_SHARED_OPERATOR",
            identity_assurance="SHARED_ACCOUNT_SELF_ATTESTED",
            claimed_actor_role="ADULT_OWNER",
            attestation_version="OWNER_CONFIRMS_V1",
            claimed_at=NOW,
        )
        self.assertTrue(created)
        incoming = await service.process_client_message(
            self._email(
                "880060", "Can you support the HubSpot API?", "pg-shared-human"
            )
        )
        self.assertIsNotNone(incoming.human_request)
        answered = await service.answer_human_request(
            incoming.human_request.id,
            "YES",
            actor_role="ARTEM",
            actor_telegram_user_id=909090,
            operator_mode="SINGLE_SHARED_OPERATOR",
            identity_assurance="SHARED_ACCOUNT_SELF_ATTESTED",
            claimed_actor_role="ARTEM",
            attestation_version="FACT_SOURCE_V1",
            claimed_at=NOW,
        )
        restarted = PostgresSalesRepository(self.sessions)
        stored_confirmation = await restarted.get_confirmation_by_key(
            confirmation.idempotency_key
        )
        stored_request = await restarted.get_human_request(
            answered.human_request.id
        )
        self.assertEqual(stored_confirmation.operator_mode, "SINGLE_SHARED_OPERATOR")
        self.assertEqual(
            stored_confirmation.identity_assurance,
            "SHARED_ACCOUNT_SELF_ATTESTED",
        )
        self.assertEqual(stored_confirmation.actual_telegram_user_id, 909090)
        self.assertEqual(stored_confirmation.action_confirmed_at, NOW)
        self.assertEqual(stored_request.claimed_actor_role, "ARTEM")
        self.assertEqual(stored_request.source_turn_id, incoming.incoming_turn.id)
        self.assertEqual(stored_request.actual_telegram_user_id, 909090)
        self.assertEqual(stored_request.action_confirmed_at, NOW)
