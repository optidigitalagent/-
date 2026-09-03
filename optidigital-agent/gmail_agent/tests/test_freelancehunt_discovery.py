"""Stage 3 contracts for official-RSS instant Freelancehunt discovery.

All project fixtures are synthetic.  Network, OpenAI, Gmail, PostgreSQL and
Telegram boundaries are replaced with deterministic test doubles.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.digest_parser import DigestJobCandidate
from gmail_agent.email_analyzer import JobAnalysis, analyze_candidate
from gmail_agent.email_classifier import EmailType
from gmail_agent.freelancehunt_discovery import (
    FeedParseError,
    FreelancehuntDiscoveryPipeline,
    FreelancehuntFeedClient,
    parse_freelancehunt_rss,
    register_freelancehunt_discovery_job,
)
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.live_status import LiveStatus, LiveStatusResult
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.project_identity import freelancehunt_project_stable_key
from gmail_agent.quality_gate import ANALYSIS_VERSION
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import TELEGRAM_TEXT_LIMIT, format_job_card_parts
from parser.base import BasePlatformParser
from parser.freelancehunt import FreelancehuntParser


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _rss_item(
    project_id: int,
    title: str,
    *,
    description: str = "Synthetic public specification. Budget 100 UAH.",
    category: str = "Synthetic services",
    published_at: datetime | None = None,
) -> str:
    published = published_at or datetime.now(timezone.utc) - timedelta(seconds=30)
    url = f"https://freelancehunt.com/project/synthetic-{project_id}/{project_id}.html"
    return f"""
      <item>
        <title>{escape(title)}</title>
        <description>{escape(description)}</description>
        <pubDate>{format_datetime(published)}</pubDate>
        <link>{url}</link>
        <guid>{url}?tracking=ignored</guid>
        <category>{escape(category)}</category>
      </item>
    """


def _rss(*items: str, built_at: datetime | None = None) -> str:
    built = built_at or datetime.now(timezone.utc)
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Official projects</title>"
        f"<lastBuildDate>{format_datetime(built)}</lastBuildDate>"
        f"{''.join(items)}</channel></rss>"
    )


class StaticChecker:
    def __init__(self, status: LiveStatus) -> None:
        self.status = status
        self.calls: list[str] = []

    async def check(self, url: str) -> LiveStatusResult:
        self.calls.append(url)
        return LiveStatusResult(
            status=self.status,
            checked_at=datetime.now(timezone.utc),
            evidence=f"synthetic {self.status.value} evidence",
            biddable=self.status == LiveStatus.ACTIVE_BIDDABLE,
            last_error=(
                "synthetic transient ambiguity"
                if self.status == LiveStatus.LIVE_STATUS_UNKNOWN
                else ""
            ),
        )


def _candidate_analysis(
    candidate: DigestJobCandidate,
    *,
    executable: str = "yes",
    score: float = 0.2,
    lane: str = "broad_online_service",
) -> JobAnalysis:
    relevant = executable != "no"
    return JobAnalysis(
        email_id=candidate.stable_key,
        is_relevant=relevant,
        title=candidate.title,
        platform="Freelancehunt",
        score=score,
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
        service_lane=lane,
        executable=executable,
        fit_score=score,
        win_probability_signal="medium",
        scope_clarity="medium",
        estimated_effort="1-2 days",
        delivery_risk="low",
        client_payment_risk="unknown",
        project_mode="CASH",
        project_mode_reason="Small but executable first-cycle work.",
        recommended_price="100 UAH" if relevant else "",
        realistic_timeline="1 day" if relevant else "",
        evidence_case_id="NO_DIRECT_CASE",
        evidence=f"The published source describes {candidate.title}.",
        proposal_draft=(
            f"We can deliver {candidate.title} using the published project requirements."
            if relevant
            else ""
        ),
        next_action=(
            "Adult owner reviews and submits manually."
            if relevant
            else "Do not bid."
        ),
        tags=candidate.tags,
        budget_currency=candidate.budget_currency,
        discovery_source=candidate.discovery_source,
        discovery_sources=candidate.discovery_source,
        source_publication_at=candidate.source_publication_at,
        source_feed_timestamp=candidate.source_feed_timestamp,
        feed_fetched_at=candidate.feed_fetched_at,
        first_seen_at=candidate.first_seen_at,
        analysis_version=ANALYSIS_VERSION,
    )


def _mock_openai_client(payload: dict[str, object]) -> MagicMock:
    choice = MagicMock()
    choice.message.content = json.dumps(payload)
    completion = MagicMock()
    completion.choices = [choice]
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=completion)
    return client


def _single_email(project_id: int) -> EmailMessage:
    url = f"https://freelancehunt.com/project/synthetic-{project_id}/{project_id}.html"
    return EmailMessage(
        id=f"gmail-{project_id}",
        sender="alerts@freelancehunt.com",
        subject="Новий проєкт: synthetic public project",
        body="Synthetic public specification. Budget 100 UAH.",
        text_body="Synthetic public specification. Budget 100 UAH.",
        received_at=datetime.now(timezone.utc) - timedelta(seconds=20),
        links=[url],
    )


class TestOfficialRssParsing(unittest.TestCase):
    def test_parses_canonical_identity_and_source_metadata(self):
        published = datetime.now(timezone.utc) - timedelta(seconds=30)
        batch = parse_freelancehunt_rss(
            _rss(
                _rss_item(
                    1700001,
                    "SEO &amp; content research",
                    description="Public SEO research specification. 100–200 USD.",
                    category="SEO",
                    published_at=published,
                )
            ),
            fetched_at=datetime.now(timezone.utc),
        )
        self.assertEqual(len(batch.candidates), 1)
        candidate = batch.candidates[0]
        self.assertEqual(candidate.project_id, "1700001")
        self.assertEqual(
            candidate.stable_key,
            freelancehunt_project_stable_key(project_id="1700001"),
        )
        self.assertEqual(candidate.discovery_source, "rss")
        self.assertEqual(candidate.event_type, EmailType.PROJECT_FEED.value)
        self.assertEqual(candidate.budget_currency, "USD")
        self.assertIn("SEO", candidate.tags)
        self.assertIsNotNone(candidate.source_publication_at)
        self.assertIsNotNone(candidate.source_feed_timestamp)
        self.assertIsNotNone(candidate.feed_fetched_at)

    def test_duplicate_project_id_in_feed_is_collapsed(self):
        item = _rss_item(1700002, "Synthetic duplicate")
        batch = parse_freelancehunt_rss(_rss(item, item))
        self.assertEqual(len(batch.candidates), 1)

    def test_malformed_and_non_rss_documents_fail_closed(self):
        for payload in ("", "<rss>", "<html><body>not rss</body></html>"):
            with self.subTest(payload=payload):
                with self.assertRaises(FeedParseError):
                    parse_freelancehunt_rss(payload)


class TestInstantDiscoveryPipeline(unittest.IsolatedAsyncioTestCase):
    async def _pipeline(
        self,
        xml: str,
        repository: InMemoryGmailRepository,
        checker: StaticChecker,
        *,
        openai_client: object | None = None,
        max_new: int = 10,
    ) -> FreelancehuntDiscoveryPipeline:
        return FreelancehuntDiscoveryPipeline(
            repository=repository,
            bot=MagicMock(),
            chat_id=123,
            feed_client=FreelancehuntFeedClient(
                fetcher=AsyncMock(return_value=xml)
            ),
            openai_client=openai_client,
            live_status_checker=checker,
            max_new_projects_per_scan=max_new,
        )

    async def test_new_active_project_sends_one_card_with_under_120s_latency(self):
        published = datetime.now(timezone.utc) - timedelta(seconds=30)
        xml = _rss(_rss_item(1700010, "AI website task", published_at=published))
        repository = InMemoryGmailRepository()
        checker = StaticChecker(LiveStatus.ACTIVE_BIDDABLE)
        pipeline = await self._pipeline(xml, repository, checker)
        send = AsyncMock(return_value=True)

        with (
            patch(
                "gmail_agent.processor.analyze_candidate",
                AsyncMock(side_effect=lambda item, **_: _candidate_analysis(item)),
            ),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            stats = await pipeline.run()

        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.ai_analyzed, 1)
        self.assertEqual(stats.live_status_active, 1)
        self.assertEqual(stats.qualified, 1)
        self.assertEqual(send.await_count, 1)
        sent_analysis = send.await_args.args[2]
        self.assertEqual(sent_analysis.live_status, LiveStatus.ACTIVE_BIDDABLE.value)
        self.assertTrue(sent_analysis.biddable)
        self.assertLess(sent_analysis.publication_to_telegram_latency_seconds, 120)
        key = freelancehunt_project_stable_key(project_id="1700010")
        stored = await repository.get_job(key)
        self.assertEqual(stored.status, "sent")
        self.assertLess(stored.publication_to_telegram_latency_seconds, 120)
        runs = await repository.list_scan_runs()
        self.assertLess(runs[0].max_publication_to_telegram_latency_seconds, 120)

    async def test_repeat_and_restart_dedup_avoid_ai_and_second_card(self):
        state: dict[str, object] = {}
        xml = _rss(_rss_item(1700011, "CRM cleanup"))
        analyze = AsyncMock(side_effect=lambda item, **_: _candidate_analysis(item))
        send = AsyncMock(return_value=True)
        first_repository = InMemoryGmailRepository(state)
        first = await self._pipeline(
            xml, first_repository, StaticChecker(LiveStatus.ACTIVE_BIDDABLE)
        )
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            first_stats = await first.run()
            repeat_stats = await first.run()
            restarted = await self._pipeline(
                xml,
                InMemoryGmailRepository(state),
                StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
            )
            restart_stats = await restarted.run()

        self.assertEqual(first_stats.sent, 1)
        self.assertEqual(repeat_stats.duplicates_skipped, 1)
        self.assertEqual(restart_stats.duplicates_skipped, 1)
        self.assertEqual(analyze.await_count, 1)
        self.assertEqual(send.await_count, 1)

    async def test_rss_then_gmail_uses_one_project_identity(self):
        project_id = 1700012
        repository = InMemoryGmailRepository()
        rss_pipeline = await self._pipeline(
            _rss(_rss_item(project_id, "Video editing")),
            repository,
            StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
        )
        candidate_analyze = AsyncMock(
            side_effect=lambda item, **_: _candidate_analysis(item, lane="video")
        )
        send = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_candidate", candidate_analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            await rss_pipeline.run()

        gmail_analyze = AsyncMock()
        gmail_processor = GmailJobProcessor(
            provider=MockGmailProvider([_single_email(project_id)]),
            bot=MagicMock(),
            chat_id=123,
            repository=repository,
            live_status_checker=StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
        )
        with (
            patch("gmail_agent.processor.analyze_email", gmail_analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            stats = await gmail_processor.run()

        self.assertEqual(stats.duplicates_skipped, 1)
        self.assertEqual(stats.duplicate_source_pairs, {"rss->gmail": 1})
        gmail_analyze.assert_not_awaited()
        self.assertEqual(send.await_count, 1)
        stored = await repository.get_job(
            freelancehunt_project_stable_key(project_id=str(project_id))
        )
        self.assertEqual(stored.discovery_sources, "rss,gmail")

    async def test_gmail_then_rss_uses_one_project_identity(self):
        project_id = 1700013
        repository = InMemoryGmailRepository()
        email = _single_email(project_id)
        key = freelancehunt_project_stable_key(project_id=str(project_id))
        single_analysis = JobAnalysis(
            email_id=key,
            is_relevant=True,
            title=email.subject,
            platform="Freelancehunt",
            score=8,
            reason="Synthetic assessment.",
            budget="100 UAH",
            url=email.links[0],
            urgency="medium",
            why_relevant="Executable.",
            language="en",
            description_completeness="FULL",
            executable="yes",
            service_lane="content",
            fit_score=8,
            estimated_effort="1 day",
            delivery_risk="Source access must be confirmed.",
            client_payment_risk="Not enough data; use a funded milestone.",
            project_mode="CASH",
            project_mode_reason="Bounded paid task.",
            recommended_price="100 UAH",
            realistic_timeline="1 day",
            evidence_case_id="NO_DIRECT_CASE",
            proposal_draft="We can deliver the synthetic content editing task.",
            next_action="Review the proposal manually.",
            analysis_version=ANALYSIS_VERSION,
        )
        send = AsyncMock(return_value=True)
        processor = GmailJobProcessor(
            provider=MockGmailProvider([email]),
            bot=MagicMock(),
            chat_id=123,
            repository=repository,
            live_status_checker=StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
        )
        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=single_analysis)),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            gmail_stats = await processor.run()

        pipeline = await self._pipeline(
            _rss(_rss_item(project_id, "Content editing")),
            repository,
            StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
        )
        candidate_analyze = AsyncMock()
        with (
            patch("gmail_agent.processor.analyze_candidate", candidate_analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            rss_stats = await pipeline.run()

        self.assertEqual(gmail_stats.sent, 1)
        self.assertEqual(rss_stats.duplicates_skipped, 1)
        self.assertEqual(rss_stats.duplicate_source_pairs, {"gmail->rss": 1})
        candidate_analyze.assert_not_awaited()
        self.assertEqual(send.await_count, 1)

    async def test_legacy_parser_then_rss_uses_one_project_identity(self):
        project_id = 1700014
        url = (
            f"https://freelancehunt.com/project/legacy-project/{project_id}.html"
        )
        state: dict[str, object] = {
            "legacy_orders": [
                {
                    "id": 77,
                    "platform": "Freelancehunt",
                    "title": "Legacy parser project",
                    "url": url,
                    "status": "notified",
                    "score": 8.0,
                }
            ]
        }
        repository = InMemoryGmailRepository(state)
        pipeline = await self._pipeline(
            _rss(_rss_item(project_id, "Legacy parser project")),
            repository,
            StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
        )
        analyze = AsyncMock()
        send = AsyncMock()
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            first = await pipeline.run()
            restarted = await self._pipeline(
                _rss(_rss_item(project_id, "Legacy parser project")),
                InMemoryGmailRepository(state),
                StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
            )
            repeat = await restarted.run()

        self.assertEqual(first.duplicates_skipped, 1)
        self.assertEqual(first.duplicate_source_pairs, {"parser->rss": 1})
        self.assertEqual(repeat.duplicates_skipped, 1)
        analyze.assert_not_awaited()
        send.assert_not_awaited()
        processed = await repository.get_processed(
            freelancehunt_project_stable_key(project_id=str(project_id))
        )
        self.assertEqual(processed.item_type, "legacy_parser")

    async def test_non_active_statuses_never_reach_ai_price_or_proposal(self):
        statuses = (
            LiveStatus.BLOCKED_RULE_VIOLATION,
            LiveStatus.CLOSED,
            LiveStatus.EXECUTOR_SELECTED,
            LiveStatus.DELETED_OR_UNAVAILABLE,
        )
        for index, status in enumerate(statuses, start=1):
            with self.subTest(status=status):
                repository = InMemoryGmailRepository()
                pipeline = await self._pipeline(
                    _rss(_rss_item(1700020 + index, f"Terminal {status.value}")),
                    repository,
                    StaticChecker(status),
                )
                analyze = AsyncMock()
                proposal_card = AsyncMock()
                diagnostic = AsyncMock(return_value=True)
                with (
                    patch("gmail_agent.processor.analyze_candidate", analyze),
                    patch("gmail_agent.processor.send_job_card", proposal_card),
                    patch("gmail_agent.processor.send_live_status_card", diagnostic),
                ):
                    stats = await pipeline.run()
                analyze.assert_not_awaited()
                proposal_card.assert_not_awaited()
                self.assertEqual(diagnostic.await_count, 1)
                self.assertEqual(stats.live_status_non_actionable, 1)
                job = next(iter(repository._state["jobs"].values()))
                self.assertFalse(job.biddable)
                self.assertEqual(job.recommended_price, "")
                self.assertEqual(job.proposal_draft, "")

    async def test_unknown_status_stays_retryable_without_ai_or_proposal(self):
        repository = InMemoryGmailRepository()
        pipeline = await self._pipeline(
            _rss(_rss_item(1700030, "Ambiguous public status")),
            repository,
            StaticChecker(LiveStatus.LIVE_STATUS_UNKNOWN),
        )
        analyze = AsyncMock()
        proposal_card = AsyncMock()
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_job_card", proposal_card),
            patch(
                "gmail_agent.processor.send_live_status_card",
                AsyncMock(return_value=True),
            ),
        ):
            stats = await pipeline.run()
        analyze.assert_not_awaited()
        proposal_card.assert_not_awaited()
        self.assertEqual(stats.live_status_unknown, 1)
        key = freelancehunt_project_stable_key(project_id="1700030")
        job = await repository.get_job(key)
        self.assertEqual(job.status, "live_status_pending")
        self.assertFalse(await repository.is_processed(key))

    async def test_active_label_without_biddable_true_fails_closed(self):
        class InconsistentChecker:
            async def check(self, _url: str) -> LiveStatusResult:
                return LiveStatusResult(
                    status=LiveStatus.ACTIVE_BIDDABLE,
                    checked_at=datetime.now(timezone.utc),
                    evidence="synthetic inconsistent result",
                    biddable=False,
                )

        repository = InMemoryGmailRepository()
        pipeline = await self._pipeline(
            _rss(_rss_item(1700031, "Inconsistent active state")),
            repository,
            InconsistentChecker(),
        )
        analyze = AsyncMock()
        proposal_card = AsyncMock()
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_job_card", proposal_card),
            patch(
                "gmail_agent.processor.send_live_status_card",
                AsyncMock(return_value=True),
            ),
        ):
            stats = await pipeline.run()
        analyze.assert_not_awaited()
        proposal_card.assert_not_awaited()
        self.assertEqual(stats.live_status_unknown, 1)
        job = await repository.get_job(
            freelancehunt_project_stable_key(project_id="1700031")
        )
        self.assertEqual(job.live_status, LiveStatus.LIVE_STATUS_UNKNOWN.value)
        self.assertFalse(job.biddable)

    async def test_broad_online_lanes_and_tiny_budgets_are_analyzed(self):
        titles = (
            "Website landing page",
            "AI bot and CRM",
            "SEO audit",
            "Content plan and SMM",
            "Image generation",
            "Video montage",
            "Audio voice cleanup",
            "Research and lead generation",
        )
        items = [
            _rss_item(
                1700100 + index,
                title,
                description=f"{title}. Fixed budget 10 UAH.",
                category=title,
            )
            for index, title in enumerate(titles)
        ]
        repository = InMemoryGmailRepository()
        pipeline = await self._pipeline(
            _rss(*items), repository, StaticChecker(LiveStatus.ACTIVE_BIDDABLE)
        )
        analyze = AsyncMock(
            side_effect=lambda item, **_: _candidate_analysis(
                item,
                score=0.1,
                lane=item.title.casefold().replace(" ", "_"),
            )
        )
        send = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            stats = await pipeline.run()

        self.assertEqual(stats.candidates_found, len(titles))
        self.assertEqual(stats.ai_analyzed, len(titles))
        self.assertEqual(stats.sent, len(titles))
        self.assertEqual(stats.below_threshold, 0)
        modes = {job.project_mode for job in repository._state["jobs"].values()}
        self.assertEqual(modes, {"CASH"})
        self.assertTrue(
            all(job.executable == "yes" for job in repository._state["jobs"].values())
        )
        self.assertTrue(
            all(job.delivery_risk for job in repository._state["jobs"].values())
        )

    async def test_executable_no_clears_offer_and_is_terminally_rejected(self):
        xml = _rss(_rss_item(1700200, "Unsupported synthetic task"))
        batch = parse_freelancehunt_rss(xml)
        client = _mock_openai_client(
            {
                "is_relevant": True,
                "title": "Unsupported synthetic task",
                "platform": "Freelancehunt",
                "fit_score": 8,
                "reason": "Cannot be truthfully delivered.",
                "budget": "1000 UAH",
                "url": batch.candidates[0].url,
                "urgency": "medium",
                "why_relevant": "Not executable.",
                "executable": "no",
                "service_lane": "unsupported",
                "recommended_price": "1000 UAH",
                "realistic_timeline": "1 day",
                "proposal_draft": "This must never be sent.",
                "project_mode": "STRATEGIC",
            }
        )
        analysis = await analyze_candidate(batch.candidates[0], client=client)
        self.assertFalse(analysis.is_relevant)
        self.assertEqual(analysis.executable, "no")
        self.assertEqual(analysis.recommended_price, "")
        self.assertEqual(analysis.proposal_draft, "")

        repository = InMemoryGmailRepository()
        pipeline = await self._pipeline(
            xml,
            repository,
            StaticChecker(LiveStatus.ACTIVE_BIDDABLE),
            openai_client=client,
        )
        send = AsyncMock()
        with patch("gmail_agent.processor.send_job_card", send):
            stats = await pipeline.run()
        self.assertEqual(stats.not_relevant, 1)
        self.assertEqual(stats.sent, 0)
        send.assert_not_awaited()
        processed = await repository.get_processed(batch.candidates[0].stable_key)
        self.assertEqual(processed.decision, "quality_non_executable")

    async def test_malformed_feed_records_failed_scan_without_project_actions(self):
        repository = InMemoryGmailRepository()
        pipeline = await self._pipeline(
            "<rss>", repository, StaticChecker(LiveStatus.ACTIVE_BIDDABLE)
        )
        stats = await pipeline.run()
        self.assertEqual(stats.errors, 1)
        self.assertEqual(stats.parser_failures, 1)
        self.assertEqual(repository._state["jobs"], {})
        runs = await repository.list_scan_runs()
        self.assertEqual(runs[0].errors, 1)


class TestStage3ConfigurationAndCompatibility(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_parser_emits_same_identity_and_bypasses_old_keywords(self):
        project_id = "1700300"
        url = f"https://freelancehunt.com/project/audio-task/{project_id}.html"
        project = {
            "platform": "Freelancehunt",
            "title": "Озвучка та монтаж відео",
            "description": "Контент-план, SMM і SEO-текст.",
            "url": url,
        }
        parser = FreelancehuntParser()
        with patch.object(parser, "_try_json_api", AsyncMock(return_value=[project])):
            projects = await parser.get_new_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["project_id"], project_id)
        self.assertEqual(
            projects[0]["stable_key"],
            freelancehunt_project_stable_key(project_id=project_id),
        )
        self.assertEqual(projects[0]["discovery_source"], "legacy_parser")

        base = BasePlatformParser()
        self.assertTrue(base._matches_filter(project))
        matched, reason = base._matches_filter_verbose(project)
        self.assertTrue(matched)
        self.assertIn("BROAD_CAPABILITY", reason)

    async def test_scheduler_is_exactly_60_seconds_single_instance_coalesced(self):
        scheduler = MagicMock()
        bot = MagicMock()
        register_freelancehunt_discovery_job(scheduler, bot, interval_seconds=1)
        kwargs = scheduler.add_job.call_args.kwargs
        self.assertEqual(kwargs["seconds"], 60)
        self.assertEqual(kwargs["max_instances"], 1)
        self.assertTrue(kwargs["coalesce"])
        self.assertEqual(kwargs["id"], "check_freelancehunt_projects")

    async def test_standard_card_is_one_html_safe_bounded_message(self):
        candidate = parse_freelancehunt_rss(
            _rss(_rss_item(1700400, "SEO <script>alert(1)</script>"))
        ).candidates[0]
        analysis = _candidate_analysis(candidate, lane="seo_content")
        analysis.title = "SEO <script>alert(1)</script>"
        analysis.full_description = "Use <b>unsafe source markup</b> & research."
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        parts = format_job_card_parts(analysis)
        self.assertEqual(len(parts), 1)
        self.assertLessEqual(len(parts[0]), TELEGRAM_TEXT_LIMIT)
        self.assertNotIn("<script>", parts[0])
        self.assertIn("&lt;script&gt;", parts[0])
        self.assertIn("CASH", parts[0])

        analysis.full_description = "<unsafe>" + ("x" * 20_000)
        long_parts = format_job_card_parts(analysis)
        self.assertGreater(len(long_parts), 1)
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in long_parts))

    async def test_hourly_parser_excludes_freelancehunt_and_preserves_others(self):
        source = (PROJECT_ROOT / "scheduler.py").read_text(encoding="utf-8")
        parser_block = source[source.index("_PARSERS = [") : source.index("_DEBUG_PARSERS")]
        self.assertNotIn("_fh_projects", parser_block)
        self.assertIn("_kb_projects", parser_block)
        self.assertIn("_flua_projects", parser_block)

    async def test_stage3_migrations_are_additive(self):
        source = (PROJECT_ROOT / "db" / "models.py").read_text(encoding="utf-8")
        required = (
            "discovery_source",
            "discovery_sources",
            "source_publication_at",
            "source_feed_timestamp",
            "feed_fetched_at",
            "first_seen_at",
            "telegram_sent_at",
            "publication_to_telegram_latency_seconds",
            "duplicate_source_pairs",
            "ai_calls_avoided",
        )
        migrations = source[source.index("_MIGRATIONS = [") :]
        for column in required:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", migrations)
        upper = migrations.upper()
        self.assertNotIn("DROP TABLE", upper)
        self.assertNotIn("TRUNCATE", upper)
        self.assertNotIn("DELETE FROM", upper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
