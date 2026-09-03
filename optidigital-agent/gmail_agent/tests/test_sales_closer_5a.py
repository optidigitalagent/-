"""Deterministic Release 5A sales-loop tests; no real platform action occurs."""

from __future__ import annotations

import hashlib
import inspect
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.sales_closer import (
    ClientIntent,
    SalesCloserError,
    SalesCloserService,
    SalesReplyCandidate,
    UntrustedSalesMessage,
    classify_client_intent,
    notification_due_at,
    reply_quality_errors,
)
from gmail_agent.sales_storage import (
    InMemorySalesRepository,
    OpportunityState,
)
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import (
    TELEGRAM_TEXT_LIMIT,
    format_lead_timeline,
    format_pipeline_counts,
    format_sales_response_card_parts,
)

NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


async def _reply_generator(context, _client, _errors):
    language = context["client_language"]
    intent = context["deterministic_intent"]
    topic = {
        "CLARIFICATION": {"en": "authentication", "ru": "авторизация", "uk": "авторизація", "pl": "autoryzacja"},
        "TECHNICAL_QUESTION": {"en": "API integration", "ru": "API интеграция", "uk": "API інтеграція", "pl": "integracja API"},
        "PORTFOLIO_OR_PROOF_REQUEST": {"en": "approved example", "ru": "подтверждённый кейс", "uk": "підтверджений кейс", "pl": "potwierdzony przykład"},
        "PRICE_OBJECTION": {"en": "price", "ru": "цена", "uk": "ціна", "pl": "cena"},
        "TIMELINE_OBJECTION": {"en": "timeline", "ru": "срок", "uk": "термін", "pl": "termin"},
        "SCOPE_CHANGE": {"en": "additional scope", "ru": "дополнительный объём", "uk": "додатковий обсяг", "pl": "dodatkowy zakres"},
        "CALL_REQUEST": {"en": "call", "ru": "созвон", "uk": "дзвінок", "pl": "spotkanie"},
        "ACCESS_REQUEST": {"en": "access", "ru": "доступ", "uk": "доступ", "pl": "dostęp"},
        "NEGOTIATION": {"en": "terms", "ru": "условия", "uk": "умови", "pl": "warunki"},
        "CLIENT_READY_TO_SELECT": {"en": "start", "ru": "начать", "uk": "почати", "pl": "zacząć"},
        "SELECTED_OR_CONTRACT_STEP": {"en": "contract", "ru": "контракт", "uk": "контракт", "pl": "umowa"},
        "REJECTION": {"en": "decision", "ru": "решение", "uk": "рішення", "pl": "decyzja"},
        "UNKNOWN": {"en": "request", "ru": "запрос", "uk": "запит", "pl": "prośba"},
    }[intent][language]
    reply = {
        "en": f"Regarding the {topic}, we will keep to the confirmed scope. Please confirm the next required input.",
        "ru": f"По вопросу «{topic}» мы сохраним подтверждённый объём. Пожалуйста, подтвердите следующий ввод.",
        "uk": f"Щодо «{topic}» ми збережемо підтверджений обсяг. Будь ласка, підтвердьте наступні дані.",
        "pl": f"W sprawie „{topic}” zachowamy potwierdzony zakres. Proszę potwierdzić następne dane.",
    }[language]
    return SalesReplyCandidate(
        reply=reply,
        russian_summary=f"Резюме: {intent}",
        actual_ask=topic,
        strategy="Ответить по фактам и сохранить согласованный объём.",
        risks="Не расширять объём без отдельной оценки.",
    )


def _job(project_id: str = "910001", *, client: str = "Client A", language: str = "en"):
    proposal = {
        "en": "We can deliver the confirmed API integration scope.",
        "ru": "Мы можем выполнить подтверждённый объём API-интеграции.",
        "uk": "Ми можемо виконати підтверджений обсяг API-інтеграції.",
        "pl": "Możemy wykonać potwierdzony zakres integracji API.",
    }[language]
    return SimpleNamespace(
        stable_key=f"freelancehunt:project:{project_id}",
        analysis_quality_status="QUALITY_VALID",
        title=f"Synthetic project {project_id}",
        project_id=project_id,
        thread_id="",
        url=f"https://freelancehunt.com/project/synthetic/{project_id}.html",
        discovery_source="rss",
        client_name=client,
        full_description="Build a synthetic API integration with authentication and tests.",
        description_completeness="FULL",
        score=8.2,
        fit_score=8.8,
        bid_count=4,
        win_probability_signal="medium",
        recommended_price="1200 USD",
        realistic_timeline="5 days",
        delivery_risk="controlled",
        client_payment_risk="unknown",
        selected_evidence="Approved evidence: Gmail Job Agent used API integration and PostgreSQL.",
        evidence_case_id="GMAIL_JOB_AGENT",
        proposal_draft=proposal,
        proposal_version=f"pqg-v3-{project_id}",
        proposal_content_sha256=hashlib.sha256(proposal.encode()).hexdigest(),
        live_status="ACTIVE_BIDDABLE",
    )


def _email(
    project_id: str,
    body: str,
    *,
    email_id: str = "gmail-1",
    client: str = "Client A",
    thread_id: str = "",
    language_subject: str = "New private message from",
):
    url = (
        f"https://freelancehunt.com/thread/{thread_id}"
        if thread_id
        else f"https://freelancehunt.com/project/synthetic/{project_id}.html"
    )
    return EmailMessage(
        id=email_id,
        subject=f"{language_subject} {client}",
        sender="Freelancehunt <notify@freelancehunt.com>",
        body=f"{body}\n{url}",
        text_body=f"{body}\n{url}",
        links=[url],
        received_at=NOW - timedelta(seconds=45),
        raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
    )


class SalesCloserCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = {}
        self.repository = InMemorySalesRepository(self.state)
        self.generator = AsyncMock(side_effect=_reply_generator)
        self.service = SalesCloserService(
            self.repository, reply_generator=self.generator, now=lambda: NOW
        )

    async def seed(self, project_id: str = "910001", **kwargs):
        opportunity = await self.service.ensure_from_validated_job(_job(project_id, **kwargs))
        self.assertIsNotNone(opportunity)
        return opportunity

    async def bid(self, project_id: str = "910001", **kwargs):
        opportunity = await self.seed(project_id, **kwargs)
        opportunity, _confirmation, _created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW - timedelta(minutes=5),
        )
        return opportunity


class TestOpportunityAndBid(SalesCloserCase):
    async def test_valid_project_creates_exactly_one_opportunity(self):
        first = await self.seed()
        second = await self.seed()
        self.assertEqual(first.id, second.id)
        self.assertEqual(len(await self.repository.list_opportunities()), 1)
        self.assertEqual(second.state, OpportunityState.PROPOSAL_READY.value)

    async def test_mark_bid_sent_records_exact_commercial_terms_and_version(self):
        opportunity = await self.seed()
        saved, confirmation, created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1175 USD",
            "6 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
        )
        self.assertTrue(created)
        self.assertEqual(saved.actual_submitted_price, "1175 USD")
        self.assertEqual(saved.actual_submitted_timeline, "6 days")
        self.assertEqual(saved.state, OpportunityState.BID_SUBMITTED.value)
        self.assertEqual(confirmation.proposal_version, opportunity.proposal_version)

    async def test_duplicate_mark_bid_sent_is_idempotent_and_conflict_closed(self):
        opportunity = await self.seed()
        _saved, first, created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        _saved, second, duplicated = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        self.assertTrue(created)
        self.assertFalse(duplicated)
        self.assertEqual(first.id, second.id)
        with self.assertRaises(SalesCloserError):
            await self.service.mark_bid_sent(
                opportunity.id,
                opportunity.proposal_version,
                "900 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=101,
            )


class TestResolutionDedupAndContext(SalesCloserCase):
    async def test_untrusted_sender_is_rejected_before_storage(self):
        message = _email("910001", "Please clarify authentication.")
        message.sender = "spoof@example.com"
        with self.assertRaises(UntrustedSalesMessage):
            await self.service.process_client_message(message)
        self.assertEqual(await self.repository.list_opportunities(), [])

    async def test_private_message_resolves_the_exact_project_opportunity(self):
        opportunity = await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify the authentication requirement.")
        )
        self.assertEqual(result.opportunity.id, opportunity.id)
        self.assertEqual(result.resolution_basis, "project_id+project_url")
        self.assertIsNotNone(result.reply_turn)

    async def test_same_client_two_projects_stay_separate(self):
        first = await self.bid("910001", client="Shared Client")
        second = await self.bid("910002", client="Shared Client")
        one = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="same-1", client="Shared Client")
        )
        two = await self.service.process_client_message(
            _email("910002", "Please clarify authentication.", email_id="same-2", client="Shared Client")
        )
        self.assertEqual({one.opportunity.id, two.opportunity.id}, {first.id, second.id})

    async def test_duplicate_gmail_and_canonical_identity_create_one_turn(self):
        await self.bid()
        message = _email("910001", "Please clarify authentication.")
        first = await self.service.process_client_message(message)
        second = await self.service.process_client_message(message)
        incoming = [
            turn
            for turn in await self.repository.list_turns(first.opportunity.id)
            if turn.direction == "INCOMING"
        ]
        self.assertEqual(len(incoming), 1)
        self.assertTrue(second.duplicate)

    async def test_missing_mapping_becomes_needs_context_without_draft(self):
        message = _email("", "Please clarify authentication.", email_id="unmapped")
        message.links = []
        message.body = "Please clarify authentication."
        message.text_body = message.body
        result = await self.service.process_client_message(message)
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertIn("source project description", result.missing_context)
        self.assertIsNone(result.reply_turn)

    async def test_conflicting_authoritative_ids_fail_closed(self):
        first = await self.bid("910001")
        second = await self.bid("910002")
        await self.repository.update_opportunity_fields(first.id, {"thread_id": "777"})
        message = _email("910002", "Please clarify authentication.", email_id="conflict", thread_id="777")
        message.body += "\nProject ID: 910002"
        message.text_body = message.body
        result = await self.service.process_client_message(message)
        self.assertTrue(result.missing_context)
        self.assertNotEqual(result.opportunity.id, second.id)


class TestIntentAndHumanFlow(SalesCloserCase):
    async def test_clarification_creates_validated_draft(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.")
        )
        self.assertEqual(result.incoming_turn.intent, ClientIntent.CLARIFICATION.value)
        self.assertEqual(result.opportunity.state, OpportunityState.NEGOTIATING.value)
        self.assertEqual(result.reply_turn.reply_version, "r1")

    async def test_technical_question_requests_one_artem_fact(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Can you support the HubSpot CRM API integration?")
        )
        self.assertEqual(result.incoming_turn.intent, ClientIntent.TECHNICAL_QUESTION.value)
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_HUMAN_INPUT.value)
        self.assertIsNotNone(result.human_request)
        self.assertIn("YES | NO | NEED_DOCS", result.human_request.question)
        self.generator.assert_not_awaited()

    async def test_human_answer_resumes_exactly_one_reply_version(self):
        await self.bid()
        waiting = await self.service.process_client_message(
            _email("910001", "Can you support the HubSpot CRM API integration?")
        )
        result = await self.service.answer_human_request(
            waiting.human_request.id,
            "YES",
            actor_role="VADIM",
            actor_telegram_user_id=303,
        )
        self.assertEqual(result.reply_turn.reply_version, "r1")
        self.assertEqual(result.human_request.status, "ANSWERED")
        duplicate = await self.service.answer_human_request(
            waiting.human_request.id,
            "YES",
            actor_role="VADIM",
            actor_telegram_user_id=303,
        )
        self.assertTrue(duplicate.duplicate)

    async def test_commercial_and_scope_intents_require_grounded_fact(self):
        cases = (
            ("Price is too expensive, can you lower price?", ClientIntent.PRICE_OBJECTION, "minimum_price"),
            ("This timeline is too long, can you deliver sooner?", ClientIntent.TIMELINE_OBJECTION, "earliest_delivery"),
            ("Please also add one more dashboard as an extra feature.", ClientIntent.SCOPE_CHANGE, "scope_change_decision"),
            ("Can we have a call tomorrow?", ClientIntent.CALL_REQUEST, "call_availability"),
        )
        for index, (body, intent, fact_key) in enumerate(cases, 1):
            with self.subTest(intent=intent):
                project = str(920000 + index)
                await self.bid(project)
                result = await self.service.process_client_message(
                    _email(project, body, email_id=f"human-{index}")
                )
                self.assertEqual(result.incoming_turn.intent, intent.value)
                self.assertEqual(result.human_request.fact_key, fact_key)
                self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_HUMAN_INPUT.value)

    async def test_scope_expansion_after_answer_is_not_accepted_for_free(self):
        await self.bid()
        waiting = await self.service.process_client_message(
            _email("910001", "Please also add one more dashboard as an extra feature.")
        )
        result = await self.service.answer_human_request(
            waiting.human_request.id,
            "SEPARATE_PAID_ESTIMATE",
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.assertIsNotNone(result.reply_turn)
        self.assertNotIn("free", result.reply_turn.content.casefold())

    async def test_proof_request_uses_only_approved_evidence_context(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please show a portfolio example or case study.")
        )
        self.generator.assert_not_awaited()
        self.assertIn("Gmail", result.reply_turn.content)
        self.assertIsNotNone(result.reply_turn)

    async def test_call_request_waits_for_availability(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Can we schedule a call tomorrow?")
        )
        self.assertEqual(result.human_request.fact_key, "call_availability")

    async def test_selected_and_contract_intents_are_escalated(self):
        for index, (body, intent) in enumerate(
            (("We choose you and are ready to start.", ClientIntent.CLIENT_READY_TO_SELECT),
             ("The contract and Safe payment are ready.", ClientIntent.SELECTED_OR_CONTRACT_STEP)),
            1,
        ):
            project = str(930000 + index)
            await self.bid(project)
            result = await self.service.process_client_message(
                _email(project, body, email_id=f"selected-{index}")
            )
            self.assertEqual(result.incoming_turn.intent, intent.value)
            expected_state = (
                OpportunityState.SELECTION_REVIEW.value
                if intent == ClientIntent.CLIENT_READY_TO_SELECT
                else OpportunityState.CONTRACT_REVIEW.value
            )
            self.assertEqual(result.opportunity.state, expected_state)

    async def test_rejection_becomes_lost(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "We decided not to proceed with the project.")
        )
        self.assertEqual(result.incoming_turn.intent, ClientIntent.REJECTION.value)
        self.assertEqual(result.opportunity.state, OpportunityState.LOST.value)

    def test_all_required_intent_labels_are_present(self):
        expected = {
            "CLARIFICATION", "TECHNICAL_QUESTION", "PORTFOLIO_OR_PROOF_REQUEST",
            "PRICE_OBJECTION", "TIMELINE_OBJECTION", "SCOPE_CHANGE", "CALL_REQUEST",
            "ACCESS_REQUEST", "NEGOTIATION", "CLIENT_READY_TO_SELECT",
            "SELECTED_OR_CONTRACT_STEP", "REJECTION", "UNKNOWN",
        }
        self.assertEqual({item.value for item in ClientIntent}, expected)


class TestLanguagesAndValidator(SalesCloserCase):
    async def test_reply_languages_uk_ru_en_pl(self):
        cases = (
            ("uk", "Потрібно уточнити авторизацію?", "Нове особисте повідомлення від"),
            ("ru", "Нужно уточнить авторизацию?", "Новое личное сообщение от"),
            ("en", "Please clarify authentication?", "New private message from"),
            ("pl", "Proszę wyjaśnić autoryzację?", "Wiadomość prywatna od"),
        )
        for index, (language, body, subject) in enumerate(cases, 1):
            with self.subTest(language=language):
                project = str(940000 + index)
                await self.bid(project, language=language)
                result = await self.service.process_client_message(
                    _email(project, body, email_id=f"lang-{language}", language_subject=subject)
                )
                self.assertEqual(result.incoming_turn.language, language)
                self.assertEqual(result.reply_turn.language, language)

    async def test_validator_rejects_unsafe_and_ungrounded_outputs(self):
        opportunity = await self.bid()
        base = {
            "opportunity": opportunity,
            "latest_message": "Please clarify authentication and price.",
            "language": "en",
            "intent": ClientIntent.CLARIFICATION,
            "context_complete": True,
        }
        cases = (
            ("I guarantee authentication will work.", "unsupported_commitment"),
            ("Authentication is available for 900 USD.", "price_mismatch"),
            ("Authentication will be delivered in 2 days.", "unapproved_deadline"),
            ("Authentication details are at https://example.com.", "external_contact"),
            ("Нужно уточнить авторизацию.", "wrong_language"),
            ("Thanks for your message. Happy to help.", "generic_or_unrelated"),
            ("Authentication increased conversion by 40%.", "invented_case_metric_or_result"),
        )
        for reply, expected in cases:
            with self.subTest(expected=expected):
                self.assertIn(expected, reply_quality_errors(reply, **base))

    async def test_scope_validator_rejects_free_expansion(self):
        opportunity = await self.bid()
        errors = reply_quality_errors(
            "The additional scope is included at no extra cost.",
            opportunity=opportunity,
            latest_message="Please add additional scope.",
            language="en",
            intent=ClientIntent.SCOPE_CHANGE,
            context_complete=True,
        )
        self.assertIn("expanded_scope_accepted_for_free", errors)

    async def test_validator_rejects_confirmed_dialogue_contradiction(self):
        opportunity = await self.bid()
        errors = reply_quality_errors(
            "We cannot support the authentication requirement.",
            opportunity=opportunity,
            latest_message="Can you support the authentication requirement?",
            language="en",
            intent=ClientIntent.CLARIFICATION,
            context_complete=True,
            confirmed_history=["We can support the authentication requirement."],
        )
        self.assertIn("contradicts_confirmed_dialogue", errors)

    async def test_validator_rejects_unconfirmed_availability(self):
        opportunity = await self.bid()
        errors = reply_quality_errors(
            "We are available for the authentication call tomorrow.",
            opportunity=opportunity,
            latest_message="Can we discuss authentication on a call?",
            language="en",
            intent=ClientIntent.CALL_REQUEST,
            context_complete=True,
        )
        self.assertIn("unsupported_commitment", errors)

    async def test_missing_context_always_fails_validator(self):
        opportunity = await self.bid()
        errors = reply_quality_errors(
            "Regarding authentication, please confirm the next input.",
            opportunity=opportunity,
            latest_message="Please clarify authentication.",
            language="en",
            intent=ClientIntent.CLARIFICATION,
            context_complete=False,
        )
        self.assertIn("required_context_missing", errors)

    async def test_maximum_one_bounded_repair(self):
        await self.bid()
        bad = SalesReplyCandidate("Thanks.", "x", "x", "x", "x")
        generator = AsyncMock(return_value=bad)
        service = SalesCloserService(self.repository, reply_generator=generator, now=lambda: NOW)
        result = await service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="repair")
        )
        self.assertEqual(generator.await_count, 2)
        self.assertIsNone(result.reply_turn)
        self.assertEqual(result.opportunity.state, OpportunityState.MANUAL_REVIEW.value)


class TestConfirmationRestartAndUx(SalesCloserCase):
    def test_working_notification_window_defers_to_kyiv_0800(self):
        late = datetime(2026, 9, 3, 19, 30, tzinfo=timezone.utc)  # 22:30 Kyiv
        due = notification_due_at(late)
        self.assertEqual(due, datetime(2026, 9, 4, 5, 0, tzinfo=timezone.utc))

    async def test_owner_sent_confirmation_binds_exact_hash_version_and_latency(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.")
        )
        saved, confirmation, created = await self.service.mark_reply_sent(
            result.opportunity.id,
            result.reply_turn.reply_version,
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
        )
        self.assertTrue(created)
        self.assertEqual(confirmation.content_sha256, result.reply_turn.content_sha256)
        self.assertEqual(confirmation.reply_version, "r1")
        self.assertEqual(saved.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual(confirmation.response_latency_seconds, 45.0)

    async def test_restart_preserves_opportunity_turns_and_waiting_state(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.")
        )
        await self.service.mark_reply_sent(
            result.opportunity.id,
            "r1",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        restarted = SalesCloserService(
            InMemorySalesRepository(self.state), reply_generator=_reply_generator, now=lambda: NOW
        )
        opportunity, _transitions, turns, _requests = await restarted.lead_timeline(
            result.opportunity.id
        )
        self.assertEqual(opportunity.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual([turn.direction for turn in turns], ["INCOMING", "OUTGOING_CONFIRMED"])

    async def test_pipeline_counts_required_states(self):
        ready = await self.seed("950001")
        submitted = await self.bid("950002")
        counts = await self.service.pipeline_counts()
        text = format_pipeline_counts(counts)
        self.assertEqual(counts[OpportunityState.PROPOSAL_READY.value], 1)
        self.assertEqual(counts[OpportunityState.BID_SUBMITTED.value], 1)
        self.assertIn("follow-up scheduler: disabled", text.casefold())
        self.assertNotEqual(ready.id, submitted.id)

    async def test_lead_timeline_contains_full_state_history_and_one_next_action(self):
        opportunity = await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.")
        )
        timeline = await self.service.lead_timeline(opportunity.id)
        parts = format_lead_timeline(*timeline)
        text = "\n".join(parts)
        self.assertIn("DISCOVERED", text)
        self.assertIn("PROPOSAL_READY", text)
        self.assertIn("BID_SUBMITTED", text)
        self.assertIn("INCOMING", text)
        self.assertEqual(text.count("Next action (one)"), 1)
        self.assertEqual(result.reply_turn.reply_version, "r1")

    async def test_sales_card_is_html_safe_and_multipart_bounded(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication <script>. " + "detail " * 1800)
        )
        parts = format_sales_response_card_parts(result)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in parts))
        self.assertNotIn("<script>", "".join(parts))

    async def test_no_automatic_platform_action_surface(self):
        source = inspect.getsource(__import__("gmail_agent.sales_closer", fromlist=["SalesCloserService"]))
        self.assertNotIn("submit_bid", source)
        self.assertNotIn("send_platform_message", source)
        self.assertNotIn("accept_contract", source)
        opportunity = await self.seed()
        self.assertEqual(opportunity.follow_up_status, "DISABLED_5A")
        self.assertIsNone(opportunity.next_follow_up_at)

    async def test_processor_routes_private_message_to_sales_pipeline_and_telegram_only(self):
        await self.bid()
        email = _email("910001", "Please clarify authentication.", email_id="processor-private")
        provider = MockGmailProvider([email])
        bot = SimpleNamespace(send_message=AsyncMock())
        processor = GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=1,
            repository=InMemoryGmailRepository(),
            sales_closer=self.service,
            max_cards_per_scan=10,
        )
        stats = await processor.run()
        self.assertEqual(stats.qualified, 1)
        bot.send_message.assert_awaited()
        self.assertIn("HIGH PRIORITY", bot.send_message.await_args_list[0].kwargs["text"])


class TestIntentClassifier(unittest.TestCase):
    def test_deterministic_intent_examples(self):
        cases = {
            "Could you clarify this requirement?": ClientIntent.CLARIFICATION,
            "Does your API integrate with our CRM?": ClientIntent.TECHNICAL_QUESTION,
            "Show a portfolio case study": ClientIntent.PORTFOLIO_OR_PROOF_REQUEST,
            "This is too expensive, lower price": ClientIntent.PRICE_OBJECTION,
            "We need this sooner, it is urgent": ClientIntent.TIMELINE_OBJECTION,
            "Please also add one more feature": ClientIntent.SCOPE_CHANGE,
            "Can we schedule a call?": ClientIntent.CALL_REQUEST,
            "Please provide access credentials": ClientIntent.ACCESS_REQUEST,
            "Let's agree milestone terms": ClientIntent.NEGOTIATION,
            "We choose you and are ready to start": ClientIntent.CLIENT_READY_TO_SELECT,
            "The contract and Safe are ready": ClientIntent.SELECTED_OR_CONTRACT_STEP,
            "We will not proceed": ClientIntent.REJECTION,
            "Hello there": ClientIntent.UNKNOWN,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify_client_intent(text), expected)
