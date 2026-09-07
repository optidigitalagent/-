"""Issue #20 regressions for decision-first project cards.

These fixtures contain only the public facts that were observed for the two
reported Freelancehunt projects.  Every external boundary is replaced here;
the separate live runner exercises the provider and PostgreSQL path.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from gmail_agent.digest_parser import DigestJobCandidate
from gmail_agent.email_analyzer import JobAnalysis, analyze_candidate, analyze_email
from gmail_agent.freelancehunt_discovery import (
    enrich_candidate_scope,
    parse_freelancehunt_rss,
)
from gmail_agent.live_status import LiveStatus
from gmail_agent.quality_gate import QualityStatus, apply_validation, validate_analysis
from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import format_job_card_parts
from unittest.mock import patch


def _completion(payload: dict[str, object]) -> MagicMock:
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = json.dumps(payload, ensure_ascii=False)
    choice.message.refusal = None
    response = MagicMock()
    response.choices = [choice]
    response.model = "gpt-4o-mini-2024-07-18"
    response.usage.prompt_tokens = 900
    response.usage.completion_tokens = 300
    response.usage.total_tokens = 1200
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)
    return client


def _take_payload() -> dict[str, object]:
    return {
        "is_relevant": True,
        "commercial_decision": "TAKE",
        "decision_reason": "The requested SEO descriptions match the approved SEO lane.",
        "clarification_question": "",
        "title": "SEO descriptions for 10 products",
        "platform": "Freelancehunt",
        "score": 8.0,
        "fit_score": 8.5,
        "reason": "Bounded SEO copywriting task.",
        "budget": "1000 UAH",
        "url": "https://freelancehunt.com/project/seo/1651611.html",
        "urgency": "medium",
        "why_relevant": "The source asks for SEO descriptions for ten products.",
        "red_flags": [],
        "language": "ru",
        "category": "SEO, copywriting",
        "skills": "SEO copywriting, ecommerce",
        "deadline": "1-2 days",
        "bid_count": None,
        "client_name": "",
        "client_profile_url": "",
        "client_context": "",
        "project_id": "1651611",
        "thread_id": "",
        "service_lane": "SEO content",
        "executable": "yes",
        "win_probability_signal": "medium — clear bounded task",
        "scope_clarity": "high — ten descriptions up to 1000 characters",
        "estimated_effort": "10-14 hours",
        "delivery_risk": "Product facts must come from the supplied attachment.",
        "client_payment_risk": "Use the platform milestone.",
        "project_mode": "CASH",
        "project_mode_reason": "The scope is small and precisely bounded.",
        "recommended_price": "1000 UAH as one milestone",
        "realistic_timeline": "2 days",
        "selected_evidence": "",
        "evidence_case_id": "STATUS_DENT",
        "evidence": "The source requests SEO descriptions for 10 ecommerce products.",
        "proposal_draft": (
            "Здравствуйте! Подготовлю SEO-описания для 10 товаров интернет-магазина: "
            "до 1000 символов каждое, с естественными ключами и акцентом на покупку. "
            "Перед началом сверю характеристики товаров из приложения, затем проверю "
            "уникальность, читаемость и соответствие объёму."
        ),
        "needs_context": False,
        "next_action": "Проверить и вручную подать готовое предложение.",
    }


class TestIssue20DecisionFirst(unittest.IsolatedAsyncioTestCase):
    async def test_provider_contract_is_strict_json_schema_and_records_usage(self):
        client = _completion(_take_payload())
        analysis = await analyze_email(
            "freelancehunt:1651611",
            "SEO descriptions for 10 products",
            "Freelancehunt",
            "Ten product descriptions, no more than 1000 characters each.",
            client=client,
        )
        kwargs = client.chat.completions.create.await_args.kwargs
        self.assertEqual(kwargs["response_format"]["type"], "json_schema")
        self.assertTrue(kwargs["response_format"]["json_schema"]["strict"])
        self.assertEqual(analysis.provider_outcome, "SUCCESS")
        self.assertEqual(analysis.provider_total_tokens, 1200)

    async def test_authoritative_candidate_budget_cannot_be_replaced_by_model(self):
        payload = _take_payload()
        payload["budget"] = "53,673 UAH"
        candidate = DigestJobCandidate(
            source_email_id="rss:1651611",
            platform="Freelancehunt",
            title="SEO descriptions for 10 products",
            description="Ten product descriptions, no more than 1000 characters each.",
            budget="1000 UAH",
            url="https://freelancehunt.com/project/seo/1651611.html",
            category="SEO",
            received_at=datetime.now(timezone.utc),
            stable_key="freelancehunt:1651611",
            project_id="1651611",
            budget_currency="UAH",
            description_completeness="FULL",
        )
        analysis = await analyze_candidate(candidate, client=_completion(payload))
        self.assertEqual(analysis.budget, "1000 UAH")
        self.assertEqual(analysis.budget_provenance, "SOURCE_CANDIDATE")

    def test_truncated_rss_description_is_never_full(self):
        description = "SEO requirements " + ("word " * 70) + "..."
        xml = f"""<?xml version='1.0'?><rss><channel><item>
          <title>SEO descriptions - 1000 UAH</title>
          <description>{description}</description>
          <link>https://freelancehunt.com/project/seo/1651611.html</link>
          <guid>https://freelancehunt.com/project/seo/1651611.html</guid>
        </item></channel></rss>"""
        candidate = parse_freelancehunt_rss(xml).candidates[0]
        self.assertEqual(candidate.description_completeness, "PARTIAL")

    async def test_logo_no_ai_requirement_becomes_justified_skip_without_model(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock()
        candidate = DigestJobCandidate(
            source_email_id="rss:1651609",
            platform="Freelancehunt",
            title="Изменить логотип",
            description=(
                "Нужна консультация по изменению существующего логотипа. "
                "Ищу именно специалиста по логотипам, а не ИИ."
            ),
            budget="1200 USD",
            url="https://freelancehunt.com/project/logo/1651609.html",
            category="Логотипы",
            received_at=datetime.now(timezone.utc),
            stable_key="freelancehunt:1651609",
            project_id="1651609",
            budget_currency="USD",
            description_completeness="FULL",
        )
        analysis = await analyze_candidate(candidate, client=client)
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        apply_validation(analysis, validate_analysis(analysis))
        client.chat.completions.create.assert_not_awaited()
        self.assertEqual(analysis.commercial_decision, "SKIP")
        self.assertEqual(analysis.analysis_quality_status, QualityStatus.NON_EXECUTABLE.value)
        rendered = "\n".join(format_job_card_parts(analysis))
        self.assertIn("⛔ <b>Ставку не тратим</b>", rendered)
        self.assertNotIn("QUALITY", rendered)
        self.assertNotIn("INVALID", rendered)

    async def test_take_persists_usage_version_hash_and_renders_after_reload(self):
        project_id = "990020001"
        payload = _take_payload()
        payload.update(
            title="Synthetic SEO scope regression",
            project_id=project_id,
            url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
            evidence="Synthetic: SEO-описания для 10 товаров до 1000 символов.",
        )
        candidate = enrich_candidate_scope(DigestJobCandidate(
            source_email_id=f"synthetic:{project_id}",
            platform="Freelancehunt",
            title="Synthetic SEO scope regression",
            description=(
                "Synthetic: нужно составить SEO-описания для 10 товаров, "
                "до 1000 символов каждое, уникальные и с естественными ключами."
            ),
            budget="1000 UAH",
            url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
            category="SEO, copywriting",
            received_at=datetime.now(timezone.utc),
            stable_key=f"freelancehunt:{project_id}",
            project_id=project_id,
            budget_currency="UAH",
            discovery_source="synthetic_test",
        ),
            description=(
                "Synthetic: нужно составить SEO-описания для 10 товаров, "
                "до 1000 символов каждое, уникальные и с естественными ключами."
            ),
            source_kind="SYNTHETIC_TEST",
            main_text_completeness="FULL",
            materials_status="NOT_REFERENCED",
            scope_sufficiency="SUFFICIENT_FOR_FIXED_TERMS",
        )
        analysis = await analyze_candidate(candidate, client=_completion(payload))
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        decision = validate_analysis(analysis)
        self.assertEqual(decision.errors, ())
        apply_validation(analysis, decision)
        self.assertTrue(analysis.proposal_version)
        self.assertEqual(len(analysis.proposal_content_sha256), 64)

        state: dict[str, object] = {}
        first = InMemoryGmailRepository(state)
        await first.save_job(GmailJobProcessor._stored_job(candidate, analysis))
        reloaded = await InMemoryGmailRepository(state).get_job(candidate.stable_key)
        restored = GmailJobProcessor._analysis_from_job(reloaded)
        self.assertEqual(restored.commercial_decision, "TAKE")
        self.assertEqual(restored.provider_total_tokens, 1200)
        self.assertEqual(restored.proposal_version, analysis.proposal_version)
        self.assertEqual(restored.proposal_content_sha256, analysis.proposal_content_sha256)
        rendered = "\n".join(format_job_card_parts(restored))
        self.assertIn("✅ <b>Подаёмся: предложение готово</b>", rendered)
        self.assertIn(analysis.proposal_draft, rendered)

    async def test_rss_full_marker_without_enrichment_proof_stays_partial(self):
        candidate = DigestJobCandidate(
            source_email_id="rss:1651611",
            platform="Freelancehunt",
            title="SEO descriptions for 10 products",
            description="RSS preview manually labelled full.",
            budget="1000 UAH",
            url="https://freelancehunt.com/project/seo/1651611.html",
            category="SEO",
            received_at=datetime.now(timezone.utc),
            stable_key="freelancehunt:1651611",
            project_id="1651611",
            discovery_source="rss",
            description_completeness="FULL",
        )
        analysis = await analyze_candidate(candidate, client=_completion(_take_payload()))
        self.assertEqual(analysis.description_completeness, "PARTIAL")
        self.assertEqual(analysis.scope_sufficiency, "UNKNOWN")
        self.assertEqual(analysis.scope_enrichment_sha256, "")

    async def test_unavailable_scope_relevant_attachment_becomes_exact_ask(self):
        candidate = enrich_candidate_scope(
            DigestJobCandidate(
                source_email_id="rss:1651611",
                platform="Freelancehunt",
                title="SEO descriptions for 10 products",
                description="RSS preview",
                budget="1000 UAH",
                url="https://freelancehunt.com/project/seo/1651611.html",
                category="SEO",
                received_at=datetime.now(timezone.utc),
                stable_key="freelancehunt:1651611",
                project_id="1651611",
                discovery_source="rss",
            ),
            description=(
                "Нужно подготовить описания товаров. Характеристики и другие "
                "условия находятся в недоступном приложении."
            ),
            source_kind="PUBLIC_PAGE_VERIFIED",
            main_text_completeness="FULL",
            materials_status="UNAVAILABLE_SCOPE_RELEVANT",
            scope_sufficiency="INSUFFICIENT_FOR_FIXED_TERMS",
        )
        client = _completion(_take_payload())
        analysis = await analyze_candidate(candidate, client=client)
        client.chat.completions.create.assert_not_awaited()
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        decision = validate_analysis(analysis)
        self.assertEqual(decision.status, QualityStatus.NEEDS_CLARIFICATION.value)
        apply_validation(analysis, decision)
        self.assertEqual(analysis.commercial_decision, "ASK")
        self.assertEqual(analysis.clarification_question.count("?"), 1)
        self.assertEqual(analysis.recommended_price, "")
        self.assertEqual(analysis.realistic_timeline, "")
        self.assertEqual(analysis.proposal_draft, "")

    async def test_execution_materials_only_requires_start_condition_after_reload(self):
        project_id = "990020002"
        payload = _take_payload()
        payload.update(
            title="Synthetic bounded descriptions",
            project_id=project_id,
            url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
            evidence="Synthetic: 10 SEO-описаний, не более 1000 символов каждое.",
        )
        candidate = enrich_candidate_scope(
            DigestJobCandidate(
                source_email_id=f"synthetic:{project_id}",
                platform="Freelancehunt",
                title="Synthetic bounded descriptions",
                description="Synthetic source placeholder.",
                budget="1000 UAH",
                url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
                category="SEO",
                received_at=datetime.now(timezone.utc),
                stable_key=f"freelancehunt:{project_id}",
                project_id=project_id,
                budget_currency="UAH",
                discovery_source="synthetic_test",
            ),
            description=(
                "Synthetic: 10 SEO-описаний, не более 1000 символов каждое; "
                "карточки товаров нужны только как исходные материалы и не добавляют требований."
            ),
            source_kind="SYNTHETIC_TEST",
            main_text_completeness="FULL",
            materials_status="UNAVAILABLE_EXECUTION_INPUTS_ONLY",
            scope_sufficiency="SUFFICIENT_FOR_FIXED_TERMS",
        )
        analysis = await analyze_candidate(candidate, client=_completion(payload))
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        decision = validate_analysis(analysis)
        self.assertEqual(decision.errors, ())
        apply_validation(analysis, decision)

        state: dict[str, object] = {}
        await InMemoryGmailRepository(state).save_job(
            GmailJobProcessor._stored_job(candidate, analysis)
        )
        job = await InMemoryGmailRepository(state).get_job(candidate.stable_key)
        restored = GmailJobProcessor._analysis_from_job(job)
        rendered = "\n".join(format_job_card_parts(restored))
        self.assertIn("10", restored.proposal_draft)
        self.assertIn("1000", restored.proposal_draft)
        self.assertIn(
            "Отсчёт срока начинается после получения согласованных исходных материалов.",
            restored.proposal_draft,
        )
        self.assertIn(restored.proposal_draft, rendered)
        self.assertEqual(restored.proposal_version, analysis.proposal_version)
        self.assertEqual(
            restored.proposal_content_sha256,
            analysis.proposal_content_sha256,
        )

    async def test_skip_delivery_never_creates_5a_opportunity(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock()
        candidate = DigestJobCandidate(
            source_email_id="rss:1651609",
            platform="Freelancehunt",
            title="Изменить логотип",
            description="Ищу именно специалиста по логотипам, а не ИИ.",
            budget="1200 USD",
            url="https://freelancehunt.com/project/logo/1651609.html",
            category="Логотипы",
            received_at=datetime.now(timezone.utc),
            stable_key="freelancehunt:1651609",
            project_id="1651609",
            description_completeness="FULL",
        )
        analysis = await analyze_candidate(candidate, client=client)
        analysis.live_status = LiveStatus.ACTIVE_BIDDABLE.value
        analysis.live_status_checked_at = datetime.now(timezone.utc)
        analysis.biddable = True
        apply_validation(analysis, validate_analysis(analysis))
        repository = InMemoryGmailRepository()
        job = await repository.save_job(GmailJobProcessor._stored_job(candidate, analysis))
        sales = MagicMock()
        sales.ensure_from_validated_job = AsyncMock()
        processor = GmailJobProcessor(
            MagicMock(), MagicMock(), 1, repository=repository, sales_closer=sales
        )
        with patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)):
            sent = await processor.deliver_validated_proposal_version(
                candidate, job, ProcessorStats(), live_status_already_checked=True
            )
        self.assertTrue(sent)
        sales.ensure_from_validated_job.assert_not_awaited()
        self.assertEqual((await repository.get_job(candidate.stable_key)).status, "skipped")

    def test_ask_card_contains_one_question_and_no_proposal_or_internal_codes(self):
        reason = "В открытом источнике не видны характеристики товаров из приложения."
        analysis = JobAnalysis(
            email_id="freelancehunt:1651611",
            is_relevant=True,
            title="SEO descriptions for 10 products",
            platform="Freelancehunt",
            score=7.0,
            reason=reason,
            budget="1000 UAH",
            url="https://freelancehunt.com/project/seo/1651611.html",
            urgency="medium",
            why_relevant="SEO content",
            analysis_succeeded=True,
            executable="maybe",
            commercial_decision="ASK",
            decision_reason=reason,
            clarification_question="Какие обязательные условия указаны в недоступном приложении?",
            next_action="Запросить у клиента обязательные требования из приложения.",
            full_description="SEO описания товаров; обязательные условия находятся в недоступном приложении.",
            evidence_case_id="NO_DIRECT_CASE",
            model_output_json=json.dumps({'ask_basis': {
                'missing_fact': 'Обязательные условия из приложения', 'owner': 'CLIENT',
                'fact_kind': 'CLIENT_REQUIREMENT',
                'source_quote': 'обязательные условия находятся в недоступном приложении',
                'absence_reason': 'Приложение недоступно.', 'required_for_estimate': True,
                'estimate_impact': 'Условия определяют объём и стоимость работы.',
            }}, ensure_ascii=False),
            language="ru",
            live_status=LiveStatus.ACTIVE_BIDDABLE.value,
            live_status_checked_at=datetime.now(timezone.utc),
            biddable=True,
        )
        decision = validate_analysis(analysis)
        self.assertEqual(decision.status, QualityStatus.NEEDS_CLARIFICATION.value)
        apply_validation(analysis, decision)
        rendered = "\n".join(format_job_card_parts(analysis))
        self.assertIn("🟡 <b>Нужно уточнение</b>", rendered)
        self.assertEqual(rendered.count("?"), 1)
        self.assertIn("Предложение:</b> отсутствует", rendered)
        self.assertNotIn("QUALITY", rendered)
        self.assertNotIn("INVALID", rendered)
