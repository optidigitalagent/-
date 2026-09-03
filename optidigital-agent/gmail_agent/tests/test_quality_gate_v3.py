"""Stage 4 V3 localization, injection and delivery regressions."""

from __future__ import annotations

import ast
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

from gmail_agent.commercial_terms import (
    Currency,
    MoneyTerms,
    PricingMode,
    TimelineTerms,
    TimelineUnit,
    parse_money_terms,
    parse_timeline_terms,
)
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.quality_gate import (
    APPLICATION_COMMERCIAL_PREFIXES,
    APPLICATION_EVIDENCE_PREFIXES,
    EVIDENCE_REGISTRY,
    apply_validation,
    final_composed_proposal_errors,
    is_proposal_ready,
    proposal_text_hash,
    proposal_version,
    validate_analysis,
)
from gmail_agent.storage import (
    DEFAULT_SENDING_LEASE,
    InMemoryGmailRepository,
)
from gmail_agent.tests.test_quality_gate_v2 import (
    ActiveChecker,
    _load_response_handler,
    analysis,
    stored,
    validated,
)

HANDLERS = Path(__file__).resolve().parents[2] / "bot" / "handlers.py"


class TestCanonicalCommercialTerms(unittest.TestCase):
    def test_valid_money_examples_are_typed(self):
        fixed = parse_money_terms("1200 USD")
        ranged = parse_money_terms("1000–1200 USD")
        milestone = parse_money_terms("1200 USD as one milestone")
        self.assertEqual(
            fixed,
            MoneyTerms(fixed.min_amount, fixed.max_amount, Currency.USD, PricingMode.FIXED, None),
        )
        self.assertEqual(ranged.pricing_mode, PricingMode.RANGE)
        self.assertEqual(milestone.milestone_count, 1)
        self.assertEqual(milestone.pricing_mode, PricingMode.MILESTONE)

    def test_valid_timeline_examples_are_typed(self):
        fixed = parse_timeline_terms("5 days")
        ranged = parse_timeline_terms("4–6 weeks")
        self.assertEqual(fixed, TimelineTerms(5, 5, TimelineUnit.DAYS))
        self.assertEqual(ranged, TimelineTerms(4, 6, TimelineUnit.WEEKS))

    def test_money_full_string_injection_and_contradictions_fail(self):
        attacks = (
            "1200 USD as one milestone; email fake@example.com",
            "1200 USD or 5000 EUR",
            "1200 USD, contact us on Discord",
            "1200 USD [price may change]",
            "one milestone and three milestones",
            "1000--1200 USD",
            "1200-1000 USD",
            "-5 USD",
            "0 USD",
            "999999999999999 USD",
        )
        for value in attacks:
            with self.subTest(value=value):
                self.assertIsNone(parse_money_terms(value))
                result = validate_analysis(analysis(recommended_price=value))
                self.assertIn("recommended_price_not_full_string_canonical", result.errors)

    def test_timeline_full_string_injection_and_contradictions_fail(self):
        attacks = (
            "5 days, maybe 2 weeks",
            "5 days; https://example.com",
            "5 days or 3 months",
            "4--6 weeks",
            "6-4 weeks",
            "-1 days",
            "0 days",
            "999999 days",
        )
        for value in attacks:
            with self.subTest(value=value):
                self.assertIsNone(parse_timeline_terms(value))
                result = validate_analysis(analysis(realistic_timeline=value))
                self.assertIn("realistic_timeline_not_full_string_canonical", result.errors)

    def test_ready_analysis_persists_canonical_json_not_raw_suffix(self):
        item = analysis(
            recommended_price="1 200 USD as one milestone",
            realistic_timeline="5 days",
        )
        apply_validation(item, validate_analysis(item))
        self.assertTrue(is_proposal_ready(item))
        money = json.loads(item.money_terms_json)
        timeline = json.loads(item.timeline_terms_json)
        self.assertEqual(
            set(money),
            {"min_amount", "max_amount", "currency", "pricing_mode", "milestone_count", "rationale_id"},
        )
        self.assertEqual(set(timeline), {"min_value", "max_value", "unit"})
        self.assertEqual(item.recommended_price, "1200 USD as one milestone")
        self.assertEqual(item.realistic_timeline, "5 days")
        self.assertNotIn("1 200 USD as one milestone", item.proposal_draft)

    def test_canonical_json_tampering_fails_reload(self):
        item = validated()
        item.money_terms_json = item.money_terms_json.replace('"USD"', '"EUR"')
        self.assertFalse(is_proposal_ready(item))
        self.assertIn(
            "money_terms_json_mismatch",
            final_composed_proposal_errors(item, item.proposal_draft),
        )

    def test_malformed_canonical_json_fails_closed_without_exception(self):
        attacks = (
            (
                "money_terms_json",
                '{"min_amount":NaN,"max_amount":1200,"currency":"USD","pricing_mode":"FIXED","milestone_count":null,"rationale_id":"MODEL_SCOPE_ESTIMATE"}',
            ),
            (
                "timeline_terms_json",
                '{"min_value":1.5,"max_value":5,"unit":"DAYS"}',
            ),
            (
                "timeline_terms_json",
                '{"min_value":true,"max_value":5,"unit":"DAYS"}',
            ),
        )
        for field_name, payload in attacks:
            with self.subTest(field_name=field_name, payload=payload):
                item = validated()
                setattr(item, field_name, payload)
                self.assertFalse(is_proposal_ready(item))


class TestLocalizedFinalComposition(unittest.TestCase):
    BODIES: ClassVar[dict[str, str]] = {
        "uk": "Можемо реалізувати інтеграцію CRM і Telegram та перевірити звітність для цього проєкту.",
        "ru": "Можем реализовать интеграцию CRM и Telegram и проверить отчётность для этого проекта.",
        "en": "We can implement the CRM and Telegram integration and verify the requested reporting.",
        "pl": "Możemy wdrożyć integrację CRM i Telegram oraz zweryfikować raportowanie dla tego projektu.",
    }

    def test_all_four_languages_have_application_owned_evidence_and_commercial_text(self):
        for language, body in self.BODIES.items():
            with self.subTest(language=language):
                item = analysis(language=language, proposal_draft=body)
                decision = validate_analysis(item)
                apply_validation(item, decision)
                self.assertTrue(is_proposal_ready(item), decision.errors)
                self.assertIn(APPLICATION_EVIDENCE_PREFIXES[language], item.proposal_draft)
                self.assertIn(APPLICATION_COMMERCIAL_PREFIXES[language], item.proposal_draft)
                self.assertIn(EVIDENCE_REGISTRY["GMAIL_JOB_AGENT"][language], item.proposal_draft)
                self.assertEqual(final_composed_proposal_errors(item, item.proposal_draft), ())

    def test_non_english_suffixes_have_no_english_service_sentences(self):
        forbidden = ("Approved evidence:", "Commercial terms:", "price —", "timeline —", "payment in")
        for language in ("uk", "ru", "pl"):
            item = analysis(language=language, proposal_draft=self.BODIES[language])
            apply_validation(item, validate_analysis(item))
            for phrase in forbidden:
                self.assertNotIn(phrase, item.proposal_draft)

    def test_no_direct_case_and_demo_required_are_localized(self):
        for case_id in ("NO_DIRECT_CASE", "DEMO_REQUIRED"):
            for language, body in self.BODIES.items():
                with self.subTest(case_id=case_id, language=language):
                    item = analysis(
                        language=language,
                        proposal_draft=body,
                        evidence_case_id=case_id,
                    )
                    apply_validation(item, validate_analysis(item))
                    self.assertTrue(is_proposal_ready(item))
                    self.assertIn(EVIDENCE_REGISTRY[case_id][language], item.proposal_draft)

    def test_proper_names_and_technologies_are_not_language_mismatches(self):
        body = "Можемо реалізувати Gmail API, PostgreSQL, Railway, CRM і Telegram для цього проєкту."
        item = analysis(language="uk", proposal_draft=body)
        decision = validate_analysis(item)
        self.assertNotIn("proposal_language_mismatch", decision.errors)
        self.assertNotIn("final_proposal_language_mismatch", decision.errors)

    def test_raw_application_suffix_injection_is_rejected(self):
        raw = self.BODIES["en"] + "\n\nApproved evidence: invented.\nCommercial terms: 1 USD."
        result = validate_analysis(analysis(proposal_draft=raw))
        self.assertIn("proposal_contains_raw_application_suffix", result.errors)

    def test_final_text_hash_and_version_are_after_exact_composition(self):
        item = validated()
        self.assertEqual(item.proposal_content_sha256, proposal_text_hash(item.proposal_draft))
        self.assertEqual(item.proposal_version, proposal_version(item))
        tampered = replace(item, proposal_draft=item.proposal_draft + " extra")
        self.assertFalse(is_proposal_ready(tampered))


class TestModelOwnedSafety(unittest.TestCase):
    PAST_WORK: ClassVar[dict[str, tuple[str, ...]]] = {
        "en": (
            "We have delivered similar systems.", "We've delivered similar systems.",
            "Our engineers implemented this before.", "Our team successfully built it.",
            "Our experience includes CRM automation.", "We previously developed this.",
        ),
        "uk": (
            "Ми вже реалізували подібну систему.", "Ми раніше розробляли це.",
            "Наша команда успішно впровадила рішення.", "Маємо досвід створення таких систем.",
        ),
        "ru": (
            "Мы уже реализовали похожую систему.", "Мы ранее разрабатывали это.",
            "Наша команда успешно внедрила решение.", "У нас есть опыт создания таких систем.",
        ),
        "pl": (
            "Nasz zespół z powodzeniem wdrożył rozwiązanie.", "Wcześniej opracowaliśmy taki system.",
            "Mamy doświadczenie w automatyzacji.", "Zrealizowaliśmy podobny projekt.",
        ),
    }

    def test_multilingual_past_work_claims_are_blocked(self):
        for language, claims in self.PAST_WORK.items():
            for claim in claims:
                with self.subTest(language=language, claim=claim):
                    result = validate_analysis(analysis(language=language, proposal_draft=claim))
                    self.assertIn("proposal_contains_unapproved_capability_claim", result.errors)

    def test_future_and_conditional_approach_claims_remain_allowed(self):
        allowed = {
            "uk": "Можемо реалізувати інтеграцію CRM для цього проєкту після підтвердження API.",
            "ru": "Можем реализовать интеграцию CRM для этого проекта после подтверждения API.",
            "pl": "Możemy wdrożyć integrację CRM dla tego projektu po potwierdzeniu API.",
            "en": "We can implement the CRM integration for this project after API confirmation.",
        }
        for language, body in allowed.items():
            result = validate_analysis(analysis(language=language, proposal_draft=body))
            self.assertNotIn("proposal_contains_unapproved_capability_claim", result.errors)

    def test_urls_domains_messengers_and_obfuscation_are_blocked(self):
        attacks = (
            "Review our work at https://example.com",
            "Review our work at www.example.com",
            "Review our work at example.com",
            "Contact us on Discord as antonov_team",
            "Join our Slack workspace",
            "See our LinkedIn profile",
            "Write on WhatsApp +380 50 123 4567",
            "Email name [at] domain [dot] com",
            "Contact us on Dіscоrd as antonov_team",
            "Find us via Telegram @antonov_team",
            "See the details at example.photography",
            "Open ftp://files.example.test/package",
            "Message @abc on the platform",
        )
        for value in attacks:
            with self.subTest(value=value):
                result = validate_analysis(analysis(proposal_draft=value))
                self.assertIn("proposal_contains_external_contact", result.errors)

    def test_contacts_in_non_body_model_fields_are_blocked(self):
        for field_name, value in (
            ("reason", "See https://example.com"),
            ("delivery_risk", "Contact us on Slack"),
            ("next_action", "Email name [at] domain [dot] com"),
            ("recommended_price", "1200 USD; https://example.com"),
            ("realistic_timeline", "5 days; Discord user"),
        ):
            with self.subTest(field_name=field_name):
                result = validate_analysis(analysis(**{field_name: value}))
                self.assertIn("structured_field_contains_external_contact", result.errors)


class TestDeliveryReliability(unittest.IsolatedAsyncioTestCase):
    async def test_manual_retrieval_forces_a_fresh_live_check(self):
        repo = InMemoryGmailRepository()
        job = await repo.save_job(stored())
        checker = MagicMock()
        checker.check = AsyncMock(
            return_value=await ActiveChecker().check(job.url or "")
        )
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=checker)
        self.assertTrue(
            await processor.deliver_validated_proposal_text_version(
                job.stable_key, AsyncMock(return_value=True)
            )
        )
        checker.check.assert_awaited_once()

    async def test_explicit_manual_retrieval_repeats_without_new_version(self):
        state: dict[str, object] = {}
        repo = InMemoryGmailRepository(state)
        job = await repo.save_job(stored())
        version = job.proposal_version
        send = AsyncMock(return_value=True)
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        self.assertTrue(await processor.deliver_validated_proposal_text_version(job.stable_key, send, live_status_already_checked=True))
        self.assertTrue(await processor.deliver_validated_proposal_text_version(job.stable_key, send, live_status_already_checked=True))
        loaded = await repo.get_job(job.stable_key)
        self.assertEqual(loaded.proposal_version, version)
        retrievals = [item for item in state["processed"].values() if item.item_type == "proposal_retrieval"]
        self.assertEqual(len(retrievals), 2)
        self.assertEqual(send.await_count, 2)

    async def test_false_and_exception_manual_send_remain_retryable(self):
        state: dict[str, object] = {}
        repo = InMemoryGmailRepository(state)
        job = await repo.save_job(stored())
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        self.assertFalse(await processor.deliver_validated_proposal_text_version(job.stable_key, AsyncMock(return_value=False), live_status_already_checked=True))
        with self.assertRaises(RuntimeError):
            await processor.deliver_validated_proposal_text_version(job.stable_key, AsyncMock(side_effect=RuntimeError("send failed")), live_status_already_checked=True)
        self.assertFalse(any(item.item_type == "proposal_retrieval" for item in state["processed"].values()))

    async def test_hard_crash_claim_becomes_retryable_after_lease(self):
        repo = InMemoryGmailRepository()
        job = await repo.save_job(stored())
        crashed_at = datetime.now(timezone.utc) - DEFAULT_SENDING_LEASE - timedelta(seconds=1)
        self.assertTrue(await repo.claim_job(job.stable_key, now=crashed_at))
        stale = await repo.list_retryable_jobs(now=datetime.now(timezone.utc))
        self.assertEqual([candidate.stable_key for candidate in stale], [job.stable_key])
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        with patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as send:
            self.assertTrue(await processor.deliver_validated_proposal_version(processor._candidate_from_job(stale[0]), stale[0], ProcessorStats(), live_status_already_checked=True))
        self.assertEqual(send.await_count, 1)

    async def test_unsolicited_delivery_is_version_deduplicated(self):
        repo = InMemoryGmailRepository()
        job = await repo.save_job(stored())
        processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
        candidate = processor._candidate_from_job(job)
        stats = ProcessorStats()
        with patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as send:
            self.assertTrue(await processor.deliver_validated_proposal_version(candidate, job, stats, live_status_already_checked=True))
            await repo.update_job_status(job.stable_key, "queued")
            latest = await repo.get_job(job.stable_key)
            self.assertFalse(await processor.deliver_validated_proposal_version(candidate, latest, stats, live_status_already_checked=True))
        self.assertEqual(send.await_count, 1)

    async def test_unsolicited_false_and_exception_each_return_to_retryable(self):
        for result in (False, RuntimeError("send failed")):
            with self.subTest(result=type(result).__name__):
                repo = InMemoryGmailRepository()
                job = await repo.save_job(stored())
                processor = GmailJobProcessor(object(), MagicMock(), 1, repository=repo, live_status_checker=ActiveChecker())
                effect = result if isinstance(result, Exception) else None
                sender = AsyncMock(side_effect=effect, return_value=result if effect is None else None)
                with patch("gmail_agent.processor.send_job_card", sender):
                    self.assertTrue(
                        await processor.deliver_validated_proposal_version(
                            processor._candidate_from_job(job),
                            job,
                            ProcessorStats(),
                            live_status_already_checked=True,
                        )
                    )
                loaded = await repo.get_job(job.stable_key)
                self.assertEqual(loaded.status, "send_failed")
                retryable = await repo.list_retryable_jobs()
                self.assertEqual([candidate.stable_key for candidate in retryable], [job.stable_key])

    async def test_direct_response_send_exception_keeps_draft_retryable(self):
        now = datetime.now(timezone.utc)
        text = "Validated synthetic proposal"
        version = "pqg-v3:synthetic"
        draft = MagicMock(
            id=8,
            text=text,
            result="draft",
            sent_at=None,
            proposal_version=version,
            proposal_content_sha256=proposal_text_hash(text),
            analysis_quality_status="QUALITY_VALID",
            quality_checked_at=now,
            source_job_identity="order:42",
            validated_live_status_at=now,
        )
        order = MagicMock(
            id=42,
            url="https://freelancehunt.com/project/synthetic-v3/1900003.html",
            status="queued",
            proposal_version=version,
            analysis_version="proposal-quality-gate-v3",
            live_status_checked_at=now,
        )
        session = MagicMock()
        session.get = AsyncMock(
            side_effect=lambda _model, item_id, **_kwargs: draft
            if item_id == 8
            else order
        )
        session.commit = AsyncMock()
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=session)
        context.__aexit__ = AsyncMock(return_value=False)
        handler = _load_response_handler()
        session_factory = MagicMock(return_value=context)
        handler.__globals__["AsyncSessionLocal"] = session_factory
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.message.edit_text = AsyncMock()
        callback.message.answer = AsyncMock(
            side_effect=RuntimeError("telegram unavailable")
        )

        with self.assertRaisesRegex(RuntimeError, "telegram unavailable"):
            await handler(callback, MagicMock(response_id=8, order_id=42))

        self.assertEqual(draft.result, "draft")
        self.assertIsNone(draft.sent_at)
        self.assertEqual(order.status, "queued")
        session.commit.assert_not_awaited()
        self.assertEqual(session_factory.call_count, 2)

    def test_direct_response_is_marked_sent_only_after_copy_answer(self):
        source = HANDLERS.read_text(encoding="utf-8")
        start = source.index("async def cb_send_manual")
        end = source.index("async def cb_rewrite", start)
        function = source[start:end]
        send_index = function.index("await callback.message.answer")
        sent_index = function.index('delivered_draft.result = "sent"')
        self.assertLess(send_index, sent_index)
        self.assertNotIn('draft.result = "sent"', function[:send_index])


class TestV3AdditivePersistence(unittest.TestCase):
    def test_v3_columns_and_migrations_are_additive(self):
        expected = {"proposal_content_sha256", "money_terms_json", "timeline_terms_json"}
        source = (HANDLERS.parents[1] / "db" / "models.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        gmail_model = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "GmailJob"
        )
        model_fields = {
            target.id
            for node in gmail_model.body
            if isinstance(node, ast.AnnAssign) and isinstance((target := node.target), ast.Name)
        }
        self.assertTrue(expected.issubset(model_fields))
        migrations = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_MIGRATIONS" for target in node.targets)
        )
        statements = [statement.upper() for statement in migrations]
        for column in expected:
            matching = [
                statement for statement in statements
                if statement.startswith("ALTER TABLE GMAIL_JOBS ")
                and f" {column.upper()} " in statement
            ]
            self.assertEqual(len(matching), 1)
            self.assertIn("ADD COLUMN IF NOT EXISTS", matching[0])
        forbidden = (" DROP ", " DELETE ", " TRUNCATE ", "ALTER COLUMN", "RENAME ")
        self.assertFalse(any(token in statement for statement in statements for token in forbidden))


if __name__ == "__main__":
    unittest.main()
