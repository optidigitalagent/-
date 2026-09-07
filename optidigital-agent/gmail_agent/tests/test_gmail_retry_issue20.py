"""Issue #20 Gmail resilience regressions; no Gmail account is contacted."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.gmail_provider import GmailRequestError, RealGmailProvider
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.storage import InMemoryGmailRepository, PostgresGmailRepository


TEST_DATABASE_URL = os.environ.get("ISSUE20_TEST_DATABASE_URL", "").strip()


class FakeHttpError(Exception):
    def __init__(
        self,
        status: int,
        message: str = "synthetic",
        *,
        reasons: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.resp = SimpleNamespace(status=status)
        self.content = (
            json.dumps(
                {
                    "error": {
                        "errors": [
                            {"reason": reason, "message": "synthetic"}
                            for reason in (reasons or [])
                        ]
                    }
                }
            ).encode("utf-8")
            if reasons is not None
            else b""
        )


def _request(*values):
    request = MagicMock()
    request.execute.side_effect = list(values)
    return request


def _metadata(
    message_id: str,
    *,
    sender: str = "Freelancehunt <info@freelancehunt.com>",
    subject: str = "New project selected for you",
) -> dict:
    return {
        "id": message_id,
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Sat, 05 Sep 2026 10:00:00 +0000"},
            ]
        },
    }


def _full(
    message_id: str,
    *,
    sender: str = "Freelancehunt <info@freelancehunt.com>",
    subject: str = "New project selected for you",
) -> dict:
    encoded = base64.urlsafe_b64encode(b"Public project body").decode().rstrip("=")
    value = _metadata(message_id, sender=sender, subject=subject)
    value["payload"]["mimeType"] = "text/plain"
    value["payload"]["body"] = {"data": encoded}
    return value


def _provider(ids: list[str], get_factory, *, attempts: int = 3) -> RealGmailProvider:
    provider = RealGmailProvider(
        "unused.json",
        "unused-token.json",
        request_max_attempts=attempts,
        retry_base_seconds=0,
        retry_cap_seconds=0,
    )
    service = MagicMock()
    messages = service.users.return_value.messages.return_value
    messages.list.return_value = _request({"messages": [{"id": value} for value in ids]})
    messages.get.side_effect = get_factory
    provider._service = service
    return provider


class TestGmailBoundedRetry(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_500_then_success_is_recovered_without_pending_failure(self):
        calls: dict[tuple[str, str], MagicMock] = {}

        def get(**kwargs):
            key = (kwargs["id"], kwargs["format"])
            if key not in calls:
                calls[key] = (
                    _request(FakeHttpError(500), _metadata(kwargs["id"]))
                    if kwargs["format"] == "metadata"
                    else _request(_full(kwargs["id"]))
                )
            return calls[key]

        provider = _provider(["one"], get)
        with patch("gmail_agent.gmail_provider.asyncio.sleep", AsyncMock()) as sleep:
            emails = await provider.get_new_emails()
        failures, completed = provider.drain_fetch_outcomes()
        self.assertEqual([email.id for email in emails], ["one"])
        self.assertEqual(failures, [])
        self.assertEqual(completed, ["one"])
        self.assertEqual(sleep.await_count, 1)

    async def test_full_503_then_success_is_recovered(self):
        calls: dict[tuple[str, str], MagicMock] = {}

        def get(**kwargs):
            key = (kwargs["id"], kwargs["format"])
            if key not in calls:
                calls[key] = (
                    _request(_metadata(kwargs["id"]))
                    if kwargs["format"] == "metadata"
                    else _request(FakeHttpError(503), _full(kwargs["id"]))
                )
            return calls[key]

        provider = _provider(["one"], get)
        with patch("gmail_agent.gmail_provider.asyncio.sleep", AsyncMock()):
            emails = await provider.get_new_emails()
        failures, completed = provider.drain_fetch_outcomes()
        self.assertEqual([email.id for email in emails], ["one"])
        self.assertEqual(failures, [])
        self.assertEqual(completed, ["one"])

    async def test_bad_message_between_two_good_is_pending_without_losing_good(self):
        def get(**kwargs):
            if kwargs["id"] == "bad" and kwargs["format"] == "metadata":
                return _request(FakeHttpError(502), FakeHttpError(502), FakeHttpError(502))
            return _request(
                _metadata(kwargs["id"]) if kwargs["format"] == "metadata" else _full(kwargs["id"])
            )

        provider = _provider(["good-1", "bad", "good-2"], get)
        with patch("gmail_agent.gmail_provider.asyncio.sleep", AsyncMock()):
            emails = await provider.get_new_emails()
        failures, completed = provider.drain_fetch_outcomes()
        self.assertEqual([email.id for email in emails], ["good-1", "good-2"])
        self.assertEqual(completed, ["good-1", "good-2"])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].message_id, "bad")
        self.assertEqual(failures[0].attempts, 3)

    async def test_auth_and_permission_fail_immediately_and_are_not_oauth_relabelled(self):
        for status, category, reasons in (
            (401, "AUTH", None),
            (403, "PERMISSION", ["forbidden"]),
        ):
            with self.subTest(status=status):
                provider = _provider(
                    ["one"],
                    lambda **_: _request(FakeHttpError(status, reasons=reasons)),
                )
                with self.assertRaisesRegex(GmailRequestError, category):
                    await provider.get_new_emails()

    def test_structured_403_reasons_precede_exception_text(self):
        cases = (
            ("rateLimitExceeded", "RATE_LIMIT", "oauth permission denied"),
            ("userRateLimitExceeded", "RATE_LIMIT", "invalid credentials"),
            ("authError", "AUTH", "quota rate limit"),
            ("insufficientPermissions", "PERMISSION", "quota rate limit"),
            ("domainPolicy", "PERMISSION", "quota rate limit"),
            ("futureUnknownReason", "UNKNOWN", "quota rate limit"),
        )
        for reason, expected, misleading_text in cases:
            with self.subTest(reason=reason):
                status, category = RealGmailProvider._gmail_error_details(
                    FakeHttpError(403, misleading_text, reasons=[reason])
                )
                self.assertEqual(status, 403)
                self.assertEqual(category, expected)

    def test_403_without_structured_reason_remains_unknown(self):
        self.assertEqual(
            RealGmailProvider._gmail_error_details(
                FakeHttpError(403, "quota rate limit permission")
            ),
            (403, "UNKNOWN"),
        )


class TestDurableFetchState(unittest.IsolatedAsyncioTestCase):
    async def test_restart_due_retry_recovery_and_alert_dedup(self):
        state: dict[str, object] = {}
        repository = InMemoryGmailRepository(state)
        old = datetime.now(timezone.utc) - timedelta(hours=2)
        for cycle in range(3):
            saved = await repository.record_gmail_fetch_failure(
                message_id="pending-id",
                stage="full",
                status_code=504,
                category="TRANSIENT_SERVER",
                attempts=3,
                safe_error="Gmail full failed after bounded retry (504)",
                now=old + timedelta(minutes=cycle),
            )
        self.assertEqual(saved.cycle_count, 3)
        self.assertIsNone(saved.alerted_at)

        restarted = InMemoryGmailRepository(state)
        due = await restarted.list_due_gmail_fetch_retries()
        self.assertEqual([item.message_id for item in due], ["pending-id"])
        await restarted.mark_gmail_fetch_retry_alerted("pending-id")
        marked = (await restarted.list_pending_gmail_fetch_retries())[0]
        self.assertIsNotNone(marked.alerted_at)
        # A later failed cycle retains the first alert marker.
        again = await restarted.record_gmail_fetch_failure(
            message_id="pending-id",
            stage="full",
            status_code=504,
            category="TRANSIENT_SERVER",
            attempts=3,
            safe_error="Gmail full failed after bounded retry (504)",
        )
        self.assertIsNotNone(again.alerted_at)
        await restarted.resolve_gmail_fetch_retry("pending-id")
        self.assertEqual(await restarted.list_pending_gmail_fetch_retries(), [])

    async def test_processor_escalates_only_third_cycle_once(self):
        repository = InMemoryGmailRepository()
        processor = GmailJobProcessor(MagicMock(), MagicMock(), 1, repository=repository)
        failure = SimpleNamespace(
            message_id="one",
            stage="metadata",
            status_code=500,
            category="TRANSIENT_SERVER",
            attempts=3,
            safe_error="safe",
        )
        for expected_errors in (0, 0, 1, 0):
            stats = ProcessorStats()
            processor._provider.drain_fetch_outcomes.return_value = ([failure], [])
            await processor._persist_gmail_fetch_outcomes(stats)
            self.assertEqual(stats.errors, expected_errors)


@unittest.skipUnless(
    TEST_DATABASE_URL,
    "ISSUE20_TEST_DATABASE_URL is not configured",
)
class TestGmailRestartNoLossPostgres(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        os.environ.setdefault("TELEGRAM_TOKEN", "synthetic-test-token")
        os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
        os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
        from db.models import Base, _MIGRATIONS

        self.schema = f"issue20_gmail_{uuid4().hex}"
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
            for statement in _MIGRATIONS:
                await connection.execute(text(statement))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.temp = tempfile.TemporaryDirectory()
        self.delivery_messages: list[str] = []
        self.pending_seen_during_delivery: list[str] = []

    async def asyncTearDown(self) -> None:
        self.temp.cleanup()
        await self.engine.dispose()
        cleanup = create_async_engine(TEST_DATABASE_URL)
        async with cleanup.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await cleanup.dispose()

    async def _make_due(self) -> None:
        async with self.sessions() as session:
            await session.execute(
                text(
                    "UPDATE gmail_fetch_retries "
                    "SET next_retry_at = NOW() - INTERVAL '1 second' "
                    "WHERE resolved_at IS NULL"
                )
            )
            await session.commit()

    def _provider_for_cycle(self, *, recover: bool) -> RealGmailProvider:
        sender = "Work.ua <jobs@work.ua>"

        def get(**kwargs):
            message_id = kwargs["id"]
            if message_id == "pending" and not recover:
                return _request(
                    FakeHttpError(503),
                    FakeHttpError(503),
                    FakeHttpError(503),
                )
            value = (
                _metadata(message_id, sender=sender, subject="New vacancy")
                if kwargs["format"] == "metadata"
                else _full(message_id, sender=sender, subject="New vacancy")
            )
            return _request(value)

        return _provider(["good-1", "pending", "good-2"], get)

    @staticmethod
    async def _analysis(**kwargs) -> JobAnalysis:
        email_id = str(kwargs["email_id"])
        relevant = email_id == "pending"
        return JobAnalysis(
            email_id=email_id,
            is_relevant=relevant,
            title="Synthetic Work.ua vacancy",
            platform="Work.ua",
            score=8.0 if relevant else 1.0,
            reason="synthetic offline integration result",
            budget="not specified",
            url="",
            urgency="medium",
            why_relevant="synthetic recovery fixture" if relevant else "",
            analysis_succeeded=True,
            commercial_decision="TAKE" if relevant else "SKIP",
            executable="yes" if relevant else "no",
            description_completeness="FULL",
            next_action="Review the synthetic card." if relevant else "Do not bid.",
        )

    def _processor(self, provider: RealGmailProvider, repository: PostgresGmailRepository):
        outer = self

        class FakeTelegramTransport:
            async def send_message(self, *, text: str, **_kwargs):
                pending = await repository.list_pending_gmail_fetch_retries()
                outer.pending_seen_during_delivery.extend(
                    item.message_id for item in pending
                )
                outer.delivery_messages.append(text)
                return SimpleNamespace(message_id=len(outer.delivery_messages))

        temp_root = Path(self.temp.name)
        return GmailJobProcessor(
            provider,
            FakeTelegramTransport(),
            1,
            min_score=6.0,
            repository=repository,
            dedup_path=temp_root / "dedup.json",
            job_store_path=temp_root / "jobs.json",
        )

    async def test_persistent_5xx_restart_due_recovery_has_no_loss_window(self):
        alert_counts: list[int] = []
        with patch("gmail_agent.processor.analyze_email", side_effect=self._analysis):
            for cycle in range(3):
                repository = PostgresGmailRepository(self.sessions)
                processor = self._processor(
                    self._provider_for_cycle(recover=False),
                    repository,
                )
                stats = await processor.run(trigger=f"synthetic-failure-{cycle + 1}")
                alert_counts.append(stats.gmail_fetch_alerts)
                pending = await repository.list_pending_gmail_fetch_retries()
                self.assertEqual([item.message_id for item in pending], ["pending"])
                if cycle < 2:
                    await self._make_due()

            self.assertEqual(alert_counts, [0, 0, 1])
            await self._make_due()

            restarted_repository = PostgresGmailRepository(self.sessions)
            restarted_processor = self._processor(
                self._provider_for_cycle(recover=True),
                restarted_repository,
            )
            recovered = await restarted_processor.run(trigger="synthetic-recovery")

            self.assertEqual(recovered.gmail_fetch_recovered, 1)
            self.assertEqual(recovered.gmail_fetch_alerts, 0)
            self.assertIn("pending", self.pending_seen_during_delivery)
            self.assertEqual(
                await restarted_repository.list_pending_gmail_fetch_retries(),
                [],
            )
            self.assertEqual(len(self.delivery_messages), 1)
            stored = await restarted_repository.get_job("pending")
            self.assertIsNotNone(stored)
            self.assertEqual(stored.status, "sent")

            repeated_repository = PostgresGmailRepository(self.sessions)
            repeated_processor = self._processor(
                self._provider_for_cycle(recover=True),
                repeated_repository,
            )
            repeated = await repeated_processor.run(trigger="synthetic-repeat")
            self.assertEqual(len(self.delivery_messages), 1)
            self.assertEqual(repeated.gmail_fetch_alerts, 0)
            self.assertGreaterEqual(repeated.duplicates_skipped, 1)

            async with self.sessions() as session:
                job_count = await session.scalar(
                    text(
                        "SELECT COUNT(*) FROM gmail_jobs "
                        "WHERE source_email_id = 'pending'"
                    )
                )
                processed_counts = dict(
                    (
                        await session.execute(
                            text(
                                "SELECT source_email_id, COUNT(*) "
                                "FROM gmail_processed_items "
                                "WHERE source_email_id IN "
                                "('good-1', 'pending', 'good-2') "
                                "GROUP BY source_email_id"
                            )
                        )
                    ).all()
                )
            self.assertEqual(job_count, 1)
            self.assertEqual(
                processed_counts,
                {"good-1": 1, "pending": 1, "good-2": 1},
            )


if __name__ == "__main__":
    unittest.main()
