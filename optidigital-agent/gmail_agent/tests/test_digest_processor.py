"""Behavioral contracts for digest-aware Gmail processing.

All fixtures are synthetic.  The tests use only the in-memory repository and
mocked AI/Telegram boundaries; they never access Gmail, OpenAI, Telegram, or a
live database.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.dedup import EmailDedup
from gmail_agent.digest_parser import parse_freelancehunt_digest
from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.tests.digest_fixtures import (
    DIGEST_ONE_JOB_HTML,
    DIGEST_TWO_JOBS_HTML,
    digest_with_job_count,
)


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


class TrackingProvider(MockGmailProvider):
    """Mock provider that exposes parent-processing calls to assertions."""

    def __init__(self, emails: list[EmailMessage]):
        super().__init__(emails)
        self.marked: list[str] = []
        self.fetch_count = 0

    async def get_new_emails(self) -> list[EmailMessage]:
        self.fetch_count += 1
        return await super().get_new_emails()

    async def mark_as_processed(self, email_id: str) -> None:
        self.marked.append(email_id)


def _digest(email_id: str, html: str) -> EmailMessage:
    return EmailMessage(
        id=email_id,
        sender="Freelancehunt <digest@freelancehunt.com>",
        subject="Підбірка вакансій «Synthetic» за 19 липня",
        body="Synthetic digest fallback text",
        text_body="",
        html_body=html,
        received_at=NOW,
    )


def _single_job() -> EmailMessage:
    return EmailMessage(
        id="single-job-001",
        sender="alerts@freelancehunt.com",
        subject="Новий проєкт: Synthetic Telegram automation",
        body="Build one synthetic Telegram automation project.",
        text_body="Build one synthetic Telegram automation project.",
        received_at=NOW,
    )


def _single_job_with_id(index: int) -> EmailMessage:
    return EmailMessage(
        id=f"single-job-{index:03d}",
        sender="alerts@freelancehunt.com",
        subject=f"Новий проєкт: Synthetic single job {index:03d}",
        body=f"Build synthetic repository-backed job {index:03d}.",
        text_body=f"Build synthetic repository-backed job {index:03d}.",
        received_at=NOW,
    )


def _workua_information() -> EmailMessage:
    return EmailMessage(
        id="workua-info-001",
        sender="newsletter@work.ua",
        subject="Ринок праці: дослідження та поради кандидатам",
        body="Synthetic informational article, not a vacancy alert.",
        text_body="Статті та поради про ринок праці.",
        html_body='<a href="https://www.work.ua/articles/example">Article</a>',
        received_at=NOW,
    )


def _analysis(
    stable_key: str,
    *,
    title: str = "Synthetic job",
    url: str = "https://freelancehunt.com/ua/job/synthetic/1.html",
    score: float = 8.0,
    is_relevant: bool = True,
) -> JobAnalysis:
    return JobAnalysis(
        email_id=stable_key,
        is_relevant=is_relevant,
        title=title,
        platform="Freelancehunt",
        score=score,
        reason="Synthetic score reason",
        budget="1000 USD",
        url=url,
        urgency="medium",
        why_relevant="Synthetic automation match",
        red_flags=[],
    )


async def _candidate_analysis(candidate, *args, score: float = 8.0, **kwargs):
    return _analysis(
        candidate.stable_key,
        title=candidate.title,
        url=candidate.url,
        score=score,
    )


def _duplicate_count(stats) -> int:
    if hasattr(stats, "duplicates_skipped"):
        return stats.duplicates_skipped
    return stats.duplicates


class TestDigestAwareProcessor(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.dedup = EmailDedup(Path(self.tempdir.name) / "email-dedup.json")
        self.repository = InMemoryGmailRepository()
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()

    def _processor(
        self,
        emails: list[EmailMessage],
        *,
        max_cards_per_scan: int = 10,
    ) -> tuple[GmailJobProcessor, TrackingProvider]:
        provider = TrackingProvider(emails)
        processor = GmailJobProcessor(
            provider=provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=max_cards_per_scan,
            digest_enabled=True,
            job_store_path=Path(self.tempdir.name) / "jobs.json",
        )
        return processor, provider

    async def test_two_child_digest_is_analyzed_and_sent_as_two_jobs(self):
        email = _digest("digest-two", DIGEST_TWO_JOBS_HTML)
        candidates = parse_freelancehunt_digest(email)
        processor, _ = self._processor([email])
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        analyze_email = AsyncMock()
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.sent, 2)
        self.assertEqual(analyze_candidate.await_count, 2)
        analyze_email.assert_not_awaited()
        self.assertEqual(send_card.await_count, 2)
        self.assertFalse(
            (Path(self.tempdir.name) / "jobs.json").exists(),
            "repository-backed digest jobs must not be mirrored to legacy JSON",
        )
        analyzed_children = [call.args[0] for call in analyze_candidate.await_args_list]
        self.assertEqual(
            [item.stable_key for item in analyzed_children],
            [item.stable_key for item in candidates],
        )
        self.assertEqual(len({item.stable_key for item in analyzed_children}), 2)
        self.assertNotIn("digest-two", {item.stable_key for item in analyzed_children})
        for candidate in candidates:
            processed = await self.repository.get_processed(candidate.stable_key)
            self.assertIsNotNone(processed)
            self.assertEqual(processed.decision, "sent")

    async def test_same_normalized_url_from_two_digests_is_sent_once(self):
        first = _digest("digest-first", DIGEST_TWO_JOBS_HTML)
        second = _digest("digest-second", DIGEST_ONE_JOB_HTML)
        first_candidates = parse_freelancehunt_digest(first)
        second_candidates = parse_freelancehunt_digest(second)
        self.assertEqual(first_candidates[0].stable_key, second_candidates[0].stable_key)
        processor, _ = self._processor([first, second])
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.analyze_email", AsyncMock()),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.sent, 2)
        self.assertEqual(send_card.await_count, 2)
        self.assertEqual(analyze_candidate.await_count, 2)
        self.assertEqual(_duplicate_count(stats), 1)

    async def test_below_threshold_child_is_terminally_deduplicated(self):
        email = _digest("digest-low", DIGEST_ONE_JOB_HTML)
        candidate = parse_freelancehunt_digest(email)[0]
        processor, _ = self._processor([email])

        async def low_score(item, *args, **kwargs):
            return await _candidate_analysis(item, score=5.9)

        analyze_candidate = AsyncMock(side_effect=low_score)
        send_card = AsyncMock(return_value=True)
        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            first = await processor.run(trigger="manual")
            second = await processor.run(trigger="manual")

        self.assertEqual(first.below_threshold, 1)
        self.assertEqual(second.sent, 0)
        self.assertEqual(_duplicate_count(second), 1)
        self.assertEqual(analyze_candidate.await_count, 1)
        send_card.assert_not_awaited()
        processed = await self.repository.get_processed(candidate.stable_key)
        self.assertIsNotNone(processed)
        self.assertEqual(processed.decision, "below_threshold")

    async def test_telegram_failure_is_not_sent_success_and_remains_retryable(self):
        email = _digest("digest-retry", DIGEST_ONE_JOB_HTML)
        candidate = parse_freelancehunt_digest(email)[0]
        processor, _ = self._processor([email])
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        send_card = AsyncMock(side_effect=[False, True])

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            failed = await processor.run(trigger="manual")

            self.assertEqual(failed.sent, 0)
            self.assertEqual(failed.errors, 1)
            self.assertIsNone(
                await self.repository.get_processed(candidate.stable_key)
            )
            failed_job = await self.repository.get_job(candidate.stable_key)
            self.assertIsNotNone(failed_job)
            self.assertEqual(failed_job.status, "send_failed")

            retried = await processor.run(trigger="manual")

        self.assertEqual(retried.sent, 1)
        self.assertEqual(send_card.await_count, 2)
        sent_job = await self.repository.get_job(candidate.stable_key)
        self.assertEqual(sent_job.status, "sent")
        processed = await self.repository.get_processed(candidate.stable_key)
        self.assertIsNotNone(processed)
        self.assertEqual(processed.decision, "sent")

    async def test_parser_failure_does_not_mark_parent_processed(self):
        email = _digest("digest-parser-failure", DIGEST_ONE_JOB_HTML)
        processor, provider = self._processor([email])

        with (
            patch(
                "gmail_agent.processor.parse_freelancehunt_digest",
                side_effect=ValueError("synthetic malformed digest"),
            ),
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze,
            patch("gmail_agent.processor.send_job_card", AsyncMock()) as send_card,
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.errors, 1)
        self.assertEqual(stats.sent, 0)
        self.assertEqual(provider.marked, [])
        self.assertFalse(self.dedup.is_processed(email.id))
        analyze.assert_not_awaited()
        send_card.assert_not_awaited()

    async def test_scan_sends_at_most_ten_cards_and_keeps_rest_queued(self):
        email = _digest("digest-twelve", digest_with_job_count(12))
        candidates = parse_freelancehunt_digest(email)
        processor, _ = self._processor([email], max_cards_per_scan=10)
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(len(candidates), 12)
        self.assertEqual(analyze_candidate.await_count, 12)
        self.assertEqual(stats.sent, 10)
        self.assertEqual(send_card.await_count, 10)
        for candidate in candidates[:10]:
            self.assertEqual(
                (await self.repository.get_job(candidate.stable_key)).status,
                "sent",
            )
        for candidate in candidates[10:]:
            self.assertEqual(
                (await self.repository.get_job(candidate.stable_key)).status,
                "queued",
            )
            self.assertIsNone(
                await self.repository.get_processed(candidate.stable_key)
            )

    async def test_empty_next_scan_drains_persistent_queue_without_parent_or_ai(self):
        email = _digest("digest-twelve-drain", digest_with_job_count(12))
        candidates = parse_freelancehunt_digest(email)
        first_processor, first_provider = self._processor(
            [email], max_cards_per_scan=10
        )
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        analyze_email = AsyncMock()
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            first = await first_processor.run(trigger="manual")

            second_processor, second_provider = self._processor(
                [], max_cards_per_scan=10
            )
            second = await second_processor.run(trigger="scheduler")

        self.assertEqual(first.sent, 10)
        self.assertEqual(second.emails_fetched, 0)
        self.assertEqual(second.sent, 2)
        self.assertEqual(first_provider.fetch_count, 1)
        self.assertEqual(second_provider.fetch_count, 1)
        self.assertEqual(first_provider.marked, [email.id])
        self.assertEqual(second_provider.marked, [])
        self.assertEqual(analyze_candidate.await_count, 12)
        analyze_email.assert_not_awaited()
        self.assertEqual(send_card.await_count, 12)
        for candidate in candidates:
            self.assertEqual(
                (await self.repository.get_job(candidate.stable_key)).status,
                "sent",
            )
            self.assertEqual(
                (await self.repository.get_processed(candidate.stable_key)).decision,
                "sent",
            )

    async def test_informational_workua_email_uses_repository_dedup_without_ai(self):
        email = _workua_information()
        processor, provider = self._processor([email])
        analyze_email = AsyncMock()
        analyze_candidate = AsyncMock()
        send_card = AsyncMock()

        with (
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            first = await processor.run(trigger="manual")

            processed = await self.repository.get_processed(email.id)
            self.assertIsNotNone(processed)
            self.assertIn(
                processed.item_type,
                {"email", "informational_newsletter"},
            )
            self.assertEqual(processed.decision, "not_relevant")

            # A fresh processor has no legacy JSON knowledge.  The durable
            # repository decision alone must prevent repeat AI/work.
            restarted_provider = TrackingProvider([email])
            restarted_dedup = EmailDedup(
                Path(self.tempdir.name) / "fresh-informational-dedup.json"
            )
            restarted_processor = GmailJobProcessor(
                provider=restarted_provider,
                bot=self.bot,
                chat_id=123456789,
                min_score=6.0,
                dedup=restarted_dedup,
                repository=self.repository,
                max_cards_per_scan=10,
                digest_enabled=True,
                job_store_path=Path(self.tempdir.name) / "info-jobs.json",
            )
            second = await restarted_processor.run(trigger="manual")

        self.assertEqual(first.not_relevant, 1)
        self.assertEqual(first.sent, 0)
        self.assertEqual(second.not_relevant, 0)
        self.assertEqual(second.sent, 0)
        self.assertEqual(_duplicate_count(second), 1)
        analyze_email.assert_not_awaited()
        analyze_candidate.assert_not_awaited()
        send_card.assert_not_awaited()
        self.assertEqual(provider.marked, ["workua-info-001"])
        self.assertEqual(restarted_provider.marked, [])
        self.assertFalse(restarted_dedup.is_processed(email.id))

    async def test_existing_single_job_flow_still_uses_analyze_email(self):
        email = _single_job()
        processor, _ = self._processor([email])
        analyze_email = AsyncMock(
            return_value=_analysis(
                email.id,
                title="Synthetic Telegram automation",
                url="https://freelancehunt.com/project/synthetic/123.html",
            )
        )
        analyze_candidate = AsyncMock()
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.sent, 1)
        analyze_email.assert_awaited_once()
        analyze_candidate.assert_not_awaited()
        send_card.assert_awaited_once()

    async def test_repository_single_jobs_share_the_ten_card_scan_cap(self):
        emails = [_single_job_with_id(index) for index in range(1, 12)]
        processor, _ = self._processor(emails, max_cards_per_scan=10)

        async def analyze_single(*args, **kwargs):
            email_id = kwargs["email_id"]
            return _analysis(
                email_id,
                title=f"Analyzed {email_id}",
                url=f"https://freelancehunt.com/project/{email_id}/99.html",
            )

        analyze_email = AsyncMock(side_effect=analyze_single)
        analyze_candidate = AsyncMock()
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.relevant, 11)
        self.assertEqual(stats.sent, 10)
        self.assertEqual(analyze_email.await_count, 11)
        analyze_candidate.assert_not_awaited()
        self.assertEqual(send_card.await_count, 10)
        for email in emails[:10]:
            job = await self.repository.get_job(email.id)
            self.assertEqual(job.status, "sent")
            self.assertEqual(
                (await self.repository.get_processed(email.id)).decision,
                "sent",
            )

        queued = await self.repository.get_job(emails[10].id)
        self.assertIsNotNone(queued)
        self.assertEqual(queued.status, "queued")
        self.assertIsNone(await self.repository.get_processed(emails[10].id))
        retryable = await self.repository.list_retryable_jobs(limit=10)
        self.assertEqual([job.stable_key for job in retryable], [emails[10].id])

    async def test_disabled_digest_pipeline_never_treats_digest_as_single_job(self):
        email = _digest("disabled-digest", DIGEST_TWO_JOBS_HTML)
        candidates = parse_freelancehunt_digest(email)
        provider = TrackingProvider([email])
        processor = GmailJobProcessor(
            provider=provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=10,
            digest_enabled=False,
            job_store_path=Path(self.tempdir.name) / "disabled-jobs.json",
        )
        analyze_email = AsyncMock()
        analyze_candidate = AsyncMock()
        send_card = AsyncMock()

        with (
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="manual")

        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.errors, 0)
        analyze_email.assert_not_awaited()
        analyze_candidate.assert_not_awaited()
        send_card.assert_not_awaited()
        self.assertEqual(provider.marked, [])
        self.assertFalse(self.dedup.is_processed(email.id))
        self.assertFalse(await self.repository.is_processed(email.id))
        for candidate in candidates:
            self.assertFalse(
                await self.repository.is_processed(candidate.stable_key)
            )
            self.assertIsNone(await self.repository.get_job(candidate.stable_key))

    async def test_disabled_digest_pipeline_does_not_drain_queued_digest_child(self):
        parent = _digest("disabled-queued-parent", DIGEST_ONE_JOB_HTML)
        candidate = parse_freelancehunt_digest(parent)[0]
        analysis = await _candidate_analysis(candidate)
        queued = GmailJobProcessor._stored_job(candidate, analysis)
        await self.repository.save_job(queued)
        provider = TrackingProvider([])
        processor = GmailJobProcessor(
            provider=provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=10,
            digest_enabled=False,
            job_store_path=Path(self.tempdir.name) / "disabled-queued-jobs.json",
        )
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze_email,
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze_candidate,
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="scheduler")

        self.assertEqual(stats.emails_fetched, 0)
        self.assertEqual(stats.sent, 0)
        analyze_email.assert_not_awaited()
        analyze_candidate.assert_not_awaited()
        send_card.assert_not_awaited()
        self.assertEqual(provider.marked, [])
        self.assertEqual(
            (await self.repository.get_job(candidate.stable_key)).status,
            "queued",
        )
        self.assertIsNone(await self.repository.get_processed(candidate.stable_key))

    async def test_disabled_digest_pipeline_can_still_drain_queued_single_job(self):
        email = _single_job_with_id(901)
        analysis = _analysis(
            email.id,
            title="Persisted single job",
            url="https://freelancehunt.com/project/persisted-single/901.html",
        )
        await self.repository.save_job(
            GmailJobProcessor._stored_single_job(email, analysis)
        )
        provider = TrackingProvider([])
        processor = GmailJobProcessor(
            provider=provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=10,
            digest_enabled=False,
            job_store_path=Path(self.tempdir.name) / "disabled-single-jobs.json",
        )
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze_email,
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze_candidate,
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run(trigger="scheduler")

        self.assertEqual(stats.sent, 1)
        analyze_email.assert_not_awaited()
        analyze_candidate.assert_not_awaited()
        send_card.assert_awaited_once()
        self.assertEqual(
            (await self.repository.get_job(email.id)).status,
            "sent",
        )
        self.assertEqual(
            (await self.repository.get_processed(email.id)).decision,
            "sent",
        )

    async def test_recognized_digest_without_repository_is_always_retryable(self):
        email = _digest("repositoryless-digest", DIGEST_TWO_JOBS_HTML)

        for digest_enabled in (True, False):
            with self.subTest(digest_enabled=digest_enabled):
                dedup = EmailDedup(
                    Path(self.tempdir.name)
                    / f"repositoryless-{digest_enabled}.json"
                )
                provider = TrackingProvider([email])
                processor = GmailJobProcessor(
                    provider=provider,
                    bot=self.bot,
                    chat_id=123456789,
                    min_score=6.0,
                    dedup=dedup,
                    repository=None,
                    max_cards_per_scan=10,
                    digest_enabled=digest_enabled,
                    job_store_path=Path(self.tempdir.name)
                    / f"repositoryless-jobs-{digest_enabled}.json",
                )
                analyze_email = AsyncMock(
                    return_value=_analysis(email.id, title="Whole digest")
                )
                analyze_candidate = AsyncMock()
                send_card = AsyncMock(return_value=True)

                with (
                    patch("gmail_agent.processor.analyze_email", analyze_email),
                    patch(
                        "gmail_agent.processor.analyze_candidate", analyze_candidate
                    ),
                    patch("gmail_agent.processor.send_job_card", send_card),
                ):
                    first = await processor.run(trigger="manual")
                    second = await processor.run(trigger="manual")

                self.assertEqual(first.sent, 0)
                self.assertEqual(second.sent, 0)
                analyze_email.assert_not_awaited()
                analyze_candidate.assert_not_awaited()
                send_card.assert_not_awaited()
                self.assertEqual(provider.marked, [])
                self.assertFalse(dedup.is_processed(email.id))
                self.assertFalse(
                    (
                        Path(self.tempdir.name)
                        / f"repositoryless-jobs-{digest_enabled}.json"
                    ).exists()
                )

    async def test_repository_is_source_of_truth_for_successful_single_job(self):
        email = _single_job()
        processor, _ = self._processor([email])
        legacy_job_store = Path(self.tempdir.name) / "jobs.json"
        legacy_sentinel = '{"legacy-job":{"title":"must remain unchanged"}}\n'
        legacy_job_store.write_text(legacy_sentinel, encoding="utf-8")
        analyze_email = AsyncMock(
            return_value=_analysis(
                email.id,
                title="Synthetic Telegram automation",
                url="https://freelancehunt.com/project/synthetic/123.html",
            )
        )
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", analyze_email),
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze_candidate,
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            first = await processor.run(trigger="manual")

            stored_job = await self.repository.get_job(email.id)
            processed = await self.repository.get_processed(email.id)
            self.assertEqual(first.sent, 1)
            self.assertIsNotNone(stored_job)
            self.assertEqual(stored_job.status, "sent")
            self.assertEqual(stored_job.source_email_id, email.id)
            self.assertIsNotNone(processed)
            self.assertEqual(processed.decision, "sent")
            self.assertEqual(processed.item_type, "single_job")
            self.assertEqual(
                legacy_job_store.read_text(encoding="utf-8"),
                legacy_sentinel,
                "repository-backed single jobs must not mutate legacy JSON",
            )

            # Simulate a restart with the same durable repository but a new,
            # empty legacy JSON file.  Repository state alone must suppress AI
            # and Telegram side effects on the repeated scan.
            restarted_provider = TrackingProvider([email])
            restarted_dedup = EmailDedup(
                Path(self.tempdir.name) / "fresh-after-restart.json"
            )
            restarted_processor = GmailJobProcessor(
                provider=restarted_provider,
                bot=self.bot,
                chat_id=123456789,
                min_score=6.0,
                dedup=restarted_dedup,
                repository=self.repository,
                max_cards_per_scan=10,
                digest_enabled=True,
                job_store_path=Path(self.tempdir.name) / "restart-jobs.json",
            )
            second = await restarted_processor.run(trigger="manual")

        self.assertEqual(second.sent, 0)
        self.assertEqual(_duplicate_count(second), 1)
        self.assertEqual(analyze_email.await_count, 1)
        analyze_candidate.assert_not_awaited()
        self.assertEqual(send_card.await_count, 1)
        self.assertFalse(restarted_dedup.is_processed(email.id))
        self.assertEqual(restarted_provider.marked, [])
        self.assertFalse(
            (Path(self.tempdir.name) / "restart-jobs.json").exists(),
            "repository-backed restart must not create a legacy job store",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
