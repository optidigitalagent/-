"""Integration tests for GmailJobProcessor — full pipeline with mocks."""

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.dedup import EmailDedup
from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.gmail_provider import MockGmailProvider
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.tests.mock_emails import (
    ALL_MOCK_EMAILS,
    EMAIL_FREELANCEHUNT_AI_BOT,
    EMAIL_SPAM_NEWSLETTER,
    RELEVANT_EMAIL_IDS,
)


class FailingGmailProvider(MockGmailProvider):
    async def get_new_emails(self):
        raise RuntimeError("Gmail OAuth token cannot be refreshed (invalid_grant).")


def _make_analysis(email_id: str, score: float, is_relevant: bool) -> JobAnalysis:
    return JobAnalysis(
        email_id=email_id,
        is_relevant=is_relevant,
        title="Test Job" if is_relevant else "",
        platform="Freelancehunt",
        score=score,
        reason="Test reason",
        budget="5000 UAH",
        url="https://example.com",
        urgency="medium",
        why_relevant="Test relevance",
        red_flags=[],
    )


class TestGmailJobProcessor(unittest.IsolatedAsyncioTestCase):
    def _make_processor(self, emails, analyze_fn, dedup_path, min_score=6.0):
        provider = MockGmailProvider(emails=emails)
        bot = MagicMock()
        bot.send_message = AsyncMock()

        dedup = EmailDedup(dedup_path)
        dedup.clear()

        processor = GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=123456789,
            min_score=min_score,
            dedup=dedup,
            job_store_path=f"{dedup_path}.jobs",
        )
        return processor, bot

    async def test_relevant_email_sent_to_telegram(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor(
            emails=[EMAIL_FREELANCEHUNT_AI_BOT],
            analyze_fn=None,
            dedup_path=dedup_path,
        )

        high_score_analysis = _make_analysis("mock_fh_001", 8.5, True)
        with patch(
            "gmail_agent.processor.analyze_email",
            AsyncMock(return_value=high_score_analysis),
        ):
            stats = await processor.run()

        self.assertEqual(stats.emails_fetched, 1)
        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.errors, 0)
        bot.send_message.assert_called_once()

    async def test_spam_email_not_sent(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor(
            emails=[EMAIL_SPAM_NEWSLETTER],
            analyze_fn=None,
            dedup_path=dedup_path,
        )

        spam_analysis = _make_analysis("mock_spam_004", 0.0, False)
        with patch(
            "gmail_agent.processor.analyze_email",
            AsyncMock(return_value=spam_analysis),
        ):
            stats = await processor.run()

        self.assertEqual(stats.not_relevant, 1)
        self.assertEqual(stats.sent, 0)
        bot.send_message.assert_not_called()

    async def test_below_threshold_not_sent(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor(
            emails=[EMAIL_FREELANCEHUNT_AI_BOT],
            analyze_fn=None,
            dedup_path=dedup_path,
            min_score=7.0,
        )

        low_score_analysis = _make_analysis("mock_fh_001", 5.0, True)
        with patch(
            "gmail_agent.processor.analyze_email",
            AsyncMock(return_value=low_score_analysis),
        ):
            stats = await processor.run()

        self.assertEqual(stats.below_threshold, 1)
        self.assertEqual(stats.sent, 0)
        bot.send_message.assert_not_called()

    async def test_duplicate_not_sent_twice(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        provider = MockGmailProvider(emails=[EMAIL_FREELANCEHUNT_AI_BOT])
        bot = MagicMock()
        bot.send_message = AsyncMock()
        dedup = EmailDedup(dedup_path)
        dedup.clear()

        processor = GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=dedup,
            job_store_path=f"{dedup_path}.jobs",
        )

        high_score_analysis = _make_analysis("mock_fh_001", 8.5, True)
        with patch(
            "gmail_agent.processor.analyze_email",
            AsyncMock(return_value=high_score_analysis),
        ):
            stats1 = await processor.run()
            stats2 = await processor.run()

        self.assertEqual(stats1.sent, 1)
        self.assertEqual(stats2.duplicates_skipped, 1)
        self.assertEqual(stats2.sent, 0)
        self.assertEqual(bot.send_message.call_count, 1)

    async def test_empty_inbox_no_errors(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor(
            emails=[],
            analyze_fn=None,
            dedup_path=dedup_path,
        )

        stats = await processor.run()

        self.assertEqual(stats.emails_fetched, 0)
        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.errors, 0)

    async def test_telegram_send_failure_is_not_deduped(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        processor, bot = self._make_processor(
            emails=[EMAIL_FREELANCEHUNT_AI_BOT],
            analyze_fn=None,
            dedup_path=dedup_path,
        )
        bot.send_message.side_effect = RuntimeError("telegram down")

        high_score_analysis = _make_analysis("mock_fh_001", 8.5, True)
        with patch(
            "gmail_agent.processor.analyze_email",
            AsyncMock(return_value=high_score_analysis),
        ):
            stats = await processor.run()

        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.errors, 1)
        self.assertIn("Telegram send failed", stats.error_details[0])
        self.assertFalse(processor._dedup.is_processed("mock_fh_001"))

    async def test_fetch_error_reports_error_details(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            dedup_path = f.name

        bot = MagicMock()
        bot.send_message = AsyncMock()
        dedup = EmailDedup(dedup_path)
        dedup.clear()
        processor = GmailJobProcessor(
            provider=FailingGmailProvider(),
            bot=bot,
            chat_id=123456789,
            min_score=6.0,
            dedup=dedup,
            job_store_path=f"{dedup_path}.jobs",
        )

        stats = await processor.run()

        self.assertEqual(stats.emails_fetched, 0)
        self.assertEqual(stats.sent, 0)
        self.assertEqual(stats.errors, 1)
        self.assertIn("invalid_grant", stats.error_details[0])
        bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
