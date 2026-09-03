"""Real-PostgreSQL regressions for nullable Score/Fit metadata boundaries.

Set ``PQG_TEST_DATABASE_URL`` to an isolated PostgreSQL database to run these
tests.  All RSS and live-status inputs are synthetic; no network, Telegram,
Gmail, OpenAI, or Freelancehunt account action is performed.
"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from email.utils import format_datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from gmail_agent.digest_parser import DigestJobCandidate
from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.email_classifier import EmailType
from gmail_agent.freelancehunt_discovery import (
    FreelancehuntDiscoveryPipeline,
    FreelancehuntFeedClient,
)
from gmail_agent.gmail_provider import EmailMessage
from gmail_agent.live_status import LiveStatus, LiveStatusResult
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.project_identity import freelancehunt_project_stable_key
from gmail_agent.quality_gate import (
    SCORE_FAILED,
    SCORE_INVALID,
    SCORE_MISSING,
    SCORE_VALID,
    is_proposal_ready,
    normalize_score_metadata,
    score_display,
)
from gmail_agent.storage import PostgresGmailRepository, StoredGmailJob


TEST_DATABASE_URL = os.environ.get("PQG_TEST_DATABASE_URL", "").strip()


def _official_rss(project_id: int) -> str:
    now = datetime.now(timezone.utc)
    published = format_datetime(now)
    url = f"https://freelancehunt.com/project/synthetic-{project_id}/{project_id}.html"
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Official projects</title>"
        f"<lastBuildDate>{published}</lastBuildDate><item>"
        "<title>Nullable metadata regression fixture</title>"
        "<description>Synthetic public specification for persistence testing.</description>"
        f"<pubDate>{published}</pubDate><link>{url}</link><guid>{url}</guid>"
        "<category>Testing</category></item></channel></rss>"
    )


class _StatusChecker:
    def __init__(self, status: LiveStatus) -> None:
        self.status = status
        self.calls = 0

    async def check(self, _url: str) -> LiveStatusResult:
        self.calls += 1
        return LiveStatusResult(
            status=self.status,
            checked_at=datetime.now(timezone.utc),
            evidence=f"synthetic {self.status.value} status evidence",
            biddable=(True if self.status == LiveStatus.ACTIVE_BIDDABLE else False),
            last_error=(
                "synthetic read-only status check did not resolve"
                if self.status == LiveStatus.LIVE_STATUS_UNKNOWN
                else ""
            ),
        )


def _stored_job(stable_key: str, **overrides: object) -> StoredGmailJob:
    values: dict[str, object] = {
        "stable_key": stable_key,
        "source_email_id": f"source:{stable_key}",
        "platform": "Freelancehunt",
        "title": "Synthetic persistence fixture",
        "score": 8.0,
        "reason": "synthetic regression reason",
        "budget": "100 UAH",
        "url": "https://freelancehunt.com/project/synthetic/990000002.html",
        "urgency": "low",
        "why_relevant": "synthetic fixture",
        "score_valid": True,
        "score_raw": "8",
        "score_state": SCORE_VALID,
        "fit_score": 7.0,
        "fit_score_valid": True,
        "fit_score_raw": "7",
        "fit_score_state": SCORE_VALID,
    }
    values.update(overrides)
    return StoredGmailJob(**values)


def _active_analysis(candidate: DigestJobCandidate) -> JobAnalysis:
    return JobAnalysis(
        email_id=candidate.stable_key,
        is_relevant=True,
        title=candidate.title,
        platform="Freelancehunt",
        score=8.0,
        reason="Synthetic full commercial assessment.",
        budget=candidate.budget or "100 UAH",
        url=candidate.url,
        urgency="medium",
        why_relevant="Truthfully executable online work.",
        event_type=candidate.event_type,
        source_email_id=candidate.source_email_id,
        full_description=candidate.description,
        description_completeness="FULL",
        language="en",
        category=candidate.category,
        project_id=candidate.project_id,
        service_lane="testing",
        executable="yes",
        fit_score=7.0,
        score_valid=True,
        score_raw="8",
        score_state=SCORE_VALID,
        fit_score_valid=True,
        fit_score_raw="7",
        fit_score_state=SCORE_VALID,
        win_probability_signal="medium",
        scope_clarity="medium",
        estimated_effort="1-2 days",
        delivery_risk="low",
        client_payment_risk="unknown",
        project_mode="CASH",
        project_mode_reason="Synthetic executable first-cycle work.",
        recommended_price="100 UAH",
        realistic_timeline="1 day",
        evidence_case_id="NO_DIRECT_CASE",
        evidence="The synthetic source supports this assessment.",
        proposal_draft="We can deliver the requested synthetic scope.",
        next_action="Adult owner reviews and submits manually.",
        tags=candidate.tags,
        budget_currency=candidate.budget_currency,
        discovery_source=candidate.discovery_source,
        discovery_sources=candidate.discovery_source,
        source_publication_at=candidate.source_publication_at,
        source_feed_timestamp=candidate.source_feed_timestamp,
        feed_fetched_at=candidate.feed_fetched_at,
        first_seen_at=candidate.first_seen_at,
    )


class TestScoreFitNormalizationContract(unittest.TestCase):
    def test_semantic_matrix(self) -> None:
        cases = (
            ("missing_none", None, None, "", None, True, 0.0, False, SCORE_MISSING, "—"),
            ("missing_empty", "", None, "", None, True, 0.0, False, SCORE_MISSING, "—"),
            ("malformed", "bad", "bad", "", None, True, 0.0, False, SCORE_INVALID, "INVALID"),
            ("nan", float("nan"), None, "", None, True, 0.0, False, SCORE_INVALID, "INVALID"),
            ("infinity", float("inf"), None, "", None, True, 0.0, False, SCORE_INVALID, "INVALID"),
            ("provider_failure", None, None, "", None, False, 0.0, False, SCORE_FAILED, "FAILED"),
            ("real_zero", 0.0, "0", "", None, True, 0.0, True, SCORE_VALID, "0.0/10"),
            ("valid", 7.25, "7.25", "", None, True, 7.25, True, SCORE_VALID, "7.2/10"),
        )
        for (
            name,
            value,
            raw,
            explicit_state,
            explicit_valid,
            succeeded,
            expected_value,
            expected_valid,
            expected_state,
            expected_display,
        ) in cases:
            with self.subTest(name=name):
                metadata = normalize_score_metadata(
                    value,
                    raw=raw,
                    explicit_state=explicit_state,
                    explicit_valid=explicit_valid,
                    analysis_succeeded=succeeded,
                )
                self.assertEqual(metadata.value, expected_value)
                self.assertIs(metadata.valid, expected_valid)
                self.assertEqual(metadata.state, expected_state)
                self.assertIsInstance(metadata.raw, str)
                self.assertEqual(
                    score_display(
                        metadata.value,
                        raw=metadata.raw,
                        explicit_state=metadata.state,
                        explicit_valid=metadata.valid,
                    ),
                    expected_display,
                )

    def test_both_processor_construction_paths_normalize_score_and_fit(self) -> None:
        analysis = JobAnalysis(
            email_id="nullable-analysis",
            is_relevant=False,
            title="Synthetic nullable analysis",
            platform="Freelancehunt",
            score=None,
            reason="synthetic",
            budget="",
            url="https://freelancehunt.com/project/synthetic/990000003.html",
            urgency="low",
            why_relevant="",
            fit_score=None,
            score_valid=None,
            score_state="",
            fit_score_valid=None,
            fit_score_state="",
        )
        candidate = DigestJobCandidate(
            source_email_id="rss:990000003",
            platform="Freelancehunt",
            title=analysis.title,
            description="Synthetic source context",
            budget="",
            url=analysis.url,
            category="Testing",
            received_at=None,
            stable_key="candidate-nullable",
            project_id="990000003",
            discovery_source="rss",
            event_type=EmailType.PROJECT_FEED.value,
        )
        digest_job = GmailJobProcessor._stored_job(candidate, analysis)
        self.assertEqual(
            (
                digest_job.score,
                digest_job.score_valid,
                digest_job.score_state,
                digest_job.fit_score,
                digest_job.fit_score_valid,
                digest_job.fit_score_state,
            ),
            (0.0, False, SCORE_MISSING, 0.0, False, SCORE_MISSING),
        )
        single = EmailMessage(
            id="gmail-nullable",
            subject=analysis.title,
            sender="alerts@freelancehunt.com",
            body="Synthetic source context",
            received_at=datetime.now(timezone.utc),
        )
        single_job = GmailJobProcessor._stored_single_job(single, analysis)
        self.assertEqual(
            (
                single_job.score_valid,
                single_job.score_state,
                single_job.fit_score_valid,
                single_job.fit_score_state,
            ),
            (False, SCORE_MISSING, False, SCORE_MISSING),
        )

        analysis.analysis_succeeded = False
        failed_job = GmailJobProcessor._stored_job(candidate, analysis)
        self.assertEqual(
            (
                failed_job.score_valid,
                failed_job.score_state,
                failed_job.fit_score_valid,
                failed_job.fit_score_state,
            ),
            (False, SCORE_FAILED, False, SCORE_FAILED),
        )


@unittest.skipUnless(TEST_DATABASE_URL, "PQG_TEST_DATABASE_URL is not configured")
class TestNullableScoreFitMetadataPostgres(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        # Defer the production settings import until this opt-in PostgreSQL
        # class actually runs; skipped tests must not mutate process-wide env.
        os.environ.setdefault("TELEGRAM_TOKEN", "synthetic-test-token")
        os.environ.setdefault("TELEGRAM_CHAT_ID", "1")
        os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
        from db.models import Base

        self.schema = f"pqg_nullable_{uuid4().hex}"
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
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.repository = PostgresGmailRepository(self.sessions)

    async def _assert_metadata(
        self,
        stable_key: str,
        *,
        score_state: str,
        fit_state: str,
        score_valid: bool,
        fit_valid: bool,
    ) -> StoredGmailJob:
        job = await self.repository.get_job(stable_key)
        self.assertIsNotNone(job)
        self.assertIsInstance(job.score, float)
        self.assertIsInstance(job.fit_score, float)
        self.assertIs(job.score_valid, score_valid)
        self.assertIs(job.fit_score_valid, fit_valid)
        self.assertEqual(job.score_state, score_state)
        self.assertEqual(job.fit_score_state, fit_state)
        self.assertIsInstance(job.score_raw, str)
        self.assertIsInstance(job.fit_score_raw, str)
        if score_state != SCORE_VALID or fit_state != SCORE_VALID:
            self.assertFalse(is_proposal_ready(job))
        return job

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        cleanup = create_async_engine(TEST_DATABASE_URL)
        async with cleanup.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await cleanup.dispose()

    async def test_official_rss_unknown_status_persists_concrete_metadata(self) -> None:
        """The exact incident route must never send nullable flags to Postgres."""

        project_id = 990000001

        async def fetcher() -> str:
            return _official_rss(project_id)

        checker = _StatusChecker(LiveStatus.LIVE_STATUS_UNKNOWN)
        pipeline = FreelancehuntDiscoveryPipeline(
            repository=self.repository,
            bot=object(),
            chat_id=1,
            feed_client=FreelancehuntFeedClient(fetcher=fetcher),
            live_status_checker=checker,
            max_new_projects_per_scan=1,
        )
        analyze = AsyncMock()
        notice = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_live_status_card", notice),
        ):
            stats = await pipeline.run()
            second = await pipeline.run()
            restarted = FreelancehuntDiscoveryPipeline(
                repository=PostgresGmailRepository(self.sessions),
                bot=object(),
                chat_id=1,
                feed_client=FreelancehuntFeedClient(fetcher=fetcher),
                live_status_checker=checker,
                max_new_projects_per_scan=1,
            )
            restart_stats = await restarted.run()

        analyze.assert_not_awaited()
        self.assertEqual(stats.live_status_unknown, 1)
        self.assertEqual((stats.errors, second.errors, restart_stats.errors), (0, 0, 0))
        self.assertEqual(checker.calls, 1)
        self.assertEqual(notice.await_count, 1)
        stable_key = freelancehunt_project_stable_key(project_id=str(project_id))
        job = await self.repository.get_job(stable_key)
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "live_status_pending")
        self.assertEqual(job.score, 0.0)
        self.assertIs(job.score_valid, False)
        self.assertEqual(job.score_state, "MISSING")
        self.assertEqual(job.fit_score, 0.0)
        self.assertIs(job.fit_score_valid, False)
        self.assertEqual(job.fit_score_state, "MISSING")
        self.assertFalse(job.qualified)
        self.assertEqual(job.proposal_draft, "")

    async def test_postgres_semantic_insert_matrix(self) -> None:
        cases = (
            ("fit-valid-none", {"fit_score": None, "fit_score_valid": None, "fit_score_raw": "", "fit_score_state": ""}, SCORE_VALID, SCORE_MISSING, True, False),
            ("score-valid-none", {"score": None, "score_valid": None, "score_raw": "", "score_state": ""}, SCORE_MISSING, SCORE_VALID, False, True),
            ("both-missing", {"score": None, "score_valid": None, "score_raw": None, "score_state": None, "fit_score": None, "fit_score_valid": None, "fit_score_raw": None, "fit_score_state": None}, SCORE_MISSING, SCORE_MISSING, False, False),
            ("malformed-score", {"score": "bad", "score_valid": None, "score_raw": "bad", "score_state": ""}, SCORE_INVALID, SCORE_VALID, False, True),
            ("malformed-fit", {"fit_score": "bad", "fit_score_valid": None, "fit_score_raw": "bad", "fit_score_state": ""}, SCORE_VALID, SCORE_INVALID, True, False),
            ("nan-score", {"score": float("nan"), "score_valid": None, "score_state": ""}, SCORE_INVALID, SCORE_VALID, False, True),
            ("infinite-fit", {"fit_score": float("inf"), "fit_score_valid": None, "fit_score_state": ""}, SCORE_VALID, SCORE_INVALID, True, False),
            ("provider-failure", {"score": None, "score_valid": None, "score_state": SCORE_FAILED, "fit_score": None, "fit_score_valid": None, "fit_score_state": SCORE_FAILED}, SCORE_FAILED, SCORE_FAILED, False, False),
            ("zero-nonexec", {"executable": "no", "score": 0.0, "score_valid": True, "score_raw": "0", "score_state": SCORE_VALID, "fit_score": 0.0, "fit_score_valid": True, "fit_score_raw": "0", "fit_score_state": SCORE_VALID}, SCORE_VALID, SCORE_VALID, True, True),
            ("zero-exec", {"executable": "yes", "score": 0.0, "score_valid": True, "score_raw": "0", "score_state": SCORE_VALID, "fit_score": 0.0, "fit_score_valid": True, "fit_score_raw": "0", "fit_score_state": SCORE_VALID}, SCORE_VALID, SCORE_VALID, True, True),
            ("different-valid", {"score": 9.0, "score_valid": True, "score_raw": "9", "score_state": SCORE_VALID, "fit_score": 6.5, "fit_score_valid": True, "fit_score_raw": "6.5", "fit_score_state": SCORE_VALID}, SCORE_VALID, SCORE_VALID, True, True),
        )
        for name, overrides, score_state, fit_state, score_valid, fit_valid in cases:
            with self.subTest(name=name):
                await self.repository.save_job(_stored_job(name, **overrides))
                loaded = await self._assert_metadata(
                    name,
                    score_state=score_state,
                    fit_state=fit_state,
                    score_valid=score_valid,
                    fit_valid=fit_valid,
                )
                if name in {"zero-nonexec", "zero-exec"}:
                    self.assertEqual((loaded.score, loaded.fit_score), (0.0, 0.0))
                    self.assertFalse(is_proposal_ready(loaded))
                if name == "different-valid":
                    self.assertEqual((loaded.score, loaded.fit_score), (9.0, 6.5))

    async def test_blocked_and_active_rss_paths_use_concrete_metadata(self) -> None:
        async def blocked_feed() -> str:
            return _official_rss(990000010)

        blocked_checker = _StatusChecker(LiveStatus.BLOCKED_RULE_VIOLATION)
        blocked_pipeline = FreelancehuntDiscoveryPipeline(
            repository=self.repository,
            bot=object(),
            chat_id=1,
            feed_client=FreelancehuntFeedClient(fetcher=blocked_feed),
            live_status_checker=blocked_checker,
            max_new_projects_per_scan=1,
        )
        analyze = AsyncMock()
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch(
                "gmail_agent.processor.send_live_status_card",
                AsyncMock(return_value=True),
            ),
        ):
            blocked_stats = await blocked_pipeline.run()
        analyze.assert_not_awaited()
        self.assertEqual(blocked_stats.errors, 0)
        blocked_key = freelancehunt_project_stable_key(project_id="990000010")
        blocked = await self._assert_metadata(
            blocked_key,
            score_state=SCORE_MISSING,
            fit_state=SCORE_MISSING,
            score_valid=False,
            fit_valid=False,
        )
        self.assertEqual(blocked.status, "live_status_terminal")
        self.assertFalse(blocked.biddable)
        self.assertFalse(blocked.qualified)

        async def active_feed() -> str:
            return _official_rss(990000011)

        active_pipeline = FreelancehuntDiscoveryPipeline(
            repository=self.repository,
            bot=object(),
            chat_id=1,
            feed_client=FreelancehuntFeedClient(fetcher=active_feed),
            live_status_checker=_StatusChecker(LiveStatus.ACTIVE_BIDDABLE),
            max_new_projects_per_scan=1,
        )
        send = AsyncMock(return_value=True)
        with (
            patch(
                "gmail_agent.processor.analyze_candidate",
                AsyncMock(side_effect=lambda candidate, **_: _active_analysis(candidate)),
            ),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            active_stats = await active_pipeline.run()
        self.assertEqual(active_stats.errors, 0)
        active_key = freelancehunt_project_stable_key(project_id="990000011")
        active = await self._assert_metadata(
            active_key,
            score_state=SCORE_VALID,
            fit_state=SCORE_VALID,
            score_valid=True,
            fit_valid=True,
        )
        self.assertEqual(active.live_status, LiveStatus.ACTIVE_BIDDABLE.value)
        self.assertTrue(active.biddable)
        self.assertEqual(send.await_count, 1)

    async def test_conflict_upsert_update_backfill_and_restart_are_defensive(self) -> None:
        key = "all-write-boundaries"
        await self.repository.save_job(_stored_job(key))

        await self.repository.save_job(
            _stored_job(
                key,
                score=None,
                score_valid=None,
                score_raw=None,
                score_state=None,
                fit_score=None,
                fit_score_valid=None,
                fit_score_raw=None,
                fit_score_state=None,
            )
        )
        await self._assert_metadata(
            key,
            score_state=SCORE_MISSING,
            fit_state=SCORE_MISSING,
            score_valid=False,
            fit_valid=False,
        )

        updated = await self.repository.update_job_fields(
            key,
            {
                "score": "malformed",
                "score_valid": None,
                "score_raw": "malformed",
                "score_state": None,
                "fit_score": float("inf"),
                "fit_score_valid": None,
                "fit_score_raw": None,
                "fit_score_state": None,
            },
        )
        self.assertIsNotNone(updated)
        await self._assert_metadata(
            key,
            score_state=SCORE_INVALID,
            fit_state=SCORE_INVALID,
            score_valid=False,
            fit_valid=False,
        )

        backfilled = await self.repository.apply_backfill_live_result(
            key,
            "synthetic-audit-snapshot",
            {
                "score": 7.0,
                "score_valid": True,
                "score_raw": "7",
                "score_state": SCORE_VALID,
                "fit_score": None,
                "fit_score_valid": None,
                "fit_score_raw": "",
                "fit_score_state": "",
                "status": "quality_review_pending",
            },
        )
        self.assertIsNotNone(backfilled)
        self.assertEqual(backfilled.original_analysis_snapshot, "synthetic-audit-snapshot")
        await self._assert_metadata(
            key,
            score_state=SCORE_VALID,
            fit_state=SCORE_MISSING,
            score_valid=True,
            fit_valid=False,
        )

        restarted = PostgresGmailRepository(self.sessions)
        reloaded = await restarted.get_job(key)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.fit_score_state, SCORE_MISSING)
        self.assertIs(reloaded.fit_score_valid, False)

    async def test_impossible_proposal_ready_metadata_fails_safe(self) -> None:
        job = _stored_job(
            "unsafe-ready",
            score=None,
            score_valid=None,
            score_raw=None,
            score_state=None,
            fit_score=None,
            fit_score_valid=None,
            fit_score_raw=None,
            fit_score_state=None,
            executable="yes",
            qualified=True,
            live_status=LiveStatus.ACTIVE_BIDDABLE.value,
            live_status_checked_at=datetime.now(timezone.utc),
            biddable=True,
            analysis_quality_status="QUALITY_VALID",
            recommended_price="100 UAH",
            realistic_timeline="1 day",
            proposal_draft="Synthetic unsafe proposal",
        )
        saved = await self.repository.save_job(job)
        self.assertEqual(saved.status, "quality_manual_review")
        self.assertEqual(saved.analysis_quality_status, "QUALITY_MANUAL_REVIEW")
        self.assertFalse(saved.qualified)
        self.assertEqual(saved.proposal_draft, "")
        self.assertIn("score_metadata_contract_violation", saved.quality_errors)
        self.assertFalse(is_proposal_ready(saved))

    async def test_migrations_are_additive_idempotent_on_clean_and_existing_schema(self) -> None:
        from db.models import init_db

        async def assert_contract(engine: object, schema: str) -> None:
            async with engine.connect() as connection:
                rows = (
                    await connection.execute(
                        text(
                            "SELECT column_name, is_nullable, column_default, data_type "
                            "FROM information_schema.columns "
                            "WHERE table_schema=:schema AND table_name='gmail_jobs' "
                            "AND column_name IN "
                            "('score_valid','fit_score_valid','score_state','fit_score_state')"
                        ),
                        {"schema": schema},
                    )
                ).mappings().all()
            columns = {row["column_name"]: row for row in rows}
            self.assertEqual(set(columns), {
                "score_valid",
                "fit_score_valid",
                "score_state",
                "fit_score_state",
            })
            for name in columns:
                self.assertEqual(columns[name]["is_nullable"], "NO")
            self.assertEqual(columns["score_valid"]["data_type"], "boolean")
            self.assertEqual(columns["fit_score_valid"]["data_type"], "boolean")
            self.assertIn("false", columns["score_valid"]["column_default"])
            self.assertIn("false", columns["fit_score_valid"]["column_default"])

        clean_schema = f"pqg_clean_{uuid4().hex}"
        bootstrap = create_async_engine(TEST_DATABASE_URL)
        async with bootstrap.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{clean_schema}"'))
        await bootstrap.dispose()
        clean_engine = create_async_engine(
            TEST_DATABASE_URL,
            connect_args={"server_settings": {"search_path": clean_schema}},
        )
        try:
            with patch("db.engine", clean_engine):
                await init_db()
                await init_db()
            await assert_contract(clean_engine, clean_schema)
            clean_sessions = async_sessionmaker(clean_engine, expire_on_commit=False)
            clean_repository = PostgresGmailRepository(clean_sessions)
            saved = await clean_repository.save_job(
                _stored_job(
                    "clean-migration-write",
                    fit_score=None,
                    fit_score_valid=None,
                    fit_score_raw=None,
                    fit_score_state=None,
                )
            )
            self.assertIs(saved.fit_score_valid, False)
            self.assertEqual(saved.fit_score_state, SCORE_MISSING)
        finally:
            await clean_engine.dispose()
            cleanup = create_async_engine(TEST_DATABASE_URL)
            async with cleanup.begin() as connection:
                await connection.execute(
                    text(f'DROP SCHEMA "{clean_schema}" CASCADE')
                )
            await cleanup.dispose()

        # ``asyncSetUp`` already created the production-like schema with all
        # Stage 4 columns present. Re-running migrations twice must be a no-op.
        with patch("db.engine", self.engine):
            await init_db()
            await init_db()
        await assert_contract(self.engine, self.schema)
        existing = await self.repository.save_job(
            _stored_job(
                "existing-columns-write",
                score=None,
                score_valid=None,
                score_raw=None,
                score_state=None,
            )
        )
        self.assertIs(existing.score_valid, False)
        self.assertEqual(existing.score_state, SCORE_MISSING)


if __name__ == "__main__":
    unittest.main()
