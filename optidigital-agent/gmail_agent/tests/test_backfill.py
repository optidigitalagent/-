"""Side-effect and idempotency contracts for digest preview/backfill."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.dedup import EmailDedup
from gmail_agent.digest_parser import parse_freelancehunt_digest
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.storage import InMemoryGmailRepository, StoredGmailJob
from gmail_agent.tests.digest_fixtures import DIGEST_TWO_JOBS_HTML
from gmail_agent.tests.test_digest_processor import (
    TrackingProvider,
    _candidate_analysis,
    _digest,
    _duplicate_count,
)


class TestDigestPreviewAndBackfill(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.dedup = EmailDedup(Path(self.tempdir.name) / "email-dedup.json")
        self.dedup.mark_processed("legacy-email-dedup-key")
        self.repository = InMemoryGmailRepository()
        self.email = _digest("historical-digest", DIGEST_TWO_JOBS_HTML)
        self.candidates = parse_freelancehunt_digest(self.email)
        self.provider = TrackingProvider([self.email])
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock()
        self.processor = GmailJobProcessor(
            provider=self.provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=10,
            digest_enabled=True,
            job_store_path=Path(self.tempdir.name) / "jobs.json",
        )

    async def test_preview_parses_and_scores_without_any_persistent_or_send_side_effect(self):
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        send_card = AsyncMock()

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze_email,
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            preview = await self.processor.run_digest_preview(days=7)

        self.assertEqual(len(preview.items), 2)
        self.assertEqual(preview.stats.emails_fetched, 1)
        self.assertEqual(preview.stats.candidates_found, 2)
        self.assertEqual(preview.stats.ai_analyzed, 2)
        self.assertEqual(preview.stats.qualified, 2)
        self.assertEqual(analyze_candidate.await_count, 2)
        analyze_email.assert_not_awaited()
        send_card.assert_not_awaited()
        self.assertEqual(self.provider.marked, [])
        self.assertTrue(self.dedup.is_processed("legacy-email-dedup-key"))
        self.assertEqual(self.dedup.count(), 1)
        self.assertEqual(await self.repository.list_scan_runs(), [])
        for candidate, item in zip(self.candidates, preview.items):
            self.assertEqual(item.stable_key, candidate.stable_key)
            self.assertEqual(item.title, candidate.title)
            self.assertTrue(item.is_relevant)
            self.assertEqual(item.score, 8.0)
            self.assertTrue(item.reason)
            self.assertFalse(await self.repository.is_processed(candidate.stable_key))
            self.assertIsNone(await self.repository.get_job(candidate.stable_key))

    async def test_backfill_preserves_legacy_dedup_and_repeat_yields_only_duplicates(self):
        analyze_candidate = AsyncMock(side_effect=_candidate_analysis)
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze_candidate),
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            first = await self.processor.run_digest_backfill(days=7)
            second = await self.processor.run_digest_backfill(days=7)

        self.assertEqual(first.sent, 2)
        self.assertEqual(first.ai_analyzed, 2)
        self.assertEqual(first.qualified, 2)
        self.assertEqual(second.sent, 0)
        self.assertEqual(second.ai_analyzed, 0)
        self.assertEqual(_duplicate_count(second), 2)
        self.assertEqual(send_card.await_count, 2)
        self.assertEqual(analyze_candidate.await_count, 2)
        self.assertTrue(self.dedup.is_processed("legacy-email-dedup-key"))
        for candidate in self.candidates:
            processed = await self.repository.get_processed(candidate.stable_key)
            self.assertIsNotNone(processed)
            self.assertEqual(processed.decision, "sent")

    async def test_empty_backfill_does_not_drain_or_mutate_unrelated_global_queue(self):
        provider = TrackingProvider([])
        processor = GmailJobProcessor(
            provider=provider,
            bot=self.bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=self.dedup,
            repository=self.repository,
            max_cards_per_scan=10,
            digest_enabled=True,
            job_store_path=Path(self.tempdir.name) / "empty-backfill-jobs.json",
        )
        unrelated = StoredGmailJob(
            stable_key="unrelated-single-job",
            source_email_id="unrelated-single-job",
            platform="Work.ua",
            title="Unrelated global queue item",
            score=8.0,
            reason="Synthetic reason",
            budget=None,
            url="https://www.work.ua/jobs/12345678/",
            urgency="medium",
            why_relevant="Synthetic match",
            status="queued",
        )
        before = await self.repository.save_job(unrelated)
        send_card = AsyncMock(return_value=True)

        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze_email,
            patch("gmail_agent.processor.analyze_candidate", AsyncMock()) as analyze_candidate,
            patch("gmail_agent.processor.send_job_card", send_card),
        ):
            stats = await processor.run_digest_backfill(days=7)

        self.assertEqual(stats.emails_fetched, 0)
        self.assertEqual(stats.sent, 0)
        analyze_email.assert_not_awaited()
        analyze_candidate.assert_not_awaited()
        send_card.assert_not_awaited()
        self.assertEqual(provider.marked, [])
        self.assertEqual(await self.repository.get_job(unrelated.stable_key), before)
        self.assertIsNone(await self.repository.get_processed(unrelated.stable_key))


if __name__ == "__main__":
    unittest.main(verbosity=2)
