"""Production-like Stage 5A loop against an isolated real PostgreSQL schema.

Set SALES_CLOSER_TEST_DATABASE_URL to a disposable PostgreSQL database.  The
test creates and drops one random schema.  Telegram and AI are mocked; Gmail
and Freelancehunt are never mutated.
"""

from __future__ import annotations

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
from gmail_agent.sales_closer import SalesCloserService, SalesReplyCandidate
from gmail_agent.sales_storage import OpportunityState, PostgresSalesRepository
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

    async def test_validated_bid_dialogue_confirmation_restart(self):
        repository = PostgresSalesRepository(self.sessions)
        service = SalesCloserService(repository, reply_generator=_generator, now=lambda: NOW)
        proposal = "We can deliver the confirmed API integration scope."
        job = SimpleNamespace(
            stable_key="freelancehunt:project:990005001",
            analysis_quality_status="QUALITY_VALID",
            title="Synthetic PostgreSQL Stage 5A project",
            project_id="990005001",
            thread_id="",
            url="https://freelancehunt.com/project/synthetic/990005001.html",
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
            proposal_version="pqg-v3-synthetic-e2e",
            proposal_content_sha256=hashlib.sha256(proposal.encode()).hexdigest(),
            live_status="ACTIVE_BIDDABLE",
        )
        opportunity = await service.ensure_from_validated_job(job)
        opportunity, bid_confirmation, created = await service.mark_bid_sent(
            opportunity.id,
            "1200 USD",
            "5 days",
            confirmed_at=NOW - timedelta(minutes=3),
        )
        self.assertTrue(created)
        self.assertEqual(bid_confirmation.proposal_version, job.proposal_version)

        email = EmailMessage(
            id="synthetic-gmail-private-1",
            subject="New private message from Synthetic Client",
            sender="Freelancehunt <notify@freelancehunt.com>",
            body=(
                "Please clarify the authentication details.\n"
                "https://freelancehunt.com/project/synthetic/990005001.html"
            ),
            text_body=(
                "Please clarify the authentication details.\n"
                "https://freelancehunt.com/project/synthetic/990005001.html"
            ),
            links=["https://freelancehunt.com/project/synthetic/990005001.html"],
            received_at=NOW - timedelta(seconds=60),
            raw_headers={"Message-ID": "<synthetic-private-1@freelancehunt.com>"},
        )
        result = await service.process_client_message(email)
        self.assertEqual(result.reply_turn.reply_version, "r1")
        telegram = SimpleNamespace(send_message=AsyncMock())
        self.assertTrue(await send_sales_response_card(telegram, 1, result))
        telegram.send_message.assert_awaited()
        await service.mark_notified(result.incoming_turn.id)
        opportunity, sent_confirmation, sent_created = await service.mark_reply_sent(
            opportunity.id, "r1", confirmed_at=NOW
        )
        self.assertTrue(sent_created)
        self.assertEqual(sent_confirmation.content_sha256, result.reply_turn.content_sha256)
        self.assertEqual(opportunity.state, OpportunityState.WAITING_CLIENT.value)

        restarted = SalesCloserService(
            PostgresSalesRepository(self.sessions), reply_generator=_generator, now=lambda: NOW
        )
        persisted, transitions, turns, requests = await restarted.lead_timeline(opportunity.id)
        self.assertEqual(persisted.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual([turn.direction for turn in turns], ["INCOMING", "OUTGOING_CONFIRMED"])
        self.assertEqual(len(requests), 0)
        self.assertEqual(transitions[-1].new_state, OpportunityState.WAITING_CLIENT.value)

        # Nullable unique identifiers must not collide across opportunities.
        second_values = vars(job).copy()
        second_values.update(
            stable_key="freelancehunt:project:990005002",
            project_id="990005002",
            url="https://freelancehunt.com/project/synthetic/990005002.html",
            proposal_version="pqg-v3-synthetic-e2e-2",
        )
        second = await restarted.ensure_from_validated_job(SimpleNamespace(**second_values))
        second, _confirmation, _created = await restarted.mark_bid_sent(
            second.id, "1200 USD", "5 days"
        )
        second_email = EmailMessage(
            id="synthetic-gmail-private-2",
            subject="New private message from Another Client",
            sender="Freelancehunt <notify@freelancehunt.com>",
            body=(
                "Please clarify the authentication details.\n"
                "https://freelancehunt.com/project/synthetic/990005002.html"
            ),
            text_body=(
                "Please clarify the authentication details.\n"
                "https://freelancehunt.com/project/synthetic/990005002.html"
            ),
            links=["https://freelancehunt.com/project/synthetic/990005002.html"],
            received_at=NOW,
            raw_headers={"Message-ID": "<synthetic-private-2@freelancehunt.com>"},
        )
        second_result = await restarted.process_client_message(second_email)
        self.assertEqual(second_result.opportunity.id, second.id)
        self.assertEqual(second_result.reply_turn.reply_version, "r1")
