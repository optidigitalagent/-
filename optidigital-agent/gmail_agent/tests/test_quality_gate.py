"""Stage 4 deterministic proposal-quality contracts.

All records, model results and Telegram calls are synthetic.  No network,
production database, client message or platform action is used.
"""

from __future__ import annotations

import ast
import json
import math
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.digest_parser import DigestJobCandidate
from gmail_agent.email_analyzer import JobAnalysis, analyze_email
from gmail_agent.email_classifier import EmailType
from gmail_agent.live_status import LiveStatus, LiveStatusResult
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.quality_gate import (
    ANALYSIS_VERSION,
    EVIDENCE_REGISTRY,
    PROPOSAL_READY_QUALITY_STATUSES,
    QualityStatus,
    apply_validation,
    finite_score,
    is_proposal_ready,
    proposal_version,
    validate_analysis,
)
from gmail_agent.storage import InMemoryGmailRepository, StoredGmailJob
from gmail_agent.telegram_notifier import (
    TELEGRAM_TEXT_LIMIT,
    format_job_card_parts,
    format_quality_review_card,
)


NOW = datetime.now(timezone.utc)
URL = "https://freelancehunt.com/project/synthetic-crm/1900001.html"
ROOT = Path(__file__).resolve().parents[2]


def _analysis(**overrides) -> JobAnalysis:
    values = {
        "email_id": "freelancehunt:1900001",
        "source_email_id": "rss:1900001",
        "is_relevant": True,
        "title": "CRM integration and Telegram reporting",
        "platform": "Freelancehunt",
        "score": 8.4,
        "fit_score": 7.1,
        "reason": "Commercially bounded integration with useful strategic value.",
        "budget": "1200 USD",
        "url": URL,
        "urgency": "medium",
        "why_relevant": "The source requires CRM integration and Telegram reporting.",
        "event_type": EmailType.PROJECT_FEED.value,
        "full_description": "Build a CRM integration and Telegram reporting workflow.",
        "description_completeness": "FULL",
        "language": "en",
        "service_lane": "CRM and automation",
        "executable": "yes",
        "win_probability_signal": "medium — clear scope",
        "scope_clarity": "high — explicit workflow",
        "estimated_effort": "24-32 hours",
        "delivery_risk": "CRM API access must be confirmed.",
        "client_payment_risk": "Not enough data; use one funded milestone.",
        "project_mode": "CASH",
        "project_mode_reason": "A bounded paid integration.",
        "recommended_price": "1200 USD as one milestone",
        "realistic_timeline": "5 days",
        "evidence_case_id": "GMAIL_JOB_AGENT",
        "evidence": "The source explicitly requests CRM and Telegram integration.",
        "proposal_draft": (
            "We can deliver the CRM integration and Telegram reporting workflow "
            "with API mapping, implementation and verification."
        ),
        "next_action": "Review and submit the proposal manually.",
        "live_status": LiveStatus.ACTIVE_BIDDABLE.value,
        "live_status_checked_at": NOW,
        "live_status_evidence": "Synthetic enabled bid form.",
        "biddable": True,
        "analysis_version": ANALYSIS_VERSION,
    }
    values.update(overrides)
    return JobAnalysis(**values)


def _validated(**overrides) -> JobAnalysis:
    analysis = _analysis(**overrides)
    apply_validation(analysis, validate_analysis(analysis))
    return analysis


def _job(**overrides) -> StoredGmailJob:
    analysis = _validated()
    values = {
        "stable_key": analysis.email_id,
        "source_email_id": analysis.source_email_id,
        "platform": analysis.platform,
        "title": analysis.title,
        "score": analysis.score,
        "reason": analysis.reason,
        "budget": analysis.budget,
        "url": analysis.url,
        "urgency": analysis.urgency,
        "why_relevant": analysis.why_relevant,
        "status": "queued",
        **GmailJobProcessor._analysis_fields(analysis),
    }
    values.update(overrides)
    return StoredGmailJob(**values)


class StaticActiveChecker:
    async def check(self, _url: str) -> LiveStatusResult:
        return LiveStatusResult(
            status=LiveStatus.ACTIVE_BIDDABLE,
            checked_at=datetime.now(timezone.utc),
            evidence="Synthetic enabled bid form.",
            biddable=True,
        )


class TestScoreAndFitParsing(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _client(payload: dict) -> MagicMock:
        choice = MagicMock()
        choice.message.content = json.dumps(payload)
        response = MagicMock(choices=[choice])
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=response)
        return client

    async def test_missing_fit_with_valid_score_stays_missing(self):
        result = await analyze_email(
            "x", "CRM project", "Freelancehunt", "Build CRM", client=self._client({"score": 8, "is_relevant": True})
        )
        self.assertEqual(result.score, 8.0)
        self.assertIsNone(result.fit_score)

    async def test_null_fit_with_valid_score_stays_missing(self):
        result = await analyze_email(
            "x", "CRM project", "Freelancehunt", "Build CRM", client=self._client({"score": 7, "fit_score": None})
        )
        self.assertEqual(result.score, 7.0)
        self.assertIsNone(result.fit_score)

    async def test_both_missing_are_not_valid_zeroes(self):
        result = await analyze_email(
            "x", "CRM project", "Freelancehunt", "Build CRM", client=self._client({})
        )
        self.assertIsNone(result.score)
        self.assertIsNone(result.fit_score)

    def test_malformed_and_non_finite_values_are_invalid(self):
        for value in ("", "bad", None, math.nan, math.inf, -math.inf, -1, 11, True):
            with self.subTest(value=value):
                self.assertIsNone(finite_score(value))

    async def test_score_and_fit_remain_distinct(self):
        result = await analyze_email(
            "x", "CRM project", "Freelancehunt", "Build CRM",
            client=self._client({"score": 8.5, "fit_score": 6.25}),
        )
        self.assertEqual(result.score, 8.5)
        self.assertEqual(result.fit_score, 6.25)


class TestDeterministicQualityValidator(unittest.TestCase):
    def assert_error(self, code: str, **overrides) -> None:
        self.assertIn(code, validate_analysis(_analysis(**overrides)).errors)

    def test_complete_active_analysis_is_valid(self):
        result = validate_analysis(_analysis())
        self.assertEqual(result.status, QualityStatus.VALID.value)
        self.assertFalse(result.errors)

    def test_relevant_executable_yes_with_zero_score_is_blocked(self):
        self.assert_error("score_zero_not_proposal_ready", score=0.0)
        self.assert_error("fit_score_zero_not_proposal_ready", fit_score=0.0)

    def test_missing_or_stale_live_check_is_blocked(self):
        self.assert_error("live_status_not_fresh", live_status_checked_at=None)
        self.assert_error(
            "live_status_not_fresh",
            live_status_checked_at=NOW.replace(year=2025),
        )

    def test_executable_no_with_zero_is_non_executable_diagnostic(self):
        analysis = _analysis(
            executable="no", is_relevant=False, score=0.0, fit_score=0.0,
            recommended_price="", realistic_timeline="", proposal_draft="",
            reason="The task cannot be delivered truthfully.",
        )
        result = validate_analysis(analysis)
        self.assertEqual(result.status, QualityStatus.NON_EXECUTABLE.value)
        apply_validation(analysis, result)
        self.assertFalse(analysis.qualified)
        self.assertFalse(analysis.proposal_draft)

    def test_missing_price_is_blocked(self):
        self.assert_error("recommended_price_missing_amount_or_currency", recommended_price="")

    def test_missing_timeline_is_blocked(self):
        self.assert_error("realistic_timeline_missing_or_unparseable", realistic_timeline="")

    def test_empty_proposal_is_blocked(self):
        self.assert_error("missing_proposal", proposal_draft="")

    def test_invalid_evidence_is_blocked(self):
        self.assert_error("invalid_evidence_case_id", evidence_case_id="INVENTED_CASE")

    def test_unsupported_claim_is_blocked(self):
        self.assert_error(
            "proposal_contains_unsupported_claim",
            proposal_draft="We have 12 years of experience delivering this CRM integration.",
        )
        self.assert_error(
            "analysis_evidence_not_source_grounded",
            evidence="The source explicitly requires quantum robotics.",
        )

    def test_external_contact_and_off_platform_cta_are_blocked(self):
        self.assert_error(
            "proposal_contains_external_contact",
            proposal_draft="We can deliver this CRM integration; email us at fake@example.invalid.",
        )
        self.assert_error(
            "proposal_contains_external_contact",
            proposal_draft="We can deliver this CRM integration; message @outside_user on Telegram.",
        )

    def test_partial_scope_requires_one_bounded_assumption_or_question(self):
        self.assert_error(
            "partial_scope_not_bounded",
            description_completeness="PARTIAL",
            proposal_draft="We can deliver the CRM integration and Telegram reporting workflow.",
        )
        result = validate_analysis(
            _analysis(
                description_completeness="PARTIAL",
                proposal_draft=(
                    "Assuming the published CRM scope is complete, we can deliver the "
                    "CRM integration and Telegram reporting workflow."
                ),
            )
        )
        self.assertNotIn("partial_scope_not_bounded", result.errors)

    def test_maybe_is_manual_review_with_exactly_one_conditioned_question(self):
        result = validate_analysis(
            _analysis(
                executable="maybe",
                description_completeness="PARTIAL",
                proposal_draft=(
                    "If API write access is available, we can deliver the CRM integration. "
                    "Can you confirm API write access?"
                ),
            )
        )
        self.assertEqual(result.status, QualityStatus.MANUAL_REVIEW.value)
        self.assertTrue(result.clarification_question.endswith("?"))

    def test_placeholder_and_multiple_owner_actions_are_blocked(self):
        self.assert_error(
            "proposal_contains_placeholder",
            proposal_draft="We can deliver [price] for the CRM integration.",
        )
        self.assert_error(
            "next_action_must_be_exactly_one",
            next_action="Review the proposal. Submit it manually.",
        )

    def test_language_must_match_declared_client_language(self):
        self.assert_error(
            "proposal_language_mismatch",
            language="uk",
            proposal_draft="We can deliver the CRM integration and Telegram reporting workflow.",
        )

    def test_budget_currency_and_effort_timeline_must_be_consistent(self):
        self.assert_error(
            "recommended_price_currency_conflicts_with_budget",
            budget="1200 USD",
            recommended_price="1200 EUR as one milestone",
        )
        self.assert_error(
            "effort_timeline_inconsistent",
            estimated_effort="80 hours",
            realistic_timeline="2 days",
        )

    def test_no_direct_case_cannot_claim_a_production_client_case(self):
        self.assert_error(
            "proposal_claims_unapproved_direct_case",
            evidence_case_id="NO_DIRECT_CASE",
            proposal_draft=(
                "Our production client case proves this CRM integration and "
                "Telegram reporting approach."
            ),
        )

    def test_registry_is_exact_and_complete(self):
        self.assertEqual(
            set(EVIDENCE_REGISTRY),
            {
                "BELLA_DENT", "DENTAL_SUPPLIER_AI_AGENT", "GMAIL_JOB_AGENT",
                "STATUS_DENT", "AMIDENTAL", "ART_STUDIO_184",
                "AUDIOBOOK_CLEANER", "MENTIUM", "NFC_REVIEW_CARDS",
                "NO_DIRECT_CASE", "DEMO_REQUIRED",
            },
        )
        self.assertTrue(all(EVIDENCE_REGISTRY.values()))

    def test_apply_validation_uses_registry_text_and_versions_proposal(self):
        analysis = _analysis(selected_evidence="model-owned free text")
        apply_validation(analysis, validate_analysis(analysis))
        self.assertEqual(analysis.selected_evidence, EVIDENCE_REGISTRY["GMAIL_JOB_AGENT"])
        self.assertIn(analysis.analysis_quality_status, PROPOSAL_READY_QUALITY_STATUSES)
        self.assertTrue(analysis.proposal_version.startswith("pqg-v1:"))
        self.assertTrue(is_proposal_ready(analysis))


class TestBoundedRepair(unittest.IsolatedAsyncioTestCase):
    def _processor(self) -> GmailJobProcessor:
        return GmailJobProcessor(object(), MagicMock(), 1, repository=InMemoryGmailRepository())

    async def test_one_repair_succeeds(self):
        processor = self._processor()
        invalid = _analysis(recommended_price="")
        repaired = _analysis()
        stats = ProcessorStats()
        with patch("gmail_agent.processor.repair_analysis", AsyncMock(return_value=repaired)) as call:
            result, provider_failed = await processor._validate_and_repair_quality(invalid, stats)
        self.assertFalse(provider_failed)
        self.assertEqual(result.analysis_quality_status, QualityStatus.REPAIRED.value)
        self.assertEqual(stats.repair_calls, 1)
        self.assertEqual(stats.repair_successes, 1)
        call.assert_awaited_once()

    async def test_one_repair_failure_becomes_manual_review(self):
        processor = self._processor()
        invalid = _analysis(recommended_price="")
        still_invalid = _analysis(recommended_price="")
        stats = ProcessorStats()
        with patch("gmail_agent.processor.repair_analysis", AsyncMock(return_value=still_invalid)) as call:
            result, provider_failed = await processor._validate_and_repair_quality(invalid, stats)
        self.assertFalse(provider_failed)
        self.assertEqual(result.analysis_quality_status, QualityStatus.MANUAL_REVIEW.value)
        self.assertEqual(result.quality_repair_count, 1)
        call.assert_awaited_once()

    async def test_provider_failure_is_retryable_not_valid_zero(self):
        processor = self._processor()
        invalid = _analysis(recommended_price="")
        failed = _analysis(
            analysis_succeeded=False, score=0.0, fit_score=0.0, proposal_draft=""
        )
        with patch("gmail_agent.processor.repair_analysis", AsyncMock(return_value=failed)) as call:
            result, provider_failed = await processor._validate_and_repair_quality(
                invalid, ProcessorStats()
            )
        self.assertTrue(provider_failed)
        self.assertEqual(result.analysis_quality_status, QualityStatus.FAILED.value)
        self.assertFalse(is_proposal_ready(result))
        call.assert_awaited_once()


class TestQualityPersistenceAndDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_quality_runs_after_live_status_and_before_send(self):
        events: list[str] = []

        class Checker:
            async def check(self, _url):
                events.append("live")
                return LiveStatusResult(
                    LiveStatus.ACTIVE_BIDDABLE,
                    datetime.now(timezone.utc),
                    "Synthetic enabled bid form.",
                    True,
                )

        candidate = DigestJobCandidate(
            source_email_id="rss:1900001",
            platform="Freelancehunt",
            title="CRM integration and Telegram reporting",
            description="Build a CRM integration and Telegram reporting workflow.",
            budget="1200 USD",
            url=URL,
            category="CRM",
            received_at=NOW,
            stable_key="freelancehunt:1900001",
            project_id="1900001",
            discovery_source="rss",
            event_type=EmailType.PROJECT_FEED.value,
            description_completeness="FULL",
        )

        async def analyze(*_args, **_kwargs):
            events.append("ai")
            return _analysis()

        async def send(*_args, **_kwargs):
            events.append("send")
            return True

        processor = GmailJobProcessor(
            object(), MagicMock(), 1,
            repository=InMemoryGmailRepository(),
            live_status_checker=Checker(),
            min_score=0.0,
        )
        original_validate = validate_analysis

        def tracked_validate(analysis, **kwargs):
            events.append("quality")
            return original_validate(analysis, **kwargs)

        with (
            patch("gmail_agent.processor.analyze_candidate", analyze),
            patch("gmail_agent.processor.validate_analysis", tracked_validate),
            patch("gmail_agent.processor.send_job_card", send),
        ):
            stats = await processor.run_candidates(
                [candidate], trigger="test", source_alias="synthetic"
            )
        self.assertEqual(events, ["live", "ai", "quality", "send"])
        self.assertEqual(stats.qualified, 1)

    async def test_storage_preserves_distinct_score_fit_and_quality_fields(self):
        repository = InMemoryGmailRepository()
        stored = await repository.save_job(_job())
        restarted = InMemoryGmailRepository(repository._state)
        loaded = await restarted.get_job(stored.stable_key)
        self.assertEqual((loaded.score, loaded.fit_score), (8.4, 7.1))
        self.assertEqual(loaded.analysis_quality_status, QualityStatus.VALID.value)
        self.assertTrue(loaded.proposal_version)

    async def test_thin_conflict_cannot_erase_a_valid_quality_package(self):
        repository = InMemoryGmailRepository()
        stored = await repository.save_job(_job())
        await repository.save_job(
            replace(
                stored,
                analysis_quality_status="",
                quality_checked_at=None,
                proposal_version="",
                proposal_draft="",
                recommended_price="",
                realistic_timeline="",
            )
        )
        loaded = await repository.get_job(stored.stable_key)
        self.assertEqual(loaded.analysis_quality_status, QualityStatus.VALID.value)
        self.assertEqual(loaded.proposal_version, stored.proposal_version)
        self.assertEqual(loaded.proposal_draft, stored.proposal_draft)
        self.assertEqual(loaded.recommended_price, stored.recommended_price)
        self.assertEqual(loaded.realistic_timeline, stored.realistic_timeline)

    async def test_proposal_version_dedup_blocks_repeat_send_after_restart(self):
        state: dict[str, object] = {}
        repository = InMemoryGmailRepository(state)
        job = await repository.save_job(_job())
        bot = MagicMock()
        processor = GmailJobProcessor(
            object(), bot, 1, repository=repository,
            live_status_checker=StaticActiveChecker(),
        )
        candidate = processor._candidate_from_job(job)
        with patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as send:
            first = ProcessorStats()
            await processor._send_stored_job(candidate, job, first, live_status_already_checked=True)
            restarted = GmailJobProcessor(
                object(), bot, 1, repository=InMemoryGmailRepository(state),
                live_status_checker=StaticActiveChecker(),
            )
            second = ProcessorStats()
            await restarted._send_stored_job(candidate, job, second, live_status_already_checked=True)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(first.proposal_versions_sent, 1)
        self.assertEqual(second.duplicates_skipped, 1)

    async def test_bounded_zero_score_backfill_preview_is_read_only(self):
        repository = InMemoryGmailRepository()
        for index in range(5):
            await repository.save_job(
                _job(
                    stable_key=f"legacy-{index}", score=0.0, fit_score=None,
                    analysis_quality_status="", recommended_price="",
                    realistic_timeline="", proposal_draft="", evidence_case_id="",
                )
            )
        before = dict(repository._state["jobs"])
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repository)
        preview = await processor.run_quality_backfill_preview(limit=3)
        self.assertEqual(preview.candidates, 3)
        self.assertEqual(preview.zero_score, 3)
        self.assertEqual(preview.missing_fit, 3)
        self.assertEqual(before, repository._state["jobs"])

    async def test_bounded_backfill_preserves_legacy_snapshot_without_sending(self):
        repository = InMemoryGmailRepository()
        for index in range(3):
            await repository.save_job(
                _job(
                    stable_key=f"legacy-execute-{index}",
                    score=0.0,
                    fit_score=None,
                    analysis_quality_status="",
                    proposal_version="",
                )
            )

        async def reanalyze(original, _errors, **_kwargs):
            return _analysis(
                email_id=original.email_id,
                source_email_id=original.source_email_id,
                url=original.url,
            )

        processor = GmailJobProcessor(
            object(), MagicMock(), 1,
            repository=repository,
            live_status_checker=StaticActiveChecker(),
        )
        repair = AsyncMock(side_effect=reanalyze)
        with (
            patch("gmail_agent.processor.repair_analysis", repair),
            patch("gmail_agent.processor.send_job_card", AsyncMock()) as send,
        ):
            stats = await processor.run_quality_backfill(
                limit=2,
                send_replacements=False,
            )

        self.assertEqual(repair.await_count, 2)
        self.assertEqual(stats.ai_analyzed, 2)
        send.assert_not_awaited()
        processed = [
            job for job in repository._state["jobs"].values()
            if job.status == "quality_validated_backfill"
        ]
        self.assertEqual(len(processed), 2)
        self.assertTrue(all('"score": 0.0' in job.original_analysis_snapshot for job in processed))
        self.assertEqual(
            sum(job.status != "quality_validated_backfill" for job in repository._state["jobs"].values()),
            1,
        )

    def test_proposal_version_is_stable_and_changes_with_proposal(self):
        first = _analysis()
        second = _analysis()
        third = _analysis(proposal_draft="We can deliver the CRM integration in a second bounded approach.")
        self.assertEqual(proposal_version(first), proposal_version(second))
        self.assertNotEqual(proposal_version(first), proposal_version(third))


class TestTelegramAndActionGuards(unittest.TestCase):
    def test_valid_card_is_html_safe_bounded_and_shows_distinct_scores(self):
        analysis = _validated(title="CRM <unsafe> integration")
        parts = format_job_card_parts(analysis)
        text = "\n".join(parts)
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in parts))
        self.assertIn("Analysis quality:</b> VALID", text)
        self.assertIn("Score:</b> 8.4/10", text)
        self.assertIn("Fit:</b> 7.1/10", text)
        self.assertIn("Evidence ID:</b> GMAIL_JOB_AGENT", text)
        self.assertNotIn("<unsafe>", text)
        self.assertIn("/reply_job", text)

    def test_repaired_card_is_visible_as_repaired(self):
        analysis = _analysis()
        apply_validation(analysis, validate_analysis(analysis, repaired=True), repair_count=1)
        self.assertIn("Analysis quality:</b> REPAIRED", "\n".join(format_job_card_parts(analysis)))

    def test_manual_review_card_has_no_proposal_or_reply_action(self):
        analysis = _analysis(recommended_price="")
        apply_validation(analysis, validate_analysis(analysis))
        text = format_quality_review_card(analysis)
        self.assertIn("QUALITY MANUAL REVIEW", text)
        self.assertIn("Usable proposal:</b> absent", text)
        self.assertIn("/quality_recheck", text)
        self.assertNotIn("/reply_job", text)
        self.assertNotIn("1200 USD", text)

    def test_every_freelancehunt_action_path_calls_quality_guard(self):
        source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {
            node.name: ast.unparse(node)
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in (
            "cb_view_response", "cb_send_manual", "cb_rewrite", "cmd_reply", "cmd_reply_job"
        ):
            with self.subTest(name=name):
                self.assertIn("_quality_allows_action", functions[name])

    def test_quality_recheck_is_admin_only_and_refreshes_live_before_one_ai_call(self):
        source = (ROOT / "bot" / "handlers.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        node = next(
            item for item in tree.body
            if isinstance(item, ast.AsyncFunctionDef) and item.name == "cmd_quality_recheck"
        )
        rendered = ast.unparse(node)
        self.assertIn("force=True", rendered)
        self.assertEqual(rendered.count("repair_analysis("), 1)
        decorator = ast.unparse(node.decorator_list[0])
        self.assertIn("admin_router", decorator)

    def test_migrations_are_additive_and_contain_every_quality_field(self):
        source = (ROOT / "db" / "models.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        migrations = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_MIGRATIONS" for target in node.targets)
        )
        quality_migrations = [statement for statement in migrations if "quality" in statement or "evidence_case_id" in statement or "proposal_version" in statement or "analysis_version" in statement]
        self.assertTrue(quality_migrations)
        self.assertTrue(all("ADD COLUMN IF NOT EXISTS" in statement for statement in quality_migrations))
        for field in (
            "analysis_quality_status", "quality_checked_at", "quality_errors",
            "quality_repair_count", "proposal_quality_score", "evidence_case_id",
            "analysis_version", "proposal_version",
        ):
            self.assertTrue(any(field in statement for statement in migrations), field)


if __name__ == "__main__":
    unittest.main()
