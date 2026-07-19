"""Acceptance tests for the safe Gmail job-alert prefilter and /gmail_debug."""

import ast
import logging
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from gmail_agent.dedup import EmailDedup
from gmail_agent.gmail_provider import (
    EmailMatchDiagnostic,
    RealGmailProvider,
    build_email_diagnostic,
)


def _load_handler_function(name: str, extra_globals: dict | None = None):
    """Load one real handler function without importing optional bot dependencies."""
    handlers_path = PROJECT_ROOT / "bot" / "handlers.py"
    tree = ast.parse(handlers_path.read_text(encoding="utf-8"), filename=str(handlers_path))
    function = next(
        node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    )
    function.decorator_list = []
    namespace = {"Message": object}
    if extra_globals:
        namespace.update(extra_globals)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(handlers_path), "exec"), namespace)
    return namespace[name]


class TestJobAlertPrefilter(unittest.TestCase):
    def test_freelancehunt_display_name_and_address_pass(self):
        result = build_email_diagnostic(
            sender="Freelancehunt <info@freelancehunt.com>",
            subject="A project selected for you",
        )

        self.assertEqual(result.sender_display_name, "Freelancehunt")
        self.assertEqual(result.sender_email, "info@freelancehunt.com")
        self.assertTrue(result.sender_matched)
        self.assertTrue(result.is_job_alert)
        self.assertEqual(result.platform, "Freelancehunt")

    def test_freelancehunt_subdomain_address_passes(self):
        result = build_email_diagnostic(
            sender="notifications@news.freelancehunt.com",
            subject="A project selected for you",
        )

        self.assertTrue(result.sender_matched)
        self.assertTrue(result.is_job_alert)
        self.assertEqual(result.platform, "Freelancehunt")

    def test_gmail_sender_does_not_pass(self):
        result = build_email_diagnostic(
            sender="Private Person <user@gmail.com>",
            subject="Lunch tomorrow?",
        )

        self.assertFalse(result.sender_matched)
        self.assertFalse(result.subject_matched)
        self.assertFalse(result.is_job_alert)
        self.assertEqual(result.platform, "Unknown")

    def test_personal_subject_containing_only_robota_does_not_pass(self):
        result = build_email_diagnostic(
            sender="Friend <user@gmail.com>",
            subject="робота",
        )

        self.assertFalse(result.sender_matched)
        self.assertFalse(result.subject_matched)
        self.assertFalse(result.is_job_alert)

    def test_platform_detection_for_workua_robota_and_upwork(self):
        cases = (
            ("jobs@alerts.work.ua", "Work.ua"),
            ("notify@robota.ua", "Robota.ua"),
            ("jobs@news.upwork.com", "Upwork"),
        )

        for sender, expected_platform in cases:
            with self.subTest(sender=sender):
                result = build_email_diagnostic(sender=sender, subject="Selected for you")
                self.assertTrue(result.sender_matched)
                self.assertTrue(result.is_job_alert)
                self.assertEqual(result.platform, expected_platform)


class TestRealProviderHeaderOnlyFetch(unittest.TestCase):
    def test_recent_diagnostics_fetches_metadata_only_and_never_full_or_body(self):
        provider = RealGmailProvider("unused-credentials.json", "unused-token.json")
        service = MagicMock()
        messages_api = service.users.return_value.messages.return_value
        messages_api.list.return_value.execute.return_value = {
            "messages": [{"id": "gmail-full-message-id-123456789"}]
        }
        messages_api.get.return_value.execute.return_value = {
            "id": "gmail-full-message-id-123456789",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Freelancehunt <info@freelancehunt.com>"},
                    {"name": "Subject", "value": "New project"},
                    {"name": "Date", "value": "Sun, 19 Jul 2026 10:00:00 +0300"},
                ],
                "body": {"data": "BODY_MUST_NOT_BE_READ"},
            },
        }
        provider._service = service

        results = provider._fetch_recent_diagnostics(max_results=10)

        self.assertEqual(len(results), 1)
        messages_api.get.assert_called_once_with(
            userId="me",
            id="gmail-full-message-id-123456789",
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        )
        for call in messages_api.get.call_args_list:
            self.assertEqual(call.kwargs["format"], "metadata")
            self.assertNotEqual(call.kwargs["format"], "full")


class TestGmailDebugSafety(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.format_results = _load_handler_function("_format_gmail_debug_results")

    async def test_debug_handler_does_not_update_dedup_invoke_ai_or_send_job_card(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dedup = EmailDedup(Path(temp_dir) / "processed.json")
            dedup.mark_processed("already-processed")
            before_count = dedup.count()

            provider = MagicMock()
            provider.get_recent_email_diagnostics = AsyncMock(return_value=[
                build_email_diagnostic(
                    "Freelancehunt <info@freelancehunt.com>",
                    "New project",
                    "Sun, 19 Jul 2026 10:00:00 +0300",
                )
            ])
            provider.get_new_emails = AsyncMock()
            provider.mark_as_processed = AsyncMock()
            message = MagicMock()
            message.answer = AsyncMock()
            settings = SimpleNamespace(
                GMAIL_ENABLED=True,
                GMAIL_USE_MOCK=False,
                GMAIL_CREDENTIALS_FILE="unused-credentials.json",
                GMAIL_TOKEN_FILE="unused-token.json",
            )
            handler = _load_handler_function(
                "cmd_gmail_debug",
                {
                    "settings": settings,
                    "logger": logging.getLogger(__name__),
                    "_format_gmail_debug_results": self.format_results,
                },
            )

            with (
                patch("gmail_agent.gmail_provider.build_provider", return_value=provider),
                patch("gmail_agent.dedup.EmailDedup.mark_processed") as mark_processed,
                patch("gmail_agent.email_analyzer.analyze_email", new=AsyncMock()) as analyze,
                patch("gmail_agent.telegram_notifier.send_job_card", new=AsyncMock()) as send_card,
            ):
                await handler(message)

            provider.get_recent_email_diagnostics.assert_awaited_once_with(max_results=10)
            provider.get_new_emails.assert_not_awaited()
            provider.mark_as_processed.assert_not_awaited()
            mark_processed.assert_not_called()
            analyze.assert_not_awaited()
            send_card.assert_not_awaited()
            self.assertEqual(EmailDedup(Path(temp_dir) / "processed.json").count(), before_count)

    async def test_formatted_diagnostics_never_include_body_full_id_or_token_secrets(self):
        body_secret = "PRIVATE_BODY_TEXT_9f73"
        full_message_id = "18f1234567890abcdef-full-gmail-id"
        access_token = "SYNTHETIC_ACCESS_TOKEN_MUST_STAY_SECRET"
        refresh_token = "SYNTHETIC_REFRESH_TOKEN_MUST_STAY_SECRET"
        client_secret = "SYNTHETIC_CLIENT_SECRET_MUST_STAY_SECRET"
        diagnostic = SimpleNamespace(
            sender_display_name="Freelancehunt",
            sender_email="info@freelancehunt.com",
            subject="New project",
            date="Sun, 19 Jul 2026 10:00:00 +0300",
            platform="Freelancehunt",
            sender_matched=True,
            subject_matched=True,
            is_job_alert=True,
            body=body_secret,
            id=full_message_id,
            access_token=access_token,
            refresh_token=refresh_token,
            client_secret=client_secret,
        )

        output = "\n".join(self.format_results([diagnostic]))

        self.assertIn("info@freelancehunt.com", output)
        self.assertIn("New project", output)
        for forbidden in (
            body_secret,
            full_message_id,
            access_token,
            refresh_token,
            client_secret,
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, output)

        allowed_fields = {field.name for field in EmailMatchDiagnostic.__dataclass_fields__.values()}
        self.assertNotIn("body", allowed_fields)
        self.assertNotIn("id", allowed_fields)


if __name__ == "__main__":
    unittest.main(verbosity=2)
