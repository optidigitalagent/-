"""Production-like Stage 5A loop against an isolated real PostgreSQL schema.

Set SALES_CLOSER_TEST_DATABASE_URL to a disposable PostgreSQL database.  The
test creates and drops one random schema.  Telegram and AI are mocked; Gmail
and Freelancehunt are never mutated.
"""

from __future__ import annotations

import hashlib
import asyncio
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
    IllegalTransitionError,
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
    assert context["confirmed_conversation"][-1]["direction"] == "INCOMING"
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
        opportunity, sent_confirmation, sent_created = await service.mark_reply_sent(
            opportunity.id,
            "r2",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
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
