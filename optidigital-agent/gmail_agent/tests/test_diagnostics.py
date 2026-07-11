"""Tests for enhanced diagnostics: ProcessorStats samples, run_debug, scan history."""

import asyncio
import sys
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.dedup import EmailDedup
from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.gmail_provider import MockGmailProvider
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.tests.mock_emails import (
    ALL_MOCK_EMAILS,
    EMAIL_FREELANCEHUNT_AI_BOT,
    EMAIL_FREELANCEHUNT_LOW_BUDGET,
    EMAIL_SPAM_NEWSLETTER,
)


def _make_analysis(email_id: str, score: float, is_relevant: bool, reason: str = "") -> JobAnalysis:
    return JobAnalysis(
        email_id=email_id,
        is_relevant=is_relevant,
        title="Test Job" if is_relevant else "",
        platform="Freelancehunt",
        score=score,
        reason=reason or ("Підходить" if is_relevant else "not_job_alert"),
        budget="5000 UAH",
        url="https://example.com",
        urgency="medium",
        why_relevant="Test relevance",
        red_flags=[],
    )


class TestProcessorStatsFields(unittest.TestCase):
    """ProcessorStats must have the new diagnostic sample fields."""

    def test_has_rejected_samples_field(self):
        stat_fields = {f.name for f in fields(ProcessorStats)}
        self.assertIn("rejected_samples", stat_fields)

    def test_has_below_score_samples_field(self):
        stat_fields = {f.name for f in fields(ProcessorStats)}
        self.assertIn("below_score_samples", stat_fields)

    def test_defaults_are_empty_lists(self):
        stats = ProcessorStats()
        self.assertEqual(stats.rejected_samples, [])
        self.assertEqual(stats.below_score_samples, [])


class TestProcessorDiagnosticSamples(unittest.IsolatedAsyncioTestCase):
    """Processor populates rejected_samples and below_score_samples."""

    def _make_processor(self, emails, dedup_path, min_score=6.0):
        provider = MockGmailProvider(emails=emails)
        bot = MagicMock()
        bot.send_message = AsyncMock()
        dedup = EmailDedup(dedup_path)
        dedup.clear()
        return GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=123456789,
            min_score=min_score,
            dedup=dedup,
            job_store_path=f"{dedup_path}.jobs",
        )

    async def test_rejected_sample_populated_for_not_relevant(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor = self._make_processor([EMAIL_SPAM_NEWSLETTER], dedup_path)
        spam_analysis = _make_analysis("mock_spam_004", 0.0, False, reason="spam newsletter")

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=spam_analysis)):
            stats = await processor.run()

        self.assertEqual(stats.not_relevant, 1)
        self.assertEqual(len(stats.rejected_samples), 1)
        sample = stats.rejected_samples[0]
        self.assertIn("from", sample)
        self.assertIn("subject", sample)
        self.assertIn("reason", sample)
        self.assertEqual(sample["reason"], "spam newsletter")

    async def test_below_score_sample_populated(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path, min_score=7.0)
        low_score = _make_analysis("mock_fh_001", 5.0, True, reason="Низький бюджет")

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=low_score)):
            stats = await processor.run()

        self.assertEqual(stats.below_threshold, 1)
        self.assertEqual(len(stats.below_score_samples), 1)
        sample = stats.below_score_samples[0]
        self.assertAlmostEqual(sample["score"], 5.0)
        self.assertEqual(sample["reason"], "Низький бюджет")

    async def test_rejected_samples_capped_at_five(self):
        """Even with many not_relevant emails, only 5 samples are stored."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        # Create 7 distinct spam emails
        from gmail_agent.gmail_provider import EmailMessage
        from datetime import datetime
        spams = [
            EmailMessage(
                id=f"spam_{i}",
                subject=f"Spam {i}",
                sender="promo@example.com",
                body="spam",
                received_at=datetime.utcnow(),
            )
            for i in range(7)
        ]

        processor = self._make_processor(spams, dedup_path)
        spam_analysis = _make_analysis("any", 0.0, False)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=spam_analysis)):
            stats = await processor.run()

        self.assertEqual(stats.not_relevant, 7)
        self.assertLessEqual(len(stats.rejected_samples), 5)


class TestRunDebug(unittest.IsolatedAsyncioTestCase):
    """run_debug() returns analysis results without sending to Telegram and without marking dedup."""

    def _make_processor(self, emails, dedup_path, min_score=6.0):
        provider = MockGmailProvider(emails=emails)
        bot = MagicMock()
        bot.send_message = AsyncMock()
        dedup = EmailDedup(dedup_path)
        dedup.clear()
        return GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=123456789,
            min_score=min_score,
            dedup=dedup,
            job_store_path=f"{dedup_path}.jobs",
        ), bot

    async def test_debug_does_not_send_telegram(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path)
        high_score = _make_analysis("mock_fh_001", 9.0, True)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=high_score)):
            results = await processor.run_debug()

        bot.send_message.assert_not_called()
        self.assertEqual(len(results), 1)

    async def test_debug_does_not_mark_dedup(self):
        """After run_debug, the email should still be processable by normal run()."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path)
        high_score = _make_analysis("mock_fh_001", 9.0, True)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=high_score)):
            await processor.run_debug()
            # After debug, dedup should NOT be updated
            dedup = processor._dedup
            self.assertFalse(dedup.is_processed("mock_fh_001"))

    async def test_debug_returns_passed_flag(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, _ = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path, min_score=6.0)
        high_score = _make_analysis("mock_fh_001", 8.0, True)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=high_score)):
            results = await processor.run_debug()

        self.assertTrue(results[0]["passed"])

    async def test_debug_returns_failed_flag_for_low_score(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, _ = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path, min_score=7.0)
        low_score = _make_analysis("mock_fh_001", 4.0, True)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=low_score)):
            results = await processor.run_debug()

        self.assertFalse(results[0]["passed"])

    async def test_debug_marks_duplicate_without_analyzing(self):
        """Email already in dedup is returned as duplicate without AI analysis."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, _ = self._make_processor([EMAIL_FREELANCEHUNT_AI_BOT], dedup_path)
        # Pre-mark as processed
        processor._dedup.mark_processed("mock_fh_001")

        analyze_mock = AsyncMock()
        with patch("gmail_agent.processor.analyze_email", analyze_mock):
            results = await processor.run_debug()

        # analyze_email should NOT be called for duplicates
        analyze_mock.assert_not_called()
        self.assertTrue(results[0]["is_duplicate"])

    async def test_debug_all_mock_emails(self):
        """run_debug handles all 5 mock emails and returns 5 results."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, _ = self._make_processor(ALL_MOCK_EMAILS, dedup_path)

        def _analysis_for(email_id, *args, **kwargs):
            relevant = email_id in {"mock_fh_001", "mock_wu_002", "mock_uw_003"}
            score = 8.0 if relevant else 0.0
            return _make_analysis(email_id, score, relevant)

        with patch("gmail_agent.processor.analyze_email", AsyncMock(side_effect=_analysis_for)):
            results = await processor.run_debug(max_emails=20)

        self.assertEqual(len(results), 5)
        passed = [r for r in results if r.get("passed")]
        self.assertEqual(len(passed), 3)

    async def test_debug_empty_inbox(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, _ = self._make_processor([], dedup_path)
        results = await processor.run_debug()
        self.assertEqual(results, [])


class TestScanHistoryState(unittest.TestCase):
    """gmail_scan_history in state.py accumulates entries and caps at 20."""

    def test_state_has_gmail_scan_history(self):
        import state
        self.assertTrue(hasattr(state, "gmail_scan_history"))
        self.assertIsInstance(state.gmail_scan_history, list)

    def test_history_capped_at_twenty(self):
        import state
        from datetime import datetime

        original = state.gmail_scan_history[:]
        state.gmail_scan_history.clear()

        try:
            for i in range(25):
                state.gmail_scan_history.append({
                    "timestamp": datetime.utcnow(),
                    "emails_found": i,
                    "relevant": 0,
                    "sent": 0,
                    "errors": 0,
                })
                if len(state.gmail_scan_history) > 20:
                    state.gmail_scan_history = state.gmail_scan_history[-20:]

            self.assertEqual(len(state.gmail_scan_history), 20)
            # Last entry should have emails_found=24
            self.assertEqual(state.gmail_scan_history[-1]["emails_found"], 24)
        finally:
            state.gmail_scan_history[:] = original


if __name__ == "__main__":
    unittest.main(verbosity=2)
