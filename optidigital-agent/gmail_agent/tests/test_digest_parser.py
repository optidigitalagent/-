"""Freelancehunt digest parsing against anonymized nested-table fixtures."""

import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gmail_agent.digest_parser import parse_freelancehunt_digest
from gmail_agent.gmail_provider import EmailMessage
from gmail_agent.tests.digest_fixtures import (
    DIGEST_ONE_JOB_HTML,
    DIGEST_TWO_JOBS_HTML,
    digest_with_job_count,
)


def _email(email_id: str, html: str) -> EmailMessage:
    return EmailMessage(
        id=email_id,
        sender="Freelancehunt <info@freelancehunt.com>",
        subject="Підбірка вакансій «Synthetic» за 19 липня",
        body="Synthetic digest",
        text_body="",
        html_body=html,
        received_at=datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
    )


def _project_card(url: str, title: str) -> str:
    """Return the smallest audited-shape card needed by the parser contract."""

    return f"""
    <table class="job-card">
      <tr>
        <td>
          <a href="{url}">{title}</a>
          <span class="budget">1 000 USD</span>
        </td>
      </tr>
      <tr><td>Safe synthetic project description.</td></tr>
    </table>
    """


class TestFreelancehuntDigestParser(unittest.TestCase):
    def test_strict_project_urls_are_normalized_and_non_projects_are_excluded(self):
        html = "".join(
            [
                _project_card(
                    "https://freelancehunt.com/project/synthetic-api/910001.html"
                    "?utm_source=email&amp;utm_campaign=digest#details",
                    "Synthetic API project",
                ),
                _project_card(
                    "https://www.freelancehunt.com/ua/project/synthetic-bot/910002.html"
                    "?utm_medium=email",
                    "Synthetic bot project",
                ),
                _project_card(
                    "https://freelancehunt.com/projects", "Projects category"
                ),
                _project_card(
                    "https://freelancehunt.com/ua/projects/programming",
                    "Programming category",
                ),
                _project_card("https://freelancehunt.com/", "Platform root"),
                _project_card(
                    "https://example.invalid/project/lookalike/910003.html",
                    "Other host lookalike",
                ),
                _project_card(
                    "https://freelancehunt.com/project/missing-id.html",
                    "Malformed project path",
                ),
                _project_card(
                    "https://freelancehunt.com/project/extra/910004.html/more",
                    "Project path with suffix",
                ),
            ]
        )

        candidates = parse_freelancehunt_digest(
            _email("synthetic-project-paths", html)
        )

        self.assertEqual(
            [candidate.url for candidate in candidates],
            [
                "https://freelancehunt.com/project/synthetic-api/910001.html",
                "https://freelancehunt.com/ua/project/synthetic-bot/910002.html",
            ],
        )
        self.assertEqual(
            [candidate.title for candidate in candidates],
            ["Synthetic API project", "Synthetic bot project"],
        )

    def test_audited_nested_tables_yield_two_individual_candidates(self):
        candidates = parse_freelancehunt_digest(
            _email("synthetic-digest-two", DIGEST_TWO_JOBS_HTML)
        )

        self.assertEqual(len(candidates), 2)
        first, second = candidates
        self.assertEqual(first.source_email_id, "synthetic-digest-two")
        self.assertEqual(first.platform, "Freelancehunt")
        self.assertEqual(first.title, "Synthetic Python automation")
        self.assertEqual(
            first.description,
            "Build an API integration for api.example.invalid.",
        )
        self.assertEqual(first.budget, "10 000 грн")
        self.assertEqual(
            first.url,
            "https://freelancehunt.com/ua/job/synthetic-python-automation/900001.html",
        )
        self.assertEqual(second.title, "Synthetic QA bot")
        self.assertEqual(
            second.description,
            "Test a notification bot against qa.example.invalid.",
        )
        self.assertEqual(second.budget, "")
        self.assertEqual(first.received_at, datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc))

    def test_category_unsubscribe_root_and_asset_links_are_not_candidates(self):
        candidates = parse_freelancehunt_digest(
            _email("synthetic-noise", DIGEST_TWO_JOBS_HTML)
        )

        urls = [candidate.url for candidate in candidates]
        self.assertEqual(len(urls), 2)
        for url in urls:
            self.assertRegex(url, r"^https://freelancehunt\.com/ua/job/.+/\d+\.html$")
            self.assertNotIn("unsubscribe", url)
            self.assertNotIn("/ua/jobs/", url)
            self.assertNotIn("assets.example.invalid", url)
        self.assertNotIn("https://freelancehunt.com/", urls)

    def test_tracking_query_and_fragment_are_removed_before_stable_keying(self):
        first_digest = parse_freelancehunt_digest(
            _email("synthetic-first", DIGEST_TWO_JOBS_HTML)
        )
        second_digest = parse_freelancehunt_digest(
            _email("synthetic-second", DIGEST_ONE_JOB_HTML)
        )

        self.assertEqual(len(second_digest), 1)
        self.assertEqual(first_digest[0].url, second_digest[0].url)
        self.assertNotIn("?", first_digest[0].url)
        self.assertNotIn("#", first_digest[0].url)
        self.assertEqual(first_digest[0].stable_key, second_digest[0].stable_key)

    def test_each_candidate_has_a_distinct_sha256_stable_key(self):
        candidates = parse_freelancehunt_digest(
            _email("synthetic-stable-keys", DIGEST_TWO_JOBS_HTML)
        )

        keys = [candidate.stable_key for candidate in candidates]
        self.assertEqual(len(set(keys)), 2)
        for key in keys:
            self.assertIsNotNone(re.fullmatch(r"[0-9a-f]{64}", key))

    def test_default_candidate_limit_is_twenty(self):
        email = _email("synthetic-cap", digest_with_job_count(25))

        candidates = parse_freelancehunt_digest(email)

        self.assertEqual(len(candidates), 20)
        self.assertEqual(candidates[0].title, "Synthetic job 01")
        self.assertEqual(candidates[-1].title, "Synthetic job 20")

    def test_explicit_candidate_limit_is_honored(self):
        email = _email("synthetic-custom-cap", digest_with_job_count(8))

        candidates = parse_freelancehunt_digest(email, max_candidates=3)

        self.assertEqual([item.title for item in candidates], [
            "Synthetic job 01",
            "Synthetic job 02",
            "Synthetic job 03",
        ])


if __name__ == "__main__":
    unittest.main(verbosity=2)
