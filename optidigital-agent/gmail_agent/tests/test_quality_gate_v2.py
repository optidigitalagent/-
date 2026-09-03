"""Behavioral Stage 4 V2 blocker regressions; all inputs are synthetic."""

from __future__ import annotations

import ast
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.html_utils import escape_html, safe_http_url
from gmail_agent.digest_parser import DigestJobCandidate
from gmail_agent.email_analyzer import JobAnalysis, repair_analysis
from gmail_agent.email_classifier import EmailType
from gmail_agent.live_status import LiveStatus, LiveStatusResult
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.proposal_service import (
    ProposalGenerationStatus,
    generate_validate_and_persist_proposal,
)
from gmail_agent.quality_gate import (
    ANALYSIS_VERSION,
    APPLICATION_EVIDENCE_PREFIX,
    EVIDENCE_REGISTRY,
    SCORE_FAILED,
    SCORE_INVALID,
    SCORE_MISSING,
    SCORE_VALID,
    QualityStatus,
    apply_validation,
    is_proposal_ready,
    proposal_text_hash,
    validate_analysis,
)
from gmail_agent.storage import InMemoryGmailRepository, StoredGmailJob
from gmail_agent.telegram_notifier import (
    TELEGRAM_TEXT_LIMIT,
    format_quality_review_card_parts,
)


NOW = datetime.now(timezone.utc)
URL = "https://freelancehunt.com/project/synthetic-v2/1900002.html"
HANDLERS = Path(__file__).resolve().parents[2] / "bot" / "handlers.py"


def analysis(**overrides) -> JobAnalysis:
    values = dict(
        email_id="freelancehunt:1900002",
        source_email_id="rss:1900002",
        is_relevant=True,
        title="CRM integration and Telegram reporting",
        platform="Freelancehunt",
        score=8.0,
        score_valid=True,
        score_raw="8.0",
        score_state=SCORE_VALID,
        fit_score=7.0,
        fit_score_valid=True,
        fit_score_raw="7.0",
        fit_score_state=SCORE_VALID,
        reason="Bounded integration scope with milestone delivery.",
        budget="1000-1400 USD",
        url=URL,
        urgency="medium",
        why_relevant="The source asks for CRM integration and Telegram reporting.",
        event_type=EmailType.PROJECT_FEED.value,
        full_description="Build a CRM integration and Telegram reporting workflow.",
        description_completeness="FULL",
        language="en",
        category="CRM",
        service_lane="CRM and automation",
        executable="yes",
        win_probability_signal="medium — clear scope",
        scope_clarity="high — explicit workflow",
        estimated_effort="24-32 hours",
        delivery_risk="API access must be confirmed.",
        client_payment_risk="Use one funded milestone.",
        project_mode="CASH",
        project_mode_reason="The scope supports one bounded milestone.",
        recommended_price="1200 USD as one milestone",
        realistic_timeline="5 days",
        evidence_case_id="GMAIL_JOB_AGENT",
        evidence="The source asks for CRM integration and Telegram reporting.",
        proposal_draft="We can map the CRM API, implement the Telegram workflow, and verify the requested reporting.",
        next_action="Review and submit the proposal manually.",
        live_status=LiveStatus.ACTIVE_BIDDABLE.value,
        live_status_checked_at=NOW,
        live_status_evidence="Synthetic enabled bid form.",
        biddable=True,
        analysis_version=ANALYSIS_VERSION,
    )
    values.update(overrides)
    return JobAnalysis(**values)


def validated(**overrides) -> JobAnalysis:
    item = analysis(**overrides)
    decision = validate_analysis(item)
    apply_validation(item, decision)
    assert is_proposal_ready(item), decision.errors
    return item


def stored(**overrides) -> StoredGmailJob:
    item = validated()
    candidate = DigestJobCandidate(
        source_email_id=item.source_email_id,
        platform=item.platform,
        title=item.title,
        description=item.full_description,
        budget=item.budget,
        url=item.url,
        category=item.category,
        received_at=NOW,
        stable_key=item.email_id,
        project_id="1900002",
        event_type=item.event_type,
        description_completeness="FULL",
        discovery_source="rss",
    )
    job = GmailJobProcessor._stored_job(candidate, item)
    return replace(job, **overrides)


class ActiveChecker:
    async def check(self, _url: str) -> LiveStatusResult:
        return LiveStatusResult(
            LiveStatus.ACTIVE_BIDDABLE,
            datetime.now(timezone.utc),
            "Synthetic enabled bid form.",
            True,
        )


class StaticChecker:
    def __init__(self, status: LiveStatus):
        self.status = status

    async def check(self, _url: str) -> LiveStatusResult:
        return LiveStatusResult(
            self.status,
            datetime.now(timezone.utc),
            f"Synthetic {self.status.value}",
            self.status == LiveStatus.ACTIVE_BIDDABLE,
        )


class TestGeneratedProposalGate(unittest.IsolatedAsyncioTestCase):
    async def _run(self, candidates: list[str]):
        source = validated()
        persisted = []
        generator = AsyncMock(side_effect=candidates)

        async def refresh(item):
            item.live_status_checked_at = datetime.now(timezone.utc)
            return item

        async def persist(item, status):
            persisted.append((replace(item), status))

        result = await generate_validate_and_persist_proposal(
            source,
            refresh_live_status=refresh,
            generate_candidate=generator,
            persist=persist,
        )
        return result, persisted, generator

    async def test_valid_parent_unsafe_email_rewrite_is_blocked(self):
        unsafe = "We can implement the CRM workflow; email me at fake@example.invalid."
        result, persisted, generator = await self._run([unsafe, unsafe])
        self.assertEqual(result.status, ProposalGenerationStatus.MANUAL_REVIEW.value)
        self.assertEqual(generator.await_count, 2)
        self.assertFalse(persisted[-1][0].proposal_draft)

    async def test_valid_parent_invented_claim_rewrite_is_blocked(self):
        unsafe = "We built an advanced AI CRM and can implement this reporting workflow."
        result, _, _ = await self._run([unsafe, unsafe])
        self.assertEqual(result.status, ProposalGenerationStatus.MANUAL_REVIEW.value)

    async def test_valid_parent_wrong_language_rewrite_is_blocked(self):
        source = validated(language="uk", proposal_draft="Можемо реалізувати інтеграцію CRM і Telegram-звітність.")
        persisted = []

        async def refresh(item):
            item.live_status_checked_at = datetime.now(timezone.utc)
            return item

        async def persist(item, status):
            persisted.append((item, status))

        wrong = AsyncMock(return_value="We can implement the CRM integration and reporting workflow.")
        result = await generate_validate_and_persist_proposal(
            source, refresh_live_status=refresh, generate_candidate=wrong, persist=persist
        )
        self.assertEqual(result.status, ProposalGenerationStatus.MANUAL_REVIEW.value)

    async def test_price_and_timeline_conflicts_are_blocked(self):
        for unsafe in (
            "We can implement the CRM workflow for 800 EUR.",
            "We can implement the CRM workflow in 2 weeks.",
        ):
            with self.subTest(unsafe=unsafe):
                result, _, _ = await self._run([unsafe, unsafe])
                self.assertEqual(result.status, ProposalGenerationStatus.MANUAL_REVIEW.value)

    async def test_valid_rewrite_gets_new_version_and_application_clauses(self):
        result, persisted, _ = await self._run([
            "We can map the CRM API, implement Telegram reporting, and verify the requested workflow."
        ])
        self.assertEqual(result.status, ProposalGenerationStatus.VALIDATED_PROPOSAL.value)
        self.assertNotEqual(result.analysis.proposal_version, validated().proposal_version)
        self.assertIn(APPLICATION_EVIDENCE_PREFIX, result.analysis.proposal_draft)
        self.assertIn(EVIDENCE_REGISTRY["GMAIL_JOB_AGENT"], result.analysis.proposal_draft)
        self.assertEqual(persisted[-1][1], "queued")

    async def test_provider_failure_never_exposes_a_draft(self):
        result, persisted, _ = await self._run([""])
        self.assertEqual(result.status, ProposalGenerationStatus.PROVIDER_RETRYABLE.value)
        self.assertFalse(result.analysis.proposal_draft)
        self.assertFalse(persisted[-1][0].proposal_draft)


class TestEvidenceAndCommercialAdversaries(unittest.TestCase):
    def assert_blocked(self, proposal: str, **overrides):
        item = analysis(proposal_draft=proposal, **overrides)
        self.assertFalse(validate_analysis(item).proposal_ready)

    def test_valid_bella_id_with_invented_ai_crm_claim(self):
        self.assert_blocked(
            "Our Bella Dent project included an AI CRM for this workflow.",
            evidence_case_id="BELLA_DENT",
        )

    def test_invented_capability_without_numbers(self):
        self.assert_blocked("We built an advanced predictive analytics platform for clients.")

    def test_another_case_than_selected(self):
        self.assert_blocked("The Bella Dent case proves this reporting workflow.")

    def test_structured_price_and_timeline_contradictions(self):
        price = validate_analysis(analysis(proposal_draft="We can deliver the CRM workflow for 800 EUR."))
        timeline = validate_analysis(analysis(proposal_draft="We can deliver the CRM workflow in 2 weeks."))
        self.assertIn("proposal_price_conflicts_with_recommended_price", price.errors)
        self.assertIn("proposal_timeline_conflicts_with_realistic_timeline", timeline.errors)

    def test_range_currency_milestone_and_timeline_unit_are_checked(self):
        cases = (
            (
                analysis(
                    recommended_price="1000-1200 USD as two milestones",
                    proposal_draft="We can deliver this CRM workflow for 1000-1100 USD.",
                ),
                "proposal_price_conflicts_with_recommended_price",
            ),
            (
                analysis(proposal_draft="We can deliver this CRM workflow in two milestones."),
                "proposal_milestone_logic_conflicts_with_recommended_price",
            ),
            (
                analysis(
                    realistic_timeline="4-5 days",
                    proposal_draft="We can deliver this CRM workflow in 4-5 weeks.",
                ),
                "proposal_timeline_conflicts_with_realistic_timeline",
            ),
        )
        for item, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, validate_analysis(item).errors)

    def test_no_direct_case_cannot_be_completed_work(self):
        self.assert_blocked(
            "Our team built this exact CRM workflow for a production client.",
            evidence_case_id="NO_DIRECT_CASE",
        )

    def test_exact_application_injected_clause_passes_after_reload(self):
        item = validated()
        self.assertEqual(validate_analysis(item).status, QualityStatus.VALID.value)
        self.assertEqual(item.proposal_draft.count(EVIDENCE_REGISTRY["GMAIL_JOB_AGENT"]), 1)

    def test_tampered_text_cannot_reuse_a_valid_proposal_version(self):
        item = validated()
        item.proposal_draft += " Tampered after validation."
        self.assertFalse(is_proposal_ready(item))

    def test_price_far_outside_budget_requires_rationale(self):
        item = analysis(
            budget="100-200 USD",
            recommended_price="1200 USD as one milestone",
            reason="Potential project.",
            project_mode_reason="Potential cash work.",
        )
        self.assertIn("price_outside_budget_requires_rationale", validate_analysis(item).errors)


def _load_response_handler():
    tree = ast.parse(HANDLERS.read_text(encoding="utf-8"), str(HANDLERS))
    definitions = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    names = {"cb_send_manual", "_response_draft_errors", "_value"}
    nodes = [definitions[name] for name in names]
    for node in nodes:
        node.decorator_list = []
    namespace = dict(
        CallbackQuery=object,
        ResponseCb=object,
        Response=object(),
        Order=object(),
        datetime=datetime,
        timezone=timezone,
        escape_html=escape_html,
        safe_http_url=safe_http_url,
        _ensure_order_current_biddable=AsyncMock(
            return_value=SimpleNamespace(allowed=True)
        ),
        _quality_allows_action=lambda _record: True,
        _live_status_refusal=lambda *_args: "live blocked",
        _quality_refusal=lambda *_args: "quality blocked",
        update_order_status=AsyncMock(),
    )
    exec(compile(ast.Module(nodes, []), str(HANDLERS), "exec"), namespace)
    return namespace["cb_send_manual"]


class TestExactResponseDraftProtection(unittest.IsolatedAsyncioTestCase):
    async def _invoke(self, draft):
        order = SimpleNamespace(
            id=42,
            url=URL,
            proposal_version="pqg-v2:current",
            analysis_version=ANALYSIS_VERSION,
            live_status_checked_at=NOW,
        )
        session = MagicMock()
        session.get = AsyncMock(
            side_effect=lambda model, _id, **_kwargs: draft if _id == 8 else order
        )
        session.commit = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        handler = _load_response_handler()
        handler.__globals__["AsyncSessionLocal"] = MagicMock(return_value=context)
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.message.edit_text = AsyncMock()
        callback.message.answer = AsyncMock()
        await handler(callback, SimpleNamespace(response_id=8, order_id=42))
        return callback, draft

    async def test_cb_send_manual_refuses_unversioned_response(self):
        draft = SimpleNamespace(
            id=8, text="unsafe", result="draft", proposal_version="",
            analysis_quality_status=QualityStatus.VALID.value,
            quality_checked_at=NOW, source_job_identity="order:42",
            validated_live_status_at=NOW,
        )
        callback, _ = await self._invoke(draft)
        callback.message.answer.assert_not_awaited()
        self.assertEqual(draft.result, "draft")

    async def test_cb_send_manual_refuses_mismatched_version(self):
        draft = SimpleNamespace(
            id=8, text="unsafe", result="draft", proposal_version="pqg-v2:other",
            proposal_content_sha256=proposal_text_hash("unsafe"),
            analysis_quality_status=QualityStatus.VALID.value,
            quality_checked_at=NOW, source_job_identity="order:42",
            validated_live_status_at=NOW,
        )
        callback, _ = await self._invoke(draft)
        callback.message.answer.assert_not_awaited()
        self.assertEqual(draft.result, "draft")

    async def test_cb_send_manual_refuses_text_changed_after_validation(self):
        draft = SimpleNamespace(
            id=8,
            text="tampered",
            result="draft",
            proposal_version="pqg-v2:current",
            proposal_content_sha256=proposal_text_hash("original"),
            analysis_quality_status=QualityStatus.VALID.value,
            quality_checked_at=NOW,
            source_job_identity="order:42",
            validated_live_status_at=NOW,
        )
        callback, _ = await self._invoke(draft)
        callback.message.answer.assert_not_awaited()
        self.assertEqual(draft.result, "draft")


class TestRepairInputAndImmutability(unittest.IsolatedAsyncioTestCase):
    async def test_full_original_package_errors_evidence_and_source_reach_repair_prompt(self):
        original = analysis(model_output_json='{"sentinel":"original-package"}')
        choice = MagicMock()
        choice.message.content = json.dumps({})
        completion = MagicMock(choices=[choice])
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=completion)

        await repair_analysis(
            original,
            ["proposal_language_mismatch", "proposal_price_conflict"],
            client=client,
        )

        prompt = client.chat.completions.create.await_args.kwargs["messages"][1]["content"]
        self.assertIn('"sentinel":"original-package"', prompt)
        self.assertIn("Normalized original analysis", prompt)
        self.assertIn("proposal_language_mismatch", prompt)
        self.assertIn(EVIDENCE_REGISTRY["GMAIL_JOB_AGENT"], prompt)
        self.assertIn(original.full_description, prompt)

    async def test_repair_cannot_change_source_language_budget_evidence_or_live_status(self):
        original = analysis()
        model_repair = analysis(
            title="Invented title",
            language="ru",
            budget="9999 EUR",
            evidence_case_id="BELLA_DENT",
            selected_evidence="invented",
            live_status=LiveStatus.CLOSED.value,
            live_status_evidence="invented",
            biddable=False,
        )
        with patch(
            "gmail_agent.email_analyzer.analyze_email",
            AsyncMock(return_value=model_repair),
        ):
            repaired = await repair_analysis(
                original, ["proposal_language_mismatch"], client=object()
            )
        for field_name in (
            "title",
            "language",
            "budget",
            "evidence_case_id",
            "live_status",
            "live_status_evidence",
            "biddable",
        ):
            self.assertEqual(getattr(repaired, field_name), getattr(original, field_name))
        self.assertEqual(
            repaired.selected_evidence,
            EVIDENCE_REGISTRY[original.evidence_case_id],
        )


class TestScoreSemantics(unittest.IsolatedAsyncioTestCase):
    async def _roundtrip(self, item: JobAnalysis):
        repository = InMemoryGmailRepository()
        candidate = GmailJobProcessor._candidate_from_job(stored())
        saved = await repository.save_job(GmailJobProcessor._stored_job(candidate, item))
        restarted = InMemoryGmailRepository(repository._state)
        return GmailJobProcessor._analysis_from_job(await restarted.get_job(saved.stable_key))

    async def test_none_remains_missing(self):
        loaded = await self._roundtrip(analysis(score=None, score_valid=False, score_raw="", score_state=SCORE_MISSING))
        self.assertEqual((loaded.score_state, loaded.score_display), (SCORE_MISSING, "—"))

    async def test_malformed_remains_invalid(self):
        loaded = await self._roundtrip(analysis(score=None, score_valid=False, score_raw="bad", score_state=SCORE_INVALID))
        self.assertEqual((loaded.score_state, loaded.score_display), (SCORE_INVALID, "INVALID"))

    async def test_real_zero_remains_real_zero(self):
        loaded = await self._roundtrip(analysis(score=0.0, score_valid=True, score_raw="0", score_state=SCORE_VALID))
        self.assertEqual((loaded.score_state, loaded.score_display), (SCORE_VALID, "0.0/10"))
        self.assertFalse(is_proposal_ready(loaded))

    async def test_provider_failure_displays_failed(self):
        loaded = await self._roundtrip(analysis(analysis_succeeded=False, score=0.0, score_valid=False, score_raw="", score_state=SCORE_FAILED))
        self.assertEqual(loaded.score_display, "FAILED")

    async def test_backfill_counts_missing_invalid_and_real_zero_separately(self):
        repo = InMemoryGmailRepository()
        for key, state, valid, raw, value in (
            ("missing", SCORE_MISSING, False, "", None),
            ("invalid", SCORE_INVALID, False, "bad", None),
            ("zero", SCORE_VALID, True, "0", 0.0),
        ):
            await repo.save_job(stored(stable_key=key, score=value or 0.0, score_state=state, score_valid=valid, score_raw=raw, analysis_quality_status=""))
        preview = await GmailJobProcessor(object(), MagicMock(), 1, repository=repo).run_quality_backfill_preview(3)
        self.assertEqual((preview.missing_score, preview.invalid_score, preview.actual_zero_score), (1, 1, 1))


class TestBackfillAuditPreservation(unittest.IsolatedAsyncioTestCase):
    async def _run(self, status: LiveStatus, *, state=None):
        repo = InMemoryGmailRepository(state)
        if not state:
            await repo.save_job(stored(stable_key="legacy", analysis_quality_status="", proposal_version="", score_valid=False, score_state=SCORE_MISSING))
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=StaticChecker(status))
        await processor.run_quality_backfill(1)
        return repo, await repo.get_job("legacy")

    async def test_active_to_unknown_keeps_snapshot_and_pending_state(self):
        _, job = await self._run(LiveStatus.LIVE_STATUS_UNKNOWN)
        self.assertTrue(job.original_analysis_snapshot)
        self.assertFalse(job.proposal_draft)
        self.assertEqual(job.status, "live_status_pending")

    async def test_active_to_blocked_keeps_snapshot_and_hides_current(self):
        _, job = await self._run(LiveStatus.BLOCKED_RULE_VIOLATION)
        self.assertTrue(job.original_analysis_snapshot)
        self.assertFalse(job.proposal_draft)
        self.assertEqual(job.status, "live_status_terminal")

    async def test_restart_keeps_snapshot(self):
        repo, job = await self._run(LiveStatus.BLOCKED_RULE_VIOLATION)
        restarted = InMemoryGmailRepository(repo._state)
        loaded = await restarted.get_job(job.stable_key)
        self.assertEqual(loaded.original_analysis_snapshot, job.original_analysis_snapshot)

    async def test_update_failure_before_snapshot_leaves_original_untouched(self):
        class FailingRepo(InMemoryGmailRepository):
            async def apply_backfill_live_result(self, *_args, **_kwargs):
                raise RuntimeError("synthetic transaction failure")

        repo = FailingRepo()
        original = await repo.save_job(stored(stable_key="legacy", analysis_quality_status="", proposal_version="", score_valid=False, score_state=SCORE_MISSING))
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=StaticChecker(LiveStatus.CLOSED))
        await processor.run_quality_backfill(1)
        loaded = await repo.get_job("legacy")
        self.assertEqual(loaded.proposal_draft, original.proposal_draft)
        self.assertFalse(loaded.original_analysis_snapshot)

    async def test_manual_delivery_never_exposes_blocked_snapshot(self):
        repo, _ = await self._run(LiveStatus.BLOCKED_RULE_VIOLATION)
        send = AsyncMock(return_value=True)
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=StaticChecker(LiveStatus.BLOCKED_RULE_VIOLATION))
        self.assertFalse(await processor.deliver_validated_proposal_text_version("legacy", send))
        send.assert_not_awaited()


class TestUnifiedVersionDelivery(unittest.IsolatedAsyncioTestCase):
    async def test_quality_recheck_same_version_twice_sends_one_card(self):
        repo = InMemoryGmailRepository()
        await repo.save_job(stored())
        processor = GmailJobProcessor(
            object(), MagicMock(), 1, repository=repo,
            live_status_checker=ActiveChecker(),
        )
        with (
            patch(
                "gmail_agent.processor.repair_analysis",
                AsyncMock(side_effect=lambda *_args, **_kwargs: analysis()),
            ),
            patch(
                "gmail_agent.processor.send_job_card", AsyncMock(return_value=True)
            ) as send,
        ):
            _, first = await processor.recheck_quality_and_deliver(
                "freelancehunt:1900002"
            )
            _, second = await processor.recheck_quality_and_deliver(
                "freelancehunt:1900002"
            )
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(send.await_count, 1)

    async def test_quality_recheck_then_real_backfill_does_not_repeat_version(self):
        repo = InMemoryGmailRepository()
        await repo.save_job(stored())
        processor = GmailJobProcessor(
            object(), MagicMock(), 1, repository=repo,
            live_status_checker=ActiveChecker(),
        )
        with (
            patch(
                "gmail_agent.processor.repair_analysis",
                AsyncMock(side_effect=lambda *_args, **_kwargs: analysis()),
            ),
            patch(
                "gmail_agent.processor.send_job_card", AsyncMock(return_value=True)
            ) as send,
        ):
            await processor.recheck_quality_and_deliver("freelancehunt:1900002")
            await repo.update_job_fields(
                "freelancehunt:1900002",
                {"analysis_quality_status": "", "status": "queued"},
            )
            await processor.run_quality_backfill(1, send_replacements=True)
        self.assertEqual(send.await_count, 1)

    async def test_same_version_explicit_manual_retrieval_repeats_after_restart(self):
        state = {}
        repo = InMemoryGmailRepository(state)
        await repo.save_job(stored())
        send = AsyncMock(return_value=True)
        first = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        self.assertTrue(await first.deliver_validated_proposal_text_version("freelancehunt:1900002", send, live_status_already_checked=True))
        restarted = GmailJobProcessor(object(), MagicMock(), 1, repository=InMemoryGmailRepository(state), live_status_checker=ActiveChecker())
        self.assertTrue(await restarted.deliver_validated_proposal_text_version("freelancehunt:1900002", send, live_status_already_checked=True))
        self.assertEqual(send.await_count, 2)

    async def test_false_send_retries_to_one_eventual_delivery(self):
        repo = InMemoryGmailRepository()
        await repo.save_job(stored())
        send = AsyncMock(side_effect=[False, True])
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        self.assertFalse(await processor.deliver_validated_proposal_text_version("freelancehunt:1900002", send, live_status_already_checked=True))
        self.assertTrue(await processor.deliver_validated_proposal_text_version("freelancehunt:1900002", send, live_status_already_checked=True))
        self.assertEqual(send.await_count, 2)

    async def test_different_validated_version_delivers_once_more(self):
        repo = InMemoryGmailRepository()
        first_job = await repo.save_job(stored())
        send = AsyncMock(return_value=True)
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        await processor.deliver_validated_proposal_text_version(first_job.stable_key, send, live_status_already_checked=True)
        changed = validated(proposal_draft="We can map the CRM API and implement a second bounded reporting approach.")
        await repo.update_job_fields(first_job.stable_key, GmailJobProcessor._analysis_fields(changed))
        self.assertTrue(await processor.deliver_validated_proposal_text_version(first_job.stable_key, send, live_status_already_checked=True))
        self.assertEqual(send.await_count, 2)

    async def test_quality_recheck_then_backfill_same_card_version_no_duplicate(self):
        repo = InMemoryGmailRepository()
        job = await repo.save_job(stored())
        bot = MagicMock()
        processor = GmailJobProcessor(object(), bot, 1, repository=repo, live_status_checker=ActiveChecker())
        candidate = processor._candidate_from_job(job)
        with patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as send:
            await processor.deliver_validated_proposal_version(candidate, job, ProcessorStats(), live_status_already_checked=True)
            await repo.update_job_status(job.stable_key, "queued")
            latest = await repo.get_job(job.stable_key)
            await processor.deliver_validated_proposal_version(candidate, latest, ProcessorStats(), live_status_already_checked=True)
        self.assertEqual(send.await_count, 1)


class TestManualReviewMultipart(unittest.TestCase):
    def test_manual_review_contains_source_and_stays_html_safe(self):
        item = analysis(
            score=None,
            score_valid=False,
            score_state=SCORE_MISSING,
            fit_score=None,
            fit_score_valid=False,
            fit_score_state=SCORE_INVALID,
            fit_score_raw="bad",
            recommended_price="",
            full_description=("Requirement <unsafe> & complete context. " * 500),
        )
        apply_validation(item, validate_analysis(item))
        parts = format_quality_review_card_parts(item)
        text = "\n".join(parts)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in parts))
        self.assertIn("Повне безпечне ТЗ", text)
        self.assertIn("Score:</b> —", text)
        self.assertIn("Fit:</b> INVALID", text)
        self.assertIn("&lt;unsafe&gt; &amp;", text)
        self.assertNotIn("<unsafe>", text)
        self.assertIn("Usable proposal:</b> absent", text)


if __name__ == "__main__":
    unittest.main()
