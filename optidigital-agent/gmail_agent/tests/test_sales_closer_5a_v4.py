"""Release 5A V4 production-blocker regressions."""

from __future__ import annotations

import ast
import asyncio
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gmail_agent.freelancehunt_private_message import (
    parse_freelancehunt_private_message_notification,
)
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.sales_closer import (
    ClientIntent,
    SalesCloserError,
    SalesCloserService,
    classify_client_intent,
)
from gmail_agent.sales_storage import (
    HumanInformationRequest,
    InMemorySalesRepository,
    OpportunityState,
)
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.telegram_notifier import send_sales_response_card
from gmail_agent.tests.test_sales_closer_5a import NOW, _job, _reply_generator


FIXTURES = Path(__file__).with_name("fixtures")


def _support_email(*, email_id: str = "real-support-v4", profile_url: str = "") -> EmailMessage:
    html = (FIXTURES / "freelancehunt_private_support_real.html").read_text(
        encoding="utf-8"
    )
    if profile_url:
        html = html.replace(
            "https://freelancehunt.com/ua/profile/show/freelancehunt_nastasiia.html",
            profile_url,
        )
    return EmailMessage(
        id=email_id,
        subject=(
            "Нове особисте повідомлення від Anastasiia : "
            "Ваш успішний старт на Freelancehunt"
        ),
        sender="Freelancehunt <notify@freelancehunt.com>",
        body="",
        text_body="",
        html_body=html,
        links=[],
        received_at=NOW,
        raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
    )


def _thread_email(
    title: str,
    thread_id: str,
    *,
    email_id: str,
    message: str = "Could you clarify the webhook authentication and retry policy?",
) -> EmailMessage:
    html = (FIXTURES / "freelancehunt_private_uk_en.html").read_text(
        encoding="utf-8"
    )
    html = html.replace("Synthetic project 910001", title)
    html = html.replace("88442211", thread_id)
    html = html.replace(
        "Could you clarify the webhook authentication and retry policy?", message
    )
    return EmailMessage(
        id=email_id,
        subject=f"Нове особисте повідомлення від Synthetic Alex : {title}",
        sender="Freelancehunt <notify@freelancehunt.com>",
        body="",
        text_body="",
        html_body=html,
        links=[],
        received_at=NOW - timedelta(seconds=30),
        raw_headers={"Message-ID": f"<{email_id}@freelancehunt.com>"},
    )


async def _bid(
    service: SalesCloserService, project_id: str, *, title: str
):
    job = _job(project_id)
    job.title = title
    opportunity = await service.ensure_from_validated_job(job)
    return (
        await service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW - timedelta(minutes=5),
        )
    )[0]


class TestRealSupportV4(unittest.TestCase):
    def test_real_profile_show_staff_slug_is_authoritative(self):
        parsed = parse_freelancehunt_private_message_notification(_support_email())
        self.assertEqual(parsed.sender_profile_slug, "freelancehunt_nastasiia")
        self.assertTrue(parsed.is_platform_support_message)
        self.assertEqual(parsed.thread_id, "88442999")

    def test_all_eight_required_profile_url_forms_extract_staff_slug(self):
        paths = (
            "/profile/freelancehunt_nastasiia",
            "/profile/freelancehunt_nastasiia.html",
            "/ua/profile/freelancehunt_nastasiia",
            "/ua/profile/freelancehunt_nastasiia.html",
            "/profile/show/freelancehunt_nastasiia",
            "/profile/show/freelancehunt_nastasiia.html",
            "/ua/profile/show/freelancehunt_nastasiia",
            "/ua/profile/show/freelancehunt_nastasiia.html",
        )
        for index, path in enumerate(paths):
            with self.subTest(path=path):
                parsed = parse_freelancehunt_private_message_notification(
                    _support_email(
                        email_id=f"support-path-{index}",
                        profile_url="https://freelancehunt.com" + path,
                    )
                )
                self.assertEqual(parsed.sender_profile_slug, "freelancehunt_nastasiia")
                self.assertTrue(parsed.is_platform_support_message)

    def test_client_text_mentioning_freelancehunt_is_not_support(self):
        parsed = parse_freelancehunt_private_message_notification(
            _thread_email(
                "Ordinary client",
                "88442001",
                email_id="ordinary-client-v4",
                message="Please keep all project communication inside Freelancehunt.",
            )
        )
        self.assertEqual(parsed.sender_profile_slug, "synthetic_alex")
        self.assertFalse(parsed.is_platform_support_message)


class TestSupportRoutingV4(unittest.IsolatedAsyncioTestCase):
    async def test_restart_scan_sends_one_support_card_and_no_sales_side_effects(self):
        sales_state: dict = {}
        gmail_state: dict = {}
        bot = SimpleNamespace(send_message=AsyncMock(return_value=True))
        generator = AsyncMock(side_effect=_reply_generator)
        email = _support_email()

        first = GmailJobProcessor(
            provider=MockGmailProvider([email]),
            bot=bot,
            chat_id=1,
            repository=InMemoryGmailRepository(gmail_state),
            sales_closer=SalesCloserService(
                InMemorySalesRepository(sales_state), reply_generator=generator
            ),
        )
        first_stats = await first.run()
        restarted_sales = InMemorySalesRepository(sales_state)
        second = GmailJobProcessor(
            provider=MockGmailProvider([_support_email()]),
            bot=bot,
            chat_id=1,
            repository=InMemoryGmailRepository(gmail_state),
            sales_closer=SalesCloserService(
                restarted_sales, reply_generator=generator
            ),
        )
        second_stats = await second.run()

        self.assertEqual(bot.send_message.await_count, 1)
        self.assertEqual(await restarted_sales.list_opportunities(), [])
        self.assertEqual(await restarted_sales.list_pending_incoming_turns(NOW), [])
        self.assertEqual(await restarted_sales.list_pending_escalations(NOW), [])
        self.assertEqual(first_stats.qualified, 0)
        self.assertEqual(first_stats.ai_analyzed, 0)
        self.assertEqual(second_stats.qualified, 0)
        self.assertEqual(second_stats.ai_analyzed, 0)
        generator.assert_not_awaited()


class TestIntentPrecedenceV4(unittest.TestCase):
    def test_explicit_rejection_wins_over_price_in_four_languages(self):
        cases = (
            "We selected another freelancer because your price is too high.",
            "Мы выбрали другого исполнителя из-за вашей цены.",
            "Ми обрали іншого виконавця через вартість.",
            "Wybraliśmy innego wykonawcę ze względu na cenę.",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(classify_client_intent(text), ClientIntent.REJECTION)

    def test_real_price_objection_requires_objection_semantics(self):
        cases = (
            "Цена не подходит, можно немного дешевле?",
            "Бюджет ниже. Можете предложить другой вариант?",
            "The price is too high. Can you reduce it?",
            "Czy możecie obniżyć cenę?",
        )
        for text in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    classify_client_intent(text), ClientIntent.PRICE_OBJECTION
                )

    def test_budget_mentions_are_not_price_objections(self):
        expected = (
            ("The budget is approved and the contract is ready.", ClientIntent.SELECTED_OR_CONTRACT_STEP),
            ("Бюджет подтверждён, можем начинать.", ClientIntent.CLIENT_READY_TO_SELECT),
            ("Окончательный бюджет составляет 1 000 USD.", ClientIntent.UNKNOWN),
            ("Budget został zatwierdzony.", ClientIntent.UNKNOWN),
        )
        for text, intent in expected:
            with self.subTest(text=text):
                self.assertEqual(classify_client_intent(text), intent)


class TestCombinedRejectionFlowV4(unittest.IsolatedAsyncioTestCase):
    async def test_combined_rejection_is_lost_without_reply_or_follow_up(self):
        cases = (
            "We selected another freelancer because your price is too high.",
            "Мы выбрали другого исполнителя из-за вашей цены.",
            "Ми обрали іншого виконавця через вартість.",
            "Wybraliśmy innego wykonawcę ze względu na cenę.",
        )
        for index, text in enumerate(cases):
            with self.subTest(text=text):
                repository = InMemorySalesRepository({})
                generator = AsyncMock(side_effect=_reply_generator)
                service = SalesCloserService(
                    repository, reply_generator=generator, now=lambda: NOW
                )
                title = f"Combined rejection {index}"
                canonical = await _bid(service, f"91030{index}", title=title)
                result = await service.process_client_message(
                    _thread_email(
                        title,
                        f"88330{index}",
                        email_id=f"combined-rejection-{index}",
                        message=text,
                    )
                )
                self.assertEqual(result.opportunity.id, canonical.id)
                self.assertEqual(result.opportunity.state, OpportunityState.LOST.value)
                self.assertTrue(result.opportunity.do_not_follow_up)
                self.assertEqual(
                    result.opportunity.follow_up_status,
                    "DISABLED_CLIENT_REJECTION",
                )
                self.assertIsNone(result.reply_turn)
                generator.assert_not_awaited()


class TestOrphanRecoveryV4(unittest.IsolatedAsyncioTestCase):
    async def _setup_orphan(self, suffix: str):
        state: dict = {}
        repository = InMemorySalesRepository(state)
        generator = AsyncMock(side_effect=_reply_generator)
        service = SalesCloserService(
            repository, reply_generator=generator, now=lambda: NOW
        )
        project_id = f"9200{suffix}"
        canonical = await _bid(
            service, project_id, title=f"Known canonical {suffix}"
        )
        thread_id = f"8877{suffix}"
        result = await service.process_client_message(
            _thread_email(
                f"Unknown title {suffix}",
                thread_id,
                email_id=f"orphan-{suffix}",
            )
        )
        return state, repository, service, generator, canonical, result, thread_id

    async def test_atomic_merge_rehomes_history_and_is_restart_idempotent(self):
        (
            state,
            repository,
            service,
            generator,
            canonical,
            orphan_result,
            thread_id,
        ) = await self._setup_orphan("401")
        orphan = orphan_result.opportunity
        self.assertTrue(orphan.is_orphan)
        self.assertEqual(orphan.state, OpportunityState.NEEDS_CONTEXT.value)
        self.assertEqual(orphan.thread_id, thread_id)
        self.assertFalse(orphan.source_description)
        self.assertFalse(orphan.actual_submitted_price)
        self.assertFalse(orphan.actual_submitted_timeline)

        await repository.update_turn_fields(
            orphan_result.incoming_turn.id,
            {
                "acknowledged_at": NOW,
                "acknowledged_by_role": "ARTEM",
                "acknowledged_by_telegram_user_id": 202,
                "escalation_count": 1,
                "alert_state": "ESCALATED",
            },
        )
        human_request, _created = await repository.create_human_request(
            HumanInformationRequest(
                id="hir_v4_rehome",
                opportunity_id=orphan.id,
                source_turn_id=orphan_result.incoming_turn.id,
                fact_key="synthetic_audit_fact",
                intent=ClientIntent.CLARIFICATION.value,
                subject_fingerprint="v4",
                question="Synthetic audit-only question",
                asked_at=NOW,
            )
        )
        sync, _ = await service.begin_context_sync(
            orphan.id, actor_role="ARTEM", actor_telegram_user_id=202
        )
        copied = (
            f"Project ID: {canonical.project_id}\n"
            f"Thread ID: {thread_id}\n"
            f"{canonical.project_url}\n"
            f"https://freelancehunt.com/ua/mailbox/read/thread/{thread_id}#last-message\n"
            "Confirmed conversation history only."
        )
        reply_result = await service.import_context(
            copied, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertEqual(reply_result.opportunity.id, canonical.id)
        self.assertEqual(generator.await_count, 1)
        self.assertIsNotNone(reply_result.reply_turn)

        saved_canonical = await repository.get_opportunity(canonical.id)
        saved_orphan = await repository.get_opportunity(orphan.id)
        self.assertEqual(saved_canonical.thread_id, thread_id)
        self.assertEqual(saved_canonical.initial_proposal, canonical.initial_proposal)
        self.assertEqual(saved_canonical.actual_submitted_price, "1200 USD")
        self.assertEqual(saved_canonical.actual_submitted_timeline, "5 days")
        self.assertEqual(saved_orphan.state, OpportunityState.MERGED.value)
        self.assertEqual(saved_orphan.merged_into_opportunity_id, canonical.id)
        self.assertEqual(saved_orphan.merged_by_role, "ARTEM")
        self.assertFalse(saved_orphan.thread_id)
        self.assertTrue(saved_orphan.merge_evidence_json)

        canonical_turns = await repository.list_turns(canonical.id)
        moved = next(turn for turn in canonical_turns if turn.id == orphan_result.incoming_turn.id)
        self.assertEqual(moved.gmail_message_id, "orphan-401")
        self.assertEqual(moved.acknowledged_by_role, "ARTEM")
        self.assertEqual(moved.escalation_count, 1)
        self.assertEqual((await repository.get_human_request(human_request.id)).opportunity_id, canonical.id)
        self.assertEqual(state["context_syncs"][sync.id].opportunity_id, canonical.id)
        counts = await repository.pipeline_counts()
        self.assertEqual(counts[OpportunityState.MERGED.value], 0)
        self.assertEqual(sum(counts.values()), 1)

        bot = SimpleNamespace(send_message=AsyncMock(return_value=True))
        self.assertTrue(await send_sales_response_card(bot, 1, reply_result))
        self.assertEqual(bot.send_message.await_count, 1)

        restarted = SalesCloserService(
            InMemorySalesRepository(state),
            reply_generator=generator,
            now=lambda: NOW,
        )
        new_sync, redirected = await restarted.begin_context_sync(
            orphan.id, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertEqual(redirected.id, canonical.id)
        repeated = await restarted.import_context(
            copied, actor_role="ARTEM", actor_telegram_user_id=202
        )
        self.assertTrue(repeated.duplicate)
        self.assertEqual(generator.await_count, 1)
        self.assertEqual(state["context_syncs"][new_sync.id].opportunity_id, canonical.id)

        future_a, future_b = await asyncio.gather(
            restarted.process_client_message(
                _thread_email(
                    "Different future title A",
                    thread_id,
                    email_id="future-thread-a",
                )
            ),
            restarted.process_client_message(
                _thread_email(
                    "Different future title B",
                    thread_id,
                    email_id="future-thread-b",
                )
            ),
        )
        self.assertEqual({future_a.opportunity.id, future_b.opportunity.id}, {canonical.id})
        self.assertEqual(len(await repository.list_opportunities()), 2)

    async def test_conflicting_identity_and_sender_only_evidence_fail_closed(self):
        (
            _state,
            repository,
            service,
            _generator,
            canonical,
            orphan_result,
            thread_id,
        ) = await self._setup_orphan("402")
        await service.begin_context_sync(
            orphan_result.opportunity.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        with self.assertRaisesRegex(SalesCloserError, "more than one opportunity identity"):
            await service.import_context(
                (
                    f"Project ID: {canonical.project_id}\nThread ID: {thread_id}\n"
                    "https://freelancehunt.com/project/conflict/999999.html"
                ),
                actor_role="ARTEM",
                actor_telegram_user_id=202,
            )
        self.assertEqual(
            (await repository.get_opportunity(orphan_result.opportunity.id)).state,
            OpportunityState.NEEDS_CONTEXT.value,
        )
        await service.cancel_context_sync(202, actor_role="ARTEM")
        await service.begin_context_sync(
            orphan_result.opportunity.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        with self.assertRaisesRegex(SalesCloserError, "does not identify"):
            await service.import_context(
                "Synthetic Alex copied this similar-looking conversation.",
                actor_role="ARTEM",
                actor_telegram_user_id=202,
            )
        self.assertEqual(
            (await repository.get_opportunity(orphan_result.opportunity.id)).state,
            OpportunityState.NEEDS_CONTEXT.value,
        )

    async def test_exact_reply_reference_can_identify_the_canonical_target(self):
        (
            _state,
            repository,
            service,
            _generator,
            canonical,
            orphan_result,
            thread_id,
        ) = await self._setup_orphan("403")
        reference = "<canonical-v4-403@freelancehunt.com>"
        canonical = await repository.update_opportunity_fields(
            canonical.id, {"reply_reference_id": reference}
        )
        await service.begin_context_sync(
            orphan_result.opportunity.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        result = await service.import_context(
            f"Thread ID: {thread_id}\nReply reference: {reference}",
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.assertEqual(result.opportunity.id, canonical.id)
        self.assertEqual(
            (await repository.get_opportunity(orphan_result.opportunity.id)).state,
            OpportunityState.MERGED.value,
        )


class TestAdditiveMergeSchemaV4(unittest.TestCase):
    def test_merge_schema_is_additive_and_restart_safe(self):
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
            "IS_ORPHAN",
            "MERGED_INTO_OPPORTUNITY_ID",
            "MERGED_AT",
            "MERGED_BY_ROLE",
            "MERGED_BY_TELEGRAM_USER_ID",
            "MERGE_EVIDENCE_JSON",
        ):
            with self.subTest(column=column):
                self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", statements)
        self.assertNotIn("DROP TABLE", statements)
        self.assertNotIn("DELETE FROM", statements)
