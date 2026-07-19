"""Synthetic MIME extraction tests; no Gmail connection or credentials required."""

import base64
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.gmail_provider import EmailMessage, RealGmailProvider


def _b64(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")


def _headers() -> list[dict[str, str]]:
    return [
        {"name": "From", "value": "Freelancehunt <info@freelancehunt.com>"},
        {"name": "Subject", "value": "Підбірка вакансій «Synthetic»"},
        {"name": "Date", "value": "Sun, 19 Jul 2026 12:00:00 +0300"},
    ]


class TestEmailMessageCompatibility(unittest.TestCase):
    def test_structured_fields_have_backward_compatible_defaults(self):
        first = EmailMessage(
            id="synthetic-default-1",
            subject="Synthetic",
            sender="sender@example.invalid",
            body="Legacy body",
            received_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )
        second = EmailMessage(
            id="synthetic-default-2",
            subject="Synthetic",
            sender="sender@example.invalid",
            body="Legacy body",
            received_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
        )

        self.assertEqual(first.body, "Legacy body")
        self.assertEqual(first.text_body, "")
        self.assertEqual(first.html_body, "")
        self.assertEqual(first.links, [])
        first.links.append("https://example.invalid/safe")
        self.assertEqual(second.links, [], "links defaults must not share mutable state")


class TestGmailMimeExtraction(unittest.TestCase):
    def setUp(self):
        self.provider = RealGmailProvider("unused-credentials.json", "unused-token.json")

    def test_html_only_root_preserves_html_and_builds_safe_visible_body(self):
        html = """
        <html><head>
          <style>.hidden { display: none }</style>
          <script>window.syntheticSecret = 'must-not-survive'</script>
        </head><body>
          <h1>Synthetic digest</h1>
          <span style="display:none">Invisible tracking text</span>
          <a href="https://freelancehunt.com/ua/job/synthetic/900001.html?utm_source=email">
            Synthetic vacancy
          </a>
          <a href="javascript:alert('unsafe')">Unsafe script URL</a>
          <img src="data:image/gif;base64,AAAA" alt="tracking pixel">
        </body></html>
        """
        raw = {
            "id": "synthetic-html-only",
            "payload": {
                "mimeType": "text/html",
                "headers": _headers(),
                "body": {"data": _b64(html)},
            },
        }

        email = self.provider._parse_message(raw)

        self.assertIsNotNone(email)
        assert email is not None
        self.assertEqual(email.text_body, "")
        self.assertIn("Synthetic vacancy", email.html_body)
        self.assertIn("Synthetic vacancy", email.body)
        self.assertNotIn("window.syntheticSecret", email.html_body)
        self.assertNotIn("window.syntheticSecret", email.body)
        self.assertNotIn("Invisible tracking text", email.body)
        self.assertEqual(
            email.links,
            [
                "https://freelancehunt.com/ua/job/synthetic/900001.html?utm_source=email"
            ],
        )

    def test_nested_multipart_extracts_plain_html_and_ignores_attachment(self):
        plain = "Synthetic plain-text digest\nSecond line"
        html = (
            '<html><body><p>Synthetic HTML digest</p>'
            '<a href="https://freelancehunt.com/ua/job/nested/900002.html">Job</a>'
            "</body></html>"
        )
        raw = {
            "id": "synthetic-nested-mime",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": _headers(),
                "body": {},
                "parts": [
                    {
                        "mimeType": "multipart/alternative",
                        "body": {},
                        "parts": [
                            {"mimeType": "text/plain", "body": {"data": _b64(plain)}},
                            {"mimeType": "text/html", "body": {"data": _b64(html)}},
                        ],
                    },
                    {
                        "mimeType": "application/octet-stream",
                        "filename": "synthetic.bin",
                        "body": {"data": _b64("attachment must be ignored")},
                    },
                ],
            },
        }

        email = self.provider._parse_message(raw)

        self.assertIsNotNone(email)
        assert email is not None
        self.assertEqual(email.text_body, plain)
        self.assertIn("Synthetic HTML digest", email.html_body)
        self.assertEqual(email.body, plain)
        self.assertNotIn("attachment must be ignored", email.body)
        self.assertEqual(
            email.links,
            ["https://freelancehunt.com/ua/job/nested/900002.html"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
