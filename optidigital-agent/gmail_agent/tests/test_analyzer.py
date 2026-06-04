"""Tests for email_analyzer — uses mock OpenAI client."""

import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.email_analyzer import JobAnalysis, _detect_platform, analyze_email


def _mock_openai_client(json_response: str):
    """Create mock AsyncOpenAI that returns json_response."""
    mock_choice = MagicMock()
    mock_choice.message.content = json_response

    mock_completion = MagicMock()
    mock_completion.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
    return mock_client


class TestDetectPlatform(unittest.TestCase):
    def test_freelancehunt(self):
        self.assertEqual(_detect_platform("noreply@freelancehunt.com"), "Freelancehunt")

    def test_workua(self):
        self.assertEqual(_detect_platform("notifications@work.ua"), "Work.ua")

    def test_upwork(self):
        self.assertEqual(_detect_platform("donotreply@upwork.com"), "Upwork")

    def test_unknown(self):
        self.assertEqual(_detect_platform("spam@example.com"), "Unknown")


class TestAnalyzeEmail(unittest.IsolatedAsyncioTestCase):
    async def test_relevant_ai_email(self):
        mock_response = """{
            "is_relevant": true,
            "title": "Telegram-бот з AI",
            "platform": "Freelancehunt",
            "score": 8.5,
            "reason": "AI/bot проект з гарним бюджетом",
            "budget": "8000–15000 UAH",
            "url": "https://freelancehunt.com/project/12345",
            "urgency": "high",
            "why_relevant": "Telegram-бот + OpenAI API — пряма спеціалізація",
            "red_flags": []
        }"""

        client = _mock_openai_client(mock_response)
        result = await analyze_email(
            email_id="test_001",
            subject="Новий проект: Telegram-бот з AI",
            sender="noreply@freelancehunt.com",
            body="Потрібен Telegram-бот з ChatGPT API. Бюджет 8000–15000 UAH.",
            client=client,
        )

        self.assertIsInstance(result, JobAnalysis)
        self.assertTrue(result.is_relevant)
        self.assertEqual(result.score, 8.5)
        self.assertEqual(result.platform, "Freelancehunt")
        self.assertEqual(result.urgency, "high")
        self.assertEqual(result.red_flags, [])

    async def test_not_relevant_spam(self):
        mock_response = """{
            "is_relevant": false,
            "title": "",
            "platform": "Unknown",
            "score": 0.0,
            "reason": "Це рекламна розсилка, не вакансія",
            "budget": "не вказано",
            "url": "",
            "urgency": "low",
            "why_relevant": "",
            "red_flags": ["spam"]
        }"""

        client = _mock_openai_client(mock_response)
        result = await analyze_email(
            email_id="test_spam",
            subject="Знижки до 50%!",
            sender="promo@spam.ua",
            body="Купуй курси зі знижкою!",
            client=client,
        )

        self.assertFalse(result.is_relevant)
        self.assertEqual(result.score, 0.0)

    async def test_openai_error_returns_default(self):
        """If OpenAI fails, returns non-relevant analysis with score=0."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception("API timeout")
        )

        result = await analyze_email(
            email_id="test_error",
            subject="Test",
            sender="test@example.com",
            body="Test body",
            client=mock_client,
        )

        self.assertIsInstance(result, JobAnalysis)
        self.assertFalse(result.is_relevant)
        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
