"""Release 5A V3 real-notification, routing and safety regressions."""

from __future__ import annotations

import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gmail_agent.freelancehunt_private_message import (
    normalize_conversation_title,
    parse_freelancehunt_private_message_notification,
)
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.sales_closer import (
    ClientIntent,
    SalesCloserService,
    classify_client_intent,
    reply_quality_errors,
)
from gmail_agent.sales_decisions import application_owned_sensitive_reply
from gmail_agent.sales_storage import (
    InMemorySalesRepository,
    OpportunityState,
    SalesOpportunity,
)
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import format_sales_response_card_parts
from gmail_agent.telegram_roles import (
    TelegramAuthorizationError,
    TelegramRole,
    authorize_telegram_actor,
    resolve_telegram_actor,
)
from gmail_agent.tests.test_sales_closer_5a import NOW, _job, _reply_generator


FIXTURES = Path(__file__).with_name("fixtures")


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _notification_email(
    subject: str,
    *,
    html_body: str = "",
    text_body: str = "",
    email_id: str = "v3-message",
) -> EmailMessage:
    body = text_body or ""
    return EmailMessage(
        id=email_id,
        subject=subject,
        sender="Freelancehunt <notify@freelancehunt.com>",
        body=body,
        text_body=text_body,
        html_body=html_body,
        links=[],
        received_at=NOW,
        raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
    )


class TestRealNotificationParserV3(unittest.TestCase):
    def test_uk_wrapper_and_english_client_message_are_separate(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Нове особисте повідомлення від Synthetic Alex : Synthetic project 910001",
                html_body=_fixture("freelancehunt_private_uk_en.html"),
            )
        )
        self.assertEqual(parsed.wrapper_language, "uk")
        self.assertEqual(parsed.client_message_language, "en")
        self.assertEqual(parsed.sender_display_name, "Synthetic Alex")
        self.assertEqual(parsed.sender_profile_slug, "synthetic_alex")
        self.assertEqual(parsed.conversation_subject, "Synthetic project 910001")
        self.assertEqual(parsed.thread_id, "88442211")
        self.assertEqual(
            parsed.safe_thread_url,
            "https://freelancehunt.com/ua/mailbox/read/thread/88442211#last-message",
        )
        self.assertEqual(
            parsed.actual_message_text,
            "Could you clarify the webhook authentication and retry policy?",
        )
        self.assertNotIn("token", parsed.safe_thread_url)

    def test_pl_wrapper_and_ukrainian_client_message_are_separate(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Wiadomość prywatna od Synthetic Olena : Integracja CRM",
                html_body=_fixture("freelancehunt_private_pl_uk.html"),
            )
        )
        self.assertEqual((parsed.wrapper_language, parsed.client_message_language), ("pl", "uk"))
        self.assertEqual(parsed.thread_id, "88442212")
        self.assertNotIn("Odpowiedz", parsed.actual_message_text)

    def test_ru_wrapper_english_plain_text_fallback(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Новое личное сообщение от Synthetic Maya : Reporting dashboard",
                text_body=_fixture("freelancehunt_private_ru_en.txt"),
            )
        )
        self.assertEqual((parsed.wrapper_language, parsed.client_message_language), ("ru", "en"))
        self.assertEqual(parsed.thread_id, "88442213")
        self.assertEqual(
            parsed.actual_message_text,
            "Please confirm whether the current budget includes the reporting dashboard.",
        )

    def test_en_wrapper_polish_plain_text_fallback(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "New private message from Synthetic Piotr : Webhook errors",
                text_body=_fixture("freelancehunt_private_en_pl.txt"),
            )
        )
        self.assertEqual((parsed.wrapper_language, parsed.client_message_language), ("en", "pl"))
        self.assertEqual(parsed.thread_id, "88442214")

    def test_project_id_and_url_are_optional_but_extracted_when_present(self):
        html_body = _fixture("freelancehunt_private_uk_en.html").replace(
            "</main>",
            '<a href="https://freelancehunt.com/project/synthetic/910001.html?tracking=removed">Project</a></main>',
        )
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Нове особисте повідомлення від Synthetic Alex : Synthetic project 910001",
                html_body=html_body,
            )
        )
        self.assertEqual(parsed.project_id, "910001")
        self.assertEqual(
            parsed.project_url,
            "https://freelancehunt.com/project/synthetic/910001.html",
        )

    def test_wrapper_profile_cta_footer_and_tracking_are_not_client_text(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Нове особисте повідомлення від Synthetic Alex : Synthetic project 910001",
                html_body=_fixture("freelancehunt_private_uk_en.html"),
            )
        )
        for forbidden in ("Synthetic Alex", "Відповісти", "Відписатися", "utm_source", "token"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, parsed.actual_message_text)

    def test_client_reference_to_freelancehunt_is_preserved(self):
        html_body = _fixture("freelancehunt_private_uk_en.html").replace(
            "Could you clarify the webhook authentication and retry policy?",
            "Please keep the full conversation inside Freelancehunt Workspace.",
        )
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Нове особисте повідомлення від Synthetic Alex : Synthetic project 910001",
                html_body=html_body,
            )
        )
        self.assertIn("Freelancehunt Workspace", parsed.actual_message_text)

    def test_multiple_structured_message_blocks_fail_closed(self):
        html_body = _fixture("freelancehunt_private_uk_en.html").replace(
            '<div class="message-text">Could',
            '<div class="message-text">First distinct block.</div><div class="message-text">Could',
        )
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "Нове особисте повідомлення від Synthetic Alex : Synthetic project 910001",
                html_body=html_body,
            )
        )
        self.assertEqual(parsed.parse_confidence, "FAILED")
        self.assertEqual(parsed.actual_message_text, "")
        self.assertIn("multiple_message_blocks", parsed.safe_parse_errors)

    def test_unbounded_wrapper_without_identity_fails_closed(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "New private message",
                text_body="You received a new private message\nPossible text\nFooter",
            )
        )
        self.assertEqual(parsed.parse_confidence, "FAILED")
        self.assertEqual(parsed.actual_message_text, "")
        self.assertTrue(parsed.safe_excerpt)

    def test_support_sender_is_classified_without_using_message_content(self):
        parsed = parse_freelancehunt_private_message_notification(
            _notification_email(
                "New private message from Freelancehunt : Profile onboarding",
                html_body=_fixture("freelancehunt_private_support.html"),
            )
        )
        self.assertTrue(parsed.is_platform_support_message)
        self.assertEqual(parsed.sender_profile_slug, "freelancehunt_support")


class V3ServiceCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = InMemorySalesRepository({})
        self.generator = AsyncMock(side_effect=_reply_generator)
        self.service = SalesCloserService(
            self.repository, reply_generator=self.generator, now=lambda: NOW
        )

    async def bid(self, project_id: str, *, title: str | None = None):
        job = _job(project_id)
        if title is not None:
            job.title = title
        opportunity = await self.service.ensure_from_validated_job(job)
        return (
            await self.service.mark_bid_sent(
                opportunity.id,
                opportunity.proposal_version,
                "1200 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=101,
            )
        )[0]

    def message(self, title: str, thread_id: str, *, email_id: str = "v3-thread"):
        html_body = _fixture("freelancehunt_private_uk_en.html").replace(
            "Synthetic project 910001", title
        ).replace("88442211", thread_id)
        return _notification_email(
            f"Нове особисте повідомлення від Synthetic Alex : {title}",
            html_body=html_body,
            email_id=email_id,
        )

    async def test_unique_exact_normalized_title_atomically_binds_thread(self):
        opportunity = await self.bid("910001", title='CRM — Integration “V2”')
        result = await self.service.process_client_message(
            self.message('CRM - Integration "V2"', "99110001")
        )
        self.assertEqual(result.opportunity.id, opportunity.id)
        self.assertEqual(result.resolution_basis, "conversation_subject_exact")
        self.assertEqual(result.opportunity.thread_id, "99110001")
        self.assertEqual(result.incoming_turn.resolution_basis, "conversation_subject_exact")
        self.assertEqual(
            normalize_conversation_title(' CRM — Integration “V2” '),
            normalize_conversation_title('crm- integration "v2"'),
        )

    async def test_ambiguous_title_never_binds_either_opportunity(self):
        first = await self.bid("910011", title="Shared exact title")
        second = await self.bid("910012", title="Shared exact title")
        result = await self.service.process_client_message(
            self.message("Shared exact title", "99110002", email_id="ambiguous-title")
        )
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertIn("exact project/thread mapping", result.missing_context)
        self.assertEqual((await self.repository.get_opportunity(first.id)).thread_id, "")
        self.assertEqual((await self.repository.get_opportunity(second.id)).thread_id, "")

    async def test_zero_title_match_becomes_needs_context(self):
        await self.bid("910021", title="Known title")
        result = await self.service.process_client_message(
            self.message("Unknown title", "99110003", email_id="unknown-title")
        )
        self.assertEqual(result.resolution_basis, "conversation_title_not_found")
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertIsNone(result.reply_turn)

    async def test_terminal_title_is_not_eligible_for_title_matching(self):
        terminal = await self.bid("910022", title="Closed exact title")
        await self.repository.transition(
            terminal.id,
            OpportunityState.LOST.value,
            source="synthetic",
            reason="synthetic terminal setup",
            actor="system",
        )
        result = await self.service.process_client_message(
            self.message("Closed exact title", "99110007", email_id="terminal-title")
        )
        self.assertNotEqual(result.opportunity.id, terminal.id)
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertEqual((await self.repository.get_opportunity(terminal.id)).thread_id, "")

    async def test_two_concurrent_notifications_for_one_thread_bind_one_opportunity(self):
        opportunity = await self.bid("910031", title="Concurrent title")
        first, second = await asyncio.gather(
            self.service.process_client_message(
                self.message("Concurrent title", "99110004", email_id="concurrent-a")
            ),
            self.service.process_client_message(
                self.message("Concurrent title", "99110004", email_id="concurrent-b")
            ),
        )
        self.assertEqual({first.opportunity.id, second.opportunity.id}, {opportunity.id})
        self.assertEqual((await self.repository.get_opportunity(opportunity.id)).thread_id, "99110004")

    async def test_explicit_rejection_stores_loss_without_reply_or_generator(self):
        opportunity = await self.bid("910041", title="Terminal rejection")
        message = self.message("Terminal rejection", "99110005", email_id="rejection")
        message.html_body = message.html_body.replace(
            "Could you clarify the webhook authentication and retry policy?",
            "We selected another freelancer and will not proceed.",
        )
        result = await self.service.process_client_message(message)
        self.assertEqual(result.opportunity.id, opportunity.id)
        self.assertEqual(result.opportunity.state, OpportunityState.LOST.value)
        self.assertIn("selected another freelancer", result.opportunity.loss_reason.casefold())
        self.assertIsNone(result.reply_turn)
        self.generator.assert_not_awaited()
        self.assertNotIn("mark_reply_sent", result.next_action)

    async def test_russian_price_objection_requests_price_decision_and_is_not_lost(self):
        await self.bid("910042", title="Price discussion")
        message = self.message("Price discussion", "99110008", email_id="price-ru")
        message.html_body = message.html_body.replace(
            "Could you clarify the webhook authentication and retry policy?",
            "Цена не подходит, можно немного дешевле?",
        )
        waiting = await self.service.process_client_message(message)
        self.assertEqual(waiting.incoming_turn.language, "ru")
        self.assertEqual(waiting.incoming_turn.intent, ClientIntent.PRICE_OBJECTION.value)
        self.assertEqual(waiting.opportunity.state, OpportunityState.NEEDS_HUMAN_INPUT.value)
        self.assertIsNotNone(waiting.human_request)
        self.assertNotEqual(waiting.opportunity.state, OpportunityState.LOST.value)
        result = await self.service.answer_human_request(
            waiting.human_request.id,
            "KEEP_CURRENT_PRICE",
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.assertIsNotNone(result.reply_turn)
        self.assertNotEqual(result.opportunity.state, OpportunityState.LOST.value)

    async def test_parse_ambiguity_never_calls_generator(self):
        await self.bid("910051", title="Ambiguous body")
        message = self.message("Ambiguous body", "99110006", email_id="ambiguous-body")
        message.html_body = message.html_body.replace(
            '<div class="message-text">Could',
            '<div class="message-text">One.</div><div class="message-text">Could',
        )
        result = await self.service.process_client_message(message)
        self.assertEqual(result.opportunity.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertTrue(any("actual client message" in item for item in result.missing_context))
        self.assertEqual(result.incoming_turn.content, "")
        self.assertTrue(result.safe_excerpt)
        card = "\n".join(format_sales_response_card_parts(result))
        self.assertIn("Sanitized notification excerpt", card)
        self.generator.assert_not_awaited()


class TestIntentPrecedenceV3(unittest.TestCase):
    def test_price_has_priority_over_nonterminal_or_rejection_wording(self):
        cases = (
            "The price is too high, so we may not proceed unless it is lower.",
            "Цена не подходит, можете сделать дешевле?",
            "Цена не подходит, можно немного дешевле?",
            "Ціна зависока, але чи можете запропонувати інший бюджет?",
            "Koszt jest za wysoki; czy możecie obniżyć cenę?",
        )
        for value in cases:
            with self.subTest(value=value):
                self.assertEqual(classify_client_intent(value), ClientIntent.PRICE_OBJECTION)

    def test_short_uncertainty_phrases_are_not_terminal_rejections(self):
        for value in ("не подходит", "не уверен", "дорого", "подумаем"):
            with self.subTest(value=value):
                self.assertNotEqual(classify_client_intent(value), ClientIntent.REJECTION)

    def test_only_explicit_terminal_phrase_is_rejection(self):
        self.assertEqual(
            classify_client_intent("We selected another freelancer and will not proceed."),
            ClientIntent.REJECTION,
        )

    def test_explicit_access_grant_beats_technical_mention(self):
        self.assertEqual(
            classify_client_intent("I will grant repository access and the required role."),
            ClientIntent.ACCESS_REQUEST,
        )

    def test_technical_question_with_access_word_is_not_access_request(self):
        self.assertEqual(
            classify_client_intent("Can the API access the database during webhook retries?"),
            ClientIntent.TECHNICAL_QUESTION,
        )

    def test_selection_and_contract_copy_contains_no_internal_actor_language(self):
        forbidden = ("bot", "бот", "ai agent", "internal automation", "owner review", "владел")
        for intent in ("CLIENT_READY_TO_SELECT", "SELECTED_OR_CONTRACT_STEP"):
            for language in ("uk", "ru", "en", "pl"):
                with self.subTest(intent=intent, language=language):
                    text = application_owned_sensitive_reply(intent, language).casefold()
                    self.assertFalse(any(word in text for word in forbidden))

    def test_validator_blocks_internal_actor_language_in_any_copy_ready_reply(self):
        errors = reply_quality_errors(
            "The AI agent will clarify the project.",
            opportunity=SalesOpportunity(
                id="opp-v3-validator",
                identity_key="synthetic-v3-validator",
                title="Synthetic project",
            ),
            latest_message="Please clarify the project.",
            language="en",
            intent=ClientIntent.CLARIFICATION,
            context_complete=True,
        )
        self.assertIn("internal_actor_language", errors)
        safe_errors = reply_quality_errors(
            "Мы уточним работу по проекту.",
            opportunity=SalesOpportunity(
                id="opp-v3-safe-russian",
                identity_key="synthetic-v3-safe-russian",
                title="Synthetic project",
            ),
            latest_message="Уточните работу по проекту.",
            language="ru",
            intent=ClientIntent.CLARIFICATION,
            context_complete=True,
        )
        self.assertNotIn("internal_actor_language", safe_errors)


class TestPartialRoleConfigurationV3(unittest.TestCase):
    def authorize(self, user_id: int, settings: SimpleNamespace, allowed: tuple[TelegramRole, ...]):
        return authorize_telegram_actor(
            user_id,
            "synthetic",
            settings,
            allowed_roles=allowed,
            required_settings=(),
        )

    def test_artem_only_can_answer_and_owner_plus_artem_work_without_vadim(self):
        artem_only = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=None,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=None,
        )
        self.assertEqual(
            self.authorize(202, artem_only, (TelegramRole.ARTEM, TelegramRole.VADIM)).role,
            TelegramRole.ARTEM,
        )
        owner_artem = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=None,
        )
        self.assertEqual(
            self.authorize(101, owner_artem, (TelegramRole.ADULT_OWNER, TelegramRole.ARTEM)).role,
            TelegramRole.ADULT_OWNER,
        )
        self.assertEqual(resolve_telegram_actor(202, "artem", owner_artem).role, TelegramRole.ARTEM)

    def test_vadim_only_can_answer(self):
        vadim_only = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=None,
            TELEGRAM_ARTEM_USER_ID=None,
            TELEGRAM_VADIM_USER_ID=303,
        )
        self.assertEqual(
            self.authorize(303, vadim_only, (TelegramRole.ARTEM, TelegramRole.VADIM)).role,
            TelegramRole.VADIM,
        )

    def test_unknown_and_duplicate_role_ids_fail_closed(self):
        settings = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=202,
        )
        with self.assertRaises(TelegramAuthorizationError):
            self.authorize(999, settings, (TelegramRole.ARTEM, TelegramRole.VADIM))
        with self.assertRaisesRegex(TelegramAuthorizationError, "Conflicting"):
            self.authorize(202, settings, (TelegramRole.ARTEM, TelegramRole.VADIM))


class TestAdditiveSchemaV3(unittest.TestCase):
    def test_v3_schema_changes_are_additive_and_restart_safe(self):
        source = (Path(__file__).parents[2] / "db" / "models.py").read_text(
            encoding="utf-8"
        )
        module = ast.parse(source)
        migrations = next(
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_MIGRATIONS"
                for target in node.targets
            )
        )
        statements = "\n".join(migrations).upper()
        for column in (
            "NORMALIZED_TITLE",
            "LOSS_REASON",
            "WRAPPER_LANGUAGE",
            "PARSE_CONFIDENCE",
            "RESOLUTION_BASIS",
        ):
            with self.subTest(column=column):
                self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", statements)
        self.assertNotIn("DROP TABLE", statements)
        self.assertNotIn("DELETE FROM", statements)


class TestSupportRoutingV3(unittest.IsolatedAsyncioTestCase):
    async def test_support_notification_creates_no_sales_artifacts_or_funnel_metric(self):
        sales_repository = InMemorySalesRepository({})
        generator = AsyncMock(side_effect=_reply_generator)
        service = SalesCloserService(sales_repository, reply_generator=generator)
        email = _notification_email(
            "New private message from Freelancehunt : Profile onboarding",
            html_body=_fixture("freelancehunt_private_support.html"),
            email_id="support-routing",
        )
        bot = SimpleNamespace(send_message=AsyncMock())
        processor = GmailJobProcessor(
            provider=MockGmailProvider([email]),
            bot=bot,
            chat_id=1,
            repository=InMemoryGmailRepository(),
            sales_closer=service,
        )
        stats = await processor.run()
        self.assertEqual(await sales_repository.list_opportunities(), [])
        self.assertTrue(
            all(value == 0 for value in (await sales_repository.pipeline_counts()).values())
        )
        self.assertEqual(stats.qualified, 0)
        self.assertEqual(stats.ai_analyzed, 0)
        generator.assert_not_awaited()
        text = bot.send_message.await_args.kwargs["text"]
        self.assertIn("PLATFORM MESSAGE", text)
        self.assertIn("not created or changed", text)
