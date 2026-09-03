"""Deterministic contracts for the Freelancehunt live bid-status guard."""

from __future__ import annotations

import tempfile
import time
import unittest
import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.dedup import EmailDedup
from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.live_status import (
    FreelancehuntLiveStatusChecker,
    LiveStatus,
    LiveStatusResult,
    active_status_is_fresh,
    classify_live_html,
    ensure_current_biddable_status,
    retry_due,
)
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.quality_gate import ANALYSIS_VERSION
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import format_job_card, format_live_status_card
from gmail_agent.tests.digest_fixtures import DIGEST_ONE_JOB_HTML


NOW = datetime.now(timezone.utc)
PROJECT_URL = "https://freelancehunt.com/project/sanitized/1650987.html"
FIXTURES = Path(__file__).parent / "fixtures"


def _result(status: LiveStatus, evidence: str = "fixture evidence") -> LiveStatusResult:
    return LiveStatusResult(
        status=status,
        checked_at=NOW,
        evidence=evidence,
        biddable=status == LiveStatus.ACTIVE_BIDDABLE,
        last_error="temporary network failure" if status == LiveStatus.LIVE_STATUS_UNKNOWN else "",
    )


class SequenceChecker:
    def __init__(self, *results: LiveStatusResult):
        self.results = list(results)
        self.calls: list[str] = []

    async def check(self, url: str) -> LiveStatusResult:
        self.calls.append(url)
        return self.results.pop(0)


def _single_project() -> EmailMessage:
    return EmailMessage(
        id="single-1650987",
        subject="Новий проєкт: sanitized fixture",
        sender="alerts@freelancehunt.com",
        body="Sanitized project description.",
        text_body="Sanitized project description.",
        html_body=f'<a href="{PROJECT_URL}">Project</a>',
        links=[PROJECT_URL],
        received_at=NOW,
    )


def _digest_project() -> EmailMessage:
    return EmailMessage(
        id="digest-live-status",
        subject="Підбірка вакансій «Synthetic»",
        sender="digest@freelancehunt.com",
        body="Synthetic digest fallback.",
        text_body="",
        html_body=DIGEST_ONE_JOB_HTML,
        received_at=NOW,
    )


def _active_analysis() -> JobAnalysis:
    return JobAnalysis(
        email_id="single-1650987",
        is_relevant=True,
        title="Sanitized active project",
        platform="Freelancehunt",
        score=8.0,
        reason="Good fit",
        budget="1000 UAH",
        url=PROJECT_URL,
        urgency="medium",
        why_relevant="Python automation",
        full_description="Sanitized active Python automation project.",
        description_completeness="FULL",
        language="en",
        service_lane="automation",
        executable="yes",
        fit_score=7.5,
        estimated_effort="2 days",
        delivery_risk="API access must be confirmed.",
        client_payment_risk="Not enough data; use a funded milestone.",
        project_mode="CASH",
        project_mode_reason="Bounded paid automation.",
        evidence_case_id="NO_DIRECT_CASE",
        proposal_draft="We can deliver this sanitized Python automation project.",
        recommended_price="1000 UAH",
        realistic_timeline="2 days",
        next_action="Review the proposal manually.",
        analysis_version=ANALYSIS_VERSION,
    )


class TestMultilingualLiveStatusClassification(unittest.TestCase):
    def test_ukrainian_blocked_banner(self):
        result = classify_live_html(
            "<div>Проект заблокований фрилансерами за порушення правил сервісу.</div>"
        )
        self.assertEqual(result.status, LiveStatus.BLOCKED_RULE_VIOLATION)
        self.assertFalse(result.biddable)

    def test_russian_blocked_banner(self):
        result = classify_live_html(
            "<div>Проект заблокирован фрилансерами за нарушение правил сервиса.</div>"
        )
        self.assertEqual(result.status, LiveStatus.BLOCKED_RULE_VIOLATION)

    def test_english_blocked_and_closed_statuses(self):
        blocked = classify_live_html(
            "<p>Project has been blocked for violating the service rules.</p>"
        )
        closed = classify_live_html("<p>Bidding is closed.</p>")
        self.assertEqual(blocked.status, LiveStatus.BLOCKED_RULE_VIOLATION)
        self.assertEqual(closed.status, LiveStatus.CLOSED)

    def test_polish_blocked_and_closed_statuses(self):
        blocked = classify_live_html(
            "<p>Projekt został zablokowany za naruszenie zasad serwisu.</p>"
        )
        closed = classify_live_html("<p>Projekt zakończony.</p>")
        self.assertEqual(blocked.status, LiveStatus.BLOCKED_RULE_VIOLATION)
        self.assertEqual(closed.status, LiveStatus.CLOSED)

    def test_active_page_requires_enabled_bid_form(self):
        html = (FIXTURES / "freelancehunt_active.html").read_text(encoding="utf-8")
        result = classify_live_html(html, checked_at=NOW)
        self.assertEqual(result.status, LiveStatus.ACTIVE_BIDDABLE)
        self.assertTrue(result.biddable)

    def test_absence_of_negative_banner_or_disabled_cta_is_not_active_proof(self):
        plain = classify_live_html("<main><h1>Project description</h1></main>")
        disabled = classify_live_html(
            '<button disabled aria-disabled="true">Submit a bid</button>'
        )
        disabled_inside_form = classify_live_html(
            '<form action="/profile"><button disabled>Submit a bid</button></form>'
        )
        hidden = classify_live_html(
            '<div hidden><a href="/bid">Submit a bid</a></div>'
        )
        for result in (plain, disabled, disabled_inside_form, hidden):
            self.assertEqual(result.status, LiveStatus.LIVE_STATUS_UNKNOWN)
            self.assertFalse(result.biddable)

    def test_executor_selected(self):
        result = classify_live_html("<div>Виконавця обрано</div>")
        self.assertEqual(result.status, LiveStatus.EXECUTOR_SELECTED)

    def test_fixture_1650987_is_blocked(self):
        html = (FIXTURES / "freelancehunt_1650987_blocked.html").read_text(
            encoding="utf-8"
        )
        result = classify_live_html(html, checked_at=NOW)
        self.assertEqual(result.status, LiveStatus.BLOCKED_RULE_VIOLATION)
        self.assertEqual(result.evidence, "проект заблокований фрилансерами за порушення правил сервісу")


class TestHttpAndBrowserFallback(unittest.IsolatedAsyncioTestCase):
    async def test_deleted_404(self):
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(return_value=SimpleNamespace(status_code=404, html="")),
            playwright_fetcher=AsyncMock(),
        )
        result = await checker.check(PROJECT_URL)
        self.assertEqual(result.status, LiveStatus.DELETED_OR_UNAVAILABLE)
        checker._playwright_fetcher.assert_not_awaited()

    async def test_transient_http_and_browser_failure_is_unknown(self):
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(side_effect=TimeoutError("synthetic timeout")),
            playwright_fetcher=AsyncMock(side_effect=RuntimeError("synthetic browser failure")),
        )
        result = await checker.check(PROJECT_URL)
        self.assertEqual(result.status, LiveStatus.LIVE_STATUS_UNKNOWN)
        self.assertFalse(result.biddable)
        self.assertIn("HTTP TimeoutError", result.last_error)

    async def test_playwright_fallback_classifies_active_page(self):
        html = (FIXTURES / "freelancehunt_active.html").read_text(encoding="utf-8")
        browser_fetch = AsyncMock(return_value=SimpleNamespace(status_code=200, html=html))
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(return_value=SimpleNamespace(status_code=403, html="challenge")),
            playwright_fetcher=browser_fetch,
        )
        result = await checker.check(PROJECT_URL)
        self.assertEqual(result.status, LiveStatus.ACTIVE_BIDDABLE)
        browser_fetch.assert_awaited_once_with(PROJECT_URL)

    async def test_official_open_project_rss_is_positive_active_evidence(self):
        browser_fetch = AsyncMock()
        rss_fetch = AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                html=f"<rss><channel><item><link>{PROJECT_URL}</link></item></channel></rss>",
            )
        )
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(
                return_value=SimpleNamespace(status_code=403, html="challenge")
            ),
            playwright_fetcher=browser_fetch,
            rss_fetcher=rss_fetch,
        )
        result = await checker.check(PROJECT_URL)
        self.assertEqual(result.status, LiveStatus.ACTIVE_BIDDABLE)
        self.assertTrue(result.biddable)
        self.assertIn("official current open-project RSS", result.evidence)
        rss_fetch.assert_awaited_once()
        browser_fetch.assert_not_awaited()

    async def test_rss_absence_is_not_terminal_and_browser_still_runs(self):
        browser_fetch = AsyncMock(
            return_value=SimpleNamespace(status_code=403, html="challenge")
        )
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(
                return_value=SimpleNamespace(status_code=403, html="challenge")
            ),
            playwright_fetcher=browser_fetch,
            rss_fetcher=AsyncMock(
                return_value=SimpleNamespace(
                    status_code=200,
                    html="<rss><channel></channel></rss>",
                )
            ),
        )
        result = await checker.check(PROJECT_URL)
        self.assertEqual(result.status, LiveStatus.LIVE_STATUS_UNKNOWN)
        self.assertIn("absent from official current open-project RSS", result.last_error)
        browser_fetch.assert_awaited_once_with(PROJECT_URL)


class TestV2ActionFreshnessGuard(unittest.IsolatedAsyncioTestCase):
    def _record(self, **changes):
        record = {
            "platform": "Freelancehunt",
            "url": PROJECT_URL,
            "live_status": LiveStatus.ACTIVE_BIDDABLE.value,
            "live_status_checked_at": datetime.now(timezone.utc),
            "live_status_evidence": "submit a bid",
            "live_status_last_error": "",
            "biddable": True,
            "qualified": True,
            "proposal_draft": "Historical proposal must be retained.",
        }
        record.update(changes)
        return record

    async def _guard(self, record, result, *, force=False):
        checker = SequenceChecker(result)

        async def persist(value):
            record.update(
                live_status=value.status.value,
                live_status_checked_at=value.checked_at,
                live_status_evidence=value.evidence,
                live_status_last_error=value.last_error,
                biddable=value.biddable,
                qualified=record["qualified"] if value.biddable else False,
            )

        guard = await ensure_current_biddable_status(
            record, checker, persist, force=force
        )
        return guard, checker

    async def test_fresh_active_uses_no_extra_request(self):
        record = self._record()
        checker = SequenceChecker(_result(LiveStatus.CLOSED))
        persist = AsyncMock()
        guard = await ensure_current_biddable_status(record, checker, persist)
        self.assertTrue(active_status_is_fresh(record))
        self.assertTrue(guard.allowed)
        self.assertEqual(checker.calls, [])
        persist.assert_not_awaited()

    async def test_active_to_blocked_before_view_is_hidden(self):
        record = self._record(
            live_status_checked_at=datetime.now(timezone.utc) - timedelta(seconds=61)
        )
        guard, checker = await self._guard(
            record, _result(LiveStatus.BLOCKED_RULE_VIOLATION)
        )
        self.assertFalse(guard.allowed)
        self.assertEqual(len(checker.calls), 1)
        self.assertFalse(record["qualified"])
        self.assertEqual(record["proposal_draft"], "Historical proposal must be retained.")

    async def test_active_to_closed_before_manual_send_is_hidden(self):
        record = self._record(live_status_checked_at=None)
        guard, _ = await self._guard(record, _result(LiveStatus.CLOSED))
        self.assertFalse(guard.allowed)
        self.assertEqual(record["live_status"], LiveStatus.CLOSED.value)

    async def test_gmail_active_to_executor_selected_before_rewrite(self):
        record = self._record(event_type="PROJECT_SINGLE", live_status_checked_at=None)
        guard, _ = await self._guard(record, _result(LiveStatus.EXECUTOR_SELECTED))
        self.assertFalse(guard.allowed)
        self.assertEqual(record["live_status"], LiveStatus.EXECUTOR_SELECTED.value)

    async def test_gmail_active_to_unknown_before_saved_proposal(self):
        record = self._record(event_type="PROJECT_DIGEST", live_status_checked_at=None)
        guard, _ = await self._guard(record, _result(LiveStatus.LIVE_STATUS_UNKNOWN))
        self.assertFalse(guard.allowed)
        self.assertFalse(record["biddable"])
        self.assertIn("Historical proposal", record["proposal_draft"])

    async def test_manual_recheck_unknown_to_active_and_blocked(self):
        for status, allowed in (
            (LiveStatus.ACTIVE_BIDDABLE, True),
            (LiveStatus.BLOCKED_RULE_VIOLATION, False),
        ):
            record = self._record(
                live_status=LiveStatus.LIVE_STATUS_UNKNOWN.value,
                live_status_checked_at=NOW,
                biddable=False,
                qualified=False,
            )
            guard, checker = await self._guard(record, _result(status), force=True)
            self.assertEqual(guard.allowed, allowed)
            self.assertEqual(len(checker.calls), 1)


class TestV2BoundedBatchChecker(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _urls(count):
        return [
            f"https://freelancehunt.com/project/sanitized-{index}/{1000 + index}.html"
            for index in range(count)
        ]

    async def test_four_protected_urls_are_concurrent_not_four_long_serial_checks(self):
        active_html = (FIXTURES / "freelancehunt_active.html").read_text(encoding="utf-8")
        active = 0
        peak = 0

        async def http_fetch(url):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await __import__("asyncio").sleep(0.2)
            active -= 1
            return SimpleNamespace(status_code=403, html="challenge")

        async def browser_fetch(url):
            await __import__("asyncio").sleep(0.2)
            return SimpleNamespace(status_code=200, html=active_html)

        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=http_fetch,
            playwright_fetcher=browser_fetch,
            max_concurrency=4,
            cache_ttl_seconds=0,
        )
        started = time.monotonic()
        results = await checker.batch_check(self._urls(4))
        elapsed = time.monotonic() - started
        # A serial implementation would need at least 1.6s (4 x 0.4s).
        self.assertLess(elapsed, 1.0)
        self.assertGreaterEqual(peak, 3)
        self.assertLessEqual(peak, 4)
        self.assertTrue(all(item.biddable for item in results.values()))

    async def test_same_url_twice_is_fetched_once_per_scan(self):
        fetch = AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                html=(FIXTURES / "freelancehunt_active.html").read_text(encoding="utf-8"),
            )
        )
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=fetch, playwright_fetcher=AsyncMock(), cache_ttl_seconds=0
        )
        await checker.batch_check([PROJECT_URL, PROJECT_URL])
        self.assertEqual(fetch.await_count, 1)

    async def test_batch_fetches_official_rss_once_for_all_urls(self):
        urls = self._urls(10)
        rss_fetch = AsyncMock(
            return_value=SimpleNamespace(
                status_code=200,
                html="<rss><channel>"
                + "".join(f"<item><link>{url}</link></item>" for url in urls)
                + "</channel></rss>",
            )
        )
        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=AsyncMock(
                return_value=SimpleNamespace(status_code=403, html="challenge")
            ),
            playwright_fetcher=AsyncMock(),
            rss_fetcher=rss_fetch,
            cache_ttl_seconds=0,
        )
        results = await checker.batch_check(urls)
        self.assertTrue(all(result.biddable for result in results.values()))
        rss_fetch.assert_awaited_once()
        checker._playwright_fetcher.assert_not_awaited()

    async def test_overall_deadline_returns_unknown_and_scheduler_can_continue(self):
        async def slow(url):
            await __import__("asyncio").sleep(0.2)
            return SimpleNamespace(status_code=200, html="")

        checker = FreelancehuntLiveStatusChecker(
            http_fetcher=slow,
            playwright_fetcher=slow,
            scan_budget_seconds=0.05,
            cache_ttl_seconds=0,
        )
        results = await checker.batch_check(self._urls(10))
        self.assertEqual(len(results), 10)
        self.assertTrue(
            all(item.status == LiveStatus.LIVE_STATUS_UNKNOWN for item in results.values())
        )

    async def test_resources_close_after_scan(self):
        checker = FreelancehuntLiveStatusChecker()
        context = MagicMock()
        context.close = AsyncMock()
        browser = MagicMock()
        browser.close = AsyncMock()
        playwright = MagicMock()
        playwright.stop = AsyncMock()
        client = MagicMock()
        client.aclose = AsyncMock()
        checker._browser_context = context
        checker._browser = browser
        checker._playwright = playwright
        checker._http_client = client
        await checker._close_resources()
        context.close.assert_awaited_once()
        browser.close.assert_awaited_once()
        playwright.stop.assert_awaited_once()
        client.aclose.assert_awaited_once()


class TestGmailLiveStatusGate(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repository_state: dict[str, object] = {}
        self.repository = InMemoryGmailRepository(self.repository_state)
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()

    def _processor(self, checker, repository=None):
        return GmailJobProcessor(
            provider=MockGmailProvider([_single_project()]),
            bot=self.bot,
            chat_id=123,
            min_score=6,
            dedup=EmailDedup(Path(self.tempdir.name) / "dedup.json"),
            repository=repository or self.repository,
            live_status_checker=checker,
            live_status_retry_base_seconds=1,
        )

    async def test_non_actionable_never_calls_ai_or_creates_proposal(self):
        checker = SequenceChecker(_result(LiveStatus.BLOCKED_RULE_VIOLATION))
        analyze = AsyncMock(return_value=_active_analysis())
        with (
            patch("gmail_agent.processor.analyze_email", analyze),
            patch("gmail_agent.processor.send_live_status_card", AsyncMock(return_value=True)),
            patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as proposal_card,
        ):
            stats = await self._processor(checker).run()
        analyze.assert_not_awaited()
        proposal_card.assert_not_awaited()
        self.assertEqual(stats.qualified, 0)
        job = await self.repository.get_job("single-1650987")
        self.assertEqual(job.live_status, LiveStatus.BLOCKED_RULE_VIOLATION.value)
        self.assertFalse(job.biddable)
        self.assertFalse(job.qualified)
        self.assertEqual(job.proposal_draft, "")

    async def test_digest_children_use_guard_before_candidate_ai(self):
        checker = SequenceChecker(_result(LiveStatus.CLOSED, "project closed"))
        processor = GmailJobProcessor(
            provider=MockGmailProvider([_digest_project()]),
            bot=self.bot,
            chat_id=123,
            repository=self.repository,
            live_status_checker=checker,
            digest_enabled=True,
        )
        analyze = AsyncMock(return_value=_active_analysis())
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.send_live_status_card", AsyncMock(return_value=True)),
            patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as proposal_card,
        ):
            stats = await processor.run()
        analyze.assert_not_awaited()
        proposal_card.assert_not_awaited()
        self.assertEqual(stats.qualified, 0)
        self.assertEqual(stats.live_status_non_actionable, 1)
        jobs = self.repository_state["jobs"]
        stored = next(iter(jobs.values()))
        self.assertEqual(stored.live_status, LiveStatus.CLOSED.value)
        self.assertEqual(stored.status, "live_status_terminal")

    async def test_unknown_rechecks_with_backoff_then_becomes_active(self):
        checker = SequenceChecker(
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
            _result(LiveStatus.ACTIVE_BIDDABLE, "зробити ставку"),
        )
        analyze = AsyncMock(return_value=_active_analysis())
        send = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_email", analyze),
            patch("gmail_agent.processor.send_live_status_card", AsyncMock(return_value=True)),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            first = await self._processor(checker).run()
            pending = await self.repository.get_job("single-1650987")
            await self.repository.save_job(
                replace(pending, live_status_checked_at=datetime.now(timezone.utc) - timedelta(seconds=5))
            )
            second = await self._processor(checker).run()
        self.assertEqual(first.qualified, 0)
        self.assertEqual(second.qualified, 1)
        self.assertEqual(analyze.await_count, 1)
        self.assertEqual(send.await_count, 1)
        active = await self.repository.get_job("single-1650987")
        self.assertEqual(active.live_status, LiveStatus.ACTIVE_BIDDABLE.value)
        self.assertTrue(active.biddable)

    async def test_repeat_and_restart_deduplicate_blocked_diagnostic(self):
        checker = SequenceChecker(_result(LiveStatus.BLOCKED_RULE_VIOLATION))
        diagnostic = AsyncMock(return_value=True)
        analyze = AsyncMock(return_value=_active_analysis())
        with (
            patch("gmail_agent.processor.analyze_email", analyze),
            patch("gmail_agent.processor.send_live_status_card", diagnostic),
        ):
            await self._processor(checker).run()
            restarted = InMemoryGmailRepository(self.repository_state)
            repeat = await self._processor(checker, restarted).run()
        self.assertEqual(diagnostic.await_count, 1)
        self.assertEqual(repeat.duplicates_skipped, 1)
        analyze.assert_not_awaited()

    async def test_qualified_metrics_exclude_blocked_and_closed(self):
        for index, status in enumerate(
            (LiveStatus.BLOCKED_RULE_VIOLATION, LiveStatus.CLOSED), start=1
        ):
            email = _single_project()
            email.id = f"terminal-{index}"
            repository = InMemoryGmailRepository()
            processor = GmailJobProcessor(
                provider=MockGmailProvider([email]),
                bot=self.bot,
                chat_id=123,
                repository=repository,
                live_status_checker=SequenceChecker(_result(status)),
            )
            with (
                patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze,
                patch("gmail_agent.processor.send_live_status_card", AsyncMock(return_value=True)),
            ):
                stats = await processor.run()
            self.assertEqual(stats.qualified, 0)
            self.assertEqual(stats.relevant, 0)
            analyze.assert_not_awaited()

    async def test_single_unknown_three_times_exhausts_and_restart_makes_no_call(self):
        checker = SequenceChecker(
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
        )
        diagnostic = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze,
            patch("gmail_agent.processor.send_live_status_card", diagnostic),
        ):
            for attempt in range(3):
                await self._processor(checker).run()
                job = await self.repository.get_job("single-1650987")
                if attempt < 2:
                    await self.repository.update_job_fields(
                        job.stable_key,
                        {
                            "live_status_checked_at": datetime.now(timezone.utc)
                            - timedelta(seconds=5)
                        },
                    )
            restarted = InMemoryGmailRepository(self.repository_state)
            await self._processor(checker, restarted).run()

        exhausted = await self.repository.get_job("single-1650987")
        self.assertEqual(exhausted.live_status, LiveStatus.LIVE_STATUS_UNKNOWN.value)
        self.assertEqual(exhausted.status, "live_status_unknown_exhausted")
        self.assertFalse(exhausted.qualified)
        self.assertEqual(len(checker.calls), 3)
        self.assertTrue(await self.repository.is_processed("single-1650987"))
        self.assertEqual(diagnostic.await_count, 1)
        analyze.assert_not_awaited()

    async def test_digest_unknown_three_times_exhausts_child_and_finishes_parent(self):
        checker = SequenceChecker(
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
            _result(LiveStatus.LIVE_STATUS_UNKNOWN),
        )
        processor = GmailJobProcessor(
            provider=MockGmailProvider([_digest_project()]),
            bot=self.bot,
            chat_id=123,
            repository=self.repository,
            live_status_checker=checker,
            live_status_retry_base_seconds=1,
            digest_enabled=True,
        )
        diagnostic = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze,
            patch("gmail_agent.processor.send_live_status_card", diagnostic),
        ):
            for attempt in range(3):
                await processor.run()
                jobs = list(self.repository_state["jobs"].values())
                self.assertEqual(len(jobs), 1)
                if attempt < 2:
                    await self.repository.update_job_fields(
                        jobs[0].stable_key,
                        {
                            "live_status_checked_at": datetime.now(timezone.utc)
                            - timedelta(seconds=5)
                        },
                    )

        child = next(iter(self.repository_state["jobs"].values()))
        self.assertEqual(child.status, "live_status_unknown_exhausted")
        self.assertEqual(child.live_status, LiveStatus.LIVE_STATUS_UNKNOWN.value)
        self.assertTrue(await self.repository.is_processed(child.stable_key))
        self.assertTrue(await self.repository.is_processed("parent:digest-live-status"))
        self.assertEqual(len(checker.calls), 3)
        self.assertEqual(diagnostic.await_count, 1)
        analyze.assert_not_awaited()

    async def test_diagnostic_false_retries_then_success_is_deduplicated(self):
        checker = SequenceChecker(_result(LiveStatus.BLOCKED_RULE_VIOLATION))
        diagnostic = AsyncMock(side_effect=[False, True])
        with patch("gmail_agent.processor.send_live_status_card", diagnostic):
            await self._processor(checker).run()
            pending = await self.repository.get_job("single-1650987")
            self.assertEqual(pending.status, "live_status_notice_pending")
            await self._processor(checker).run()
            delivered = await self.repository.get_job("single-1650987")
            self.assertEqual(delivered.status, "live_status_terminal")
            await self._processor(checker).run()
        self.assertEqual(diagnostic.await_count, 2)
        notices = [
            item
            for key, item in self.repository_state["processed"].items()
            if key.startswith("live-status-notice:")
        ]
        self.assertEqual(len(notices), 1)

    def test_retry_is_limited_and_exponential(self):
        self.assertFalse(retry_due(NOW, 3, now=NOW + timedelta(days=1), max_retries=3))
        self.assertFalse(retry_due(NOW, 2, now=NOW + timedelta(seconds=119), base_seconds=60))
        self.assertTrue(retry_due(NOW, 2, now=NOW + timedelta(seconds=120), base_seconds=60))


class TestTelegramLiveStatusFormatting(unittest.TestCase):
    def test_active_card_has_verified_status_and_checked_time(self):
        analysis = _active_analysis()
        analysis.event_type = "PROJECT_SINGLE"
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = NOW
        analysis.biddable = True
        card = format_job_card(analysis)
        self.assertIn("Live status:</b> ACTIVE — bid available", card)
        self.assertIn(
            f"Checked:</b> {NOW.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            card,
        )
        self.assertIn("Готовий відгук", card)

    def test_blocked_card_has_no_price_or_proposal(self):
        analysis = _active_analysis()
        analysis.live_status = LiveStatus.BLOCKED_RULE_VIOLATION.value
        analysis.live_status_checked_at = NOW
        analysis.live_status_evidence = "safe blocked evidence"
        analysis.biddable = False
        card = format_live_status_card(analysis)
        self.assertIn("Bid available:</b> no", card)
        self.assertIn("BLOCKED_RULE_VIOLATION", card)
        self.assertNotIn("1000 UAH", card)
        self.assertNotIn("Sanitized proposal draft", card)


class TestDirectParserUsesSharedGuard(unittest.TestCase):
    def test_direct_parser_checks_shared_guard_before_scoring(self):
        project_root = Path(__file__).resolve().parents[2]
        scheduler_path = project_root / "scheduler.py"
        processor_path = project_root / "gmail_agent" / "processor.py"
        scheduler_source = scheduler_path.read_text(encoding="utf-8")
        processor_source = processor_path.read_text(encoding="utf-8")
        self.assertIn(
            "from gmail_agent.live_status import", scheduler_source
        )
        self.assertIn("FreelancehuntLiveStatusChecker", scheduler_source)
        self.assertIn("batch_check", scheduler_source)
        self.assertIn("from .live_status import", processor_source)

        tree = ast.parse(scheduler_source)
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "check_new_orders"
        )
        guard_lines = [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "check"
        ]
        score_lines = [
            node.lineno
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "score_order"
        ]
        self.assertTrue(guard_lines)
        self.assertTrue(score_lines)
        self.assertLess(min(guard_lines), min(score_lines))
        for field in (
            "live_status",
            "live_status_evidence",
            "biddable",
            "qualified",
        ):
            self.assertIn(f'"{field}"', scheduler_source)

    def test_all_direct_proposal_actions_fail_closed(self):
        project_root = Path(__file__).resolve().parents[2]
        handlers_source = (project_root / "bot" / "handlers.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(handlers_source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in ("cb_view_response", "cb_send_manual", "cb_rewrite", "cmd_reply"):
            calls = {
                node.func.id
                for node in ast.walk(functions[name])
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            }
            self.assertIn("_ensure_order_current_biddable", calls, name)

    def test_gmail_proposals_use_unified_service_and_manual_recheck_is_read_only(self):
        project_root = Path(__file__).resolve().parents[2]
        source = (project_root / "bot" / "handlers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        reply_calls = {
            node.func.id
            for node in ast.walk(functions["cmd_reply_job"])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("GmailJobProcessor", reply_calls)
        reply_source = ast.get_source_segment(source, functions["cmd_reply_job"]) or ""
        self.assertIn("deliver_validated_proposal_text_version", reply_source)
        self.assertIn("generate_validate_and_persist_proposal", reply_source)
        self.assertNotIn("generate_reply", reply_source)
        recheck = functions["cmd_recheck_live"]
        recheck_source = ast.get_source_segment(source, recheck) or ""
        self.assertIn("force=True", recheck_source)
        self.assertNotIn("generate_response", recheck_source)
        self.assertNotIn("generate_reply", recheck_source)


class TestAdditiveMigration(unittest.TestCase):
    def test_live_status_fields_are_additive_on_both_storage_paths(self):
        models_source = (
            Path(__file__).resolve().parents[2] / "db" / "models.py"
        ).read_text(encoding="utf-8")
        required = {
            "live_status",
            "live_status_checked_at",
            "live_status_evidence",
            "biddable",
            "live_status_retry_count",
            "live_status_last_error",
            "qualified",
        }
        sql = models_source.casefold()
        for table in ("gmail_jobs", "orders"):
            for column in required:
                self.assertIn(
                    f"alter table {table} add column if not exists {column}", sql
                )
