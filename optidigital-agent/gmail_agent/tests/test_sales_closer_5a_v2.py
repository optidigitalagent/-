"""Release 5A correction-cycle V2 blocker regressions; all data is synthetic."""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gmail_agent.processor import GmailJobProcessor, ProcessorStats
from gmail_agent.quality_gate import (
    approved_evidence_text,
    contains_external_contact,
    contains_unsupported_case_or_capability_claim,
)
from gmail_agent.sales_closer import (
    ClientIntent,
    SalesCloserError,
    SalesCloserService,
    classify_client_intent,
    reply_quality_errors,
)
from gmail_agent.sales_decisions import access_or_contract_errors
from gmail_agent.sales_storage import (
    IllegalTransitionError,
    InMemorySalesRepository,
    OpportunityState,
)
from gmail_agent.storage import InMemoryGmailRepository
from gmail_agent.tests.test_quality_gate_v2 import stored
from gmail_agent.tests.test_quality_gate_v2 import validated as stage4_validated
from gmail_agent.tests.test_sales_closer_5a import NOW, _email, _job, _reply_generator
from gmail_agent.telegram_roles import (
    TelegramAuthorizationError,
    TelegramRole,
    authorize_telegram_actor,
)
from gmail_agent.telegram_notifier import format_job_card_parts


class V2Case(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state: dict = {}
        self.repository = InMemorySalesRepository(self.state)
        self.generator = AsyncMock(side_effect=_reply_generator)
        self.service = SalesCloserService(
            self.repository, reply_generator=self.generator, now=lambda: NOW
        )

    async def seed(self, project_id: str = "910001"):
        opportunity = await self.service.ensure_from_validated_job(_job(project_id))
        self.assertIsNotNone(opportunity)
        return opportunity

    async def bid(self, project_id: str = "910001"):
        opportunity = await self.seed(project_id)
        opportunity, _confirmation, _created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1 200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW - timedelta(minutes=3),
        )
        return opportunity

    async def answer(self, body: str, answer: str, *, project_id: str = "910001"):
        await self.bid(project_id)
        waiting = await self.service.process_client_message(
            _email(project_id, body, email_id=f"human-{project_id}")
        )
        return await self.service.answer_human_request(
            waiting.human_request.id,
            answer,
            actor_role="VADIM",
            actor_telegram_user_id=303,
        )


class TestTelegramActorAuthorizationV2(V2Case):
    async def test_adult_owner_command_executed_by_artem_is_blocked(self):
        configured = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=303,
        )
        with self.assertRaisesRegex(TelegramAuthorizationError, "not allowed"):
            authorize_telegram_actor(
                202,
                "artem",
                configured,
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=("TELEGRAM_ADULT_OWNER_USER_ID",),
            )

    async def test_answer_lead_executed_by_unknown_user_is_blocked(self):
        configured = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=303,
        )
        with self.assertRaisesRegex(TelegramAuthorizationError, "not allowed"):
            authorize_telegram_actor(
                999,
                "unknown",
                configured,
                allowed_roles=(TelegramRole.ARTEM, TelegramRole.VADIM),
                required_settings=(
                    "TELEGRAM_ARTEM_USER_ID", "TELEGRAM_VADIM_USER_ID"
                ),
            )

    def test_missing_role_setting_fails_closed_with_exact_name(self):
        settings = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=None,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=303,
        )
        with self.assertRaisesRegex(
            TelegramAuthorizationError, "TELEGRAM_ADULT_OWNER_USER_ID"
        ):
            authorize_telegram_actor(
                101,
                "owner",
                settings,
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=("TELEGRAM_ADULT_OWNER_USER_ID",),
            )

    def test_duplicate_role_ids_fail_closed(self):
        configured = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=101,
            TELEGRAM_VADIM_USER_ID=303,
        )
        with self.assertRaisesRegex(
            TelegramAuthorizationError,
            "TELEGRAM_ADULT_OWNER_USER_ID, TELEGRAM_ARTEM_USER_ID",
        ):
            authorize_telegram_actor(
                101,
                "ambiguous",
                configured,
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=("TELEGRAM_ADULT_OWNER_USER_ID",),
            )

    async def test_actual_actor_role_and_id_persist(self):
        opportunity = await self.seed()
        saved, confirmation, _created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        transitions = await self.repository.list_transitions(saved.id)
        self.assertEqual(confirmation.actor_role, "ADULT_OWNER")
        self.assertEqual(confirmation.actor_telegram_user_id, 101)
        bid_transition = next(
            item
            for item in transitions
            if item.new_state == OpportunityState.BID_SUBMITTED.value
        )
        self.assertEqual(bid_transition.actor_role, "ADULT_OWNER")
        self.assertEqual(bid_transition.actor_telegram_user_id, 101)


class TestExactVersionAndStaleReplyV2(V2Case):
    def test_bid_package_card_shows_exact_proposal_version_command(self):
        analysis = stage4_validated()
        text = "\n".join(format_job_card_parts(analysis))
        self.assertIn(
            f"{analysis.proposal_version} | &lt;price&gt; | &lt;timeline&gt;", text
        )

    async def test_mark_bid_sent_exact_version_passes_with_canonical_terms(self):
        opportunity = await self.seed()
        saved, confirmation, created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1 200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        self.assertTrue(created)
        self.assertEqual(saved.actual_submitted_price, "1200 USD")
        self.assertEqual(json.loads(confirmation.money_terms_json)["currency"], "USD")

    async def test_proposal_replacement_blocks_old_version(self):
        original = await self.seed()
        replacement = _job()
        replacement.proposal_draft = "Replacement exact proposal body."
        replacement.proposal_version = "pqg-v3-replacement"
        import hashlib

        replacement.proposal_content_sha256 = hashlib.sha256(
            replacement.proposal_draft.encode()
        ).hexdigest()
        current = await self.service.ensure_from_validated_job(replacement)
        with self.assertRaisesRegex(SalesCloserError, "proposal version is stale"):
            await self.service.mark_bid_sent(
                original.id,
                original.proposal_version,
                "1200 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=101,
            )
        persisted = await self.repository.get_opportunity(current.id)
        self.assertEqual(persisted.state, OpportunityState.PROPOSAL_READY.value)

    async def test_newer_incoming_blocks_old_reply_and_names_regeneration(self):
        await self.bid()
        first = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="incoming-old")
        )
        second = await self.service.process_client_message(
            _email(
                "910001",
                "Please clarify authentication headers.",
                email_id="incoming-new",
            )
        )
        with self.assertRaisesRegex(
            SalesCloserError,
            rf"{second.incoming_turn.id}.*?/regenerate_lead {second.opportunity.id}",
        ):
            await self.service.mark_reply_sent(
                first.opportunity.id,
                first.reply_turn.reply_version,
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=101,
            )
        stale = await self.repository.get_turn(first.reply_turn.id)
        self.assertEqual(stale.direction, "OUTGOING_SUPERSEDED")
        self.assertNotEqual(second.opportunity.state, OpportunityState.WAITING_CLIENT.value)

    async def test_two_concurrent_incoming_turns_get_distinct_versions(self):
        await self.bid()

        async def yielding_generator(context, client, errors):
            await asyncio.sleep(0)
            return await _reply_generator(context, client, errors)

        self.service._reply_generator = yielding_generator
        results = await asyncio.gather(
            self.service.process_client_message(
                _email("910001", "Please clarify authentication A.", email_id="race-a")
            ),
            self.service.process_client_message(
                _email("910001", "Please clarify authentication B.", email_id="race-b")
            ),
        )
        turns = await self.repository.list_turns(results[0].opportunity.id)
        versions = {turn.reply_version for turn in turns if turn.reply_version}
        self.assertEqual(versions, {"r1", "r2"})
        self.assertEqual(
            sum(turn.direction == "OUTGOING_DRAFT" for turn in turns), 1
        )


class TestTurnScopedDecisionsV2(V2Case):
    async def test_hubspot_yes_does_not_authorize_shopify(self):
        await self.bid()
        hubspot = await self.service.process_client_message(
            _email("910001", "Can you support the HubSpot API?", email_id="hubspot")
        )
        await self.service.answer_human_request(
            hubspot.human_request.id,
            "YES",
            actor_role="VADIM",
            actor_telegram_user_id=303,
        )
        shopify = await self.service.process_client_message(
            _email("910001", "Can you support the Shopify API?", email_id="shopify")
        )
        self.assertIsNotNone(shopify.human_request)
        self.assertNotEqual(
            shopify.human_request.subject_fingerprint,
            hubspot.human_request.subject_fingerprint,
        )

    async def test_technical_no_cannot_become_capability_yes(self):
        result = await self.answer("Can you support the HubSpot API?", "NO")
        self.assertIn("cannot confirm", result.reply_turn.content.casefold())
        self.assertNotIn("we can confirm", result.reply_turn.content.casefold())

    async def test_need_docs_produces_one_safe_clarification(self):
        result = await self.answer("Can you support the HubSpot API?", "NEED_DOCS")
        self.assertEqual(result.reply_turn.content.count("?"), 1)
        self.assertIn("documentation", result.reply_turn.content.casefold())

    async def test_separate_scope_requires_application_owned_paid_wording(self):
        result = await self.answer(
            "Please also add another dashboard.", "SEPARATE_PAID_ESTIMATE"
        )
        value = result.reply_turn.content.casefold()
        self.assertIn("outside the current scope", value)
        self.assertIn("separate paid estimate", value)

    async def test_include_scope_is_blocked_without_explicit_approval(self):
        opportunity = await self.bid()
        errors = reply_quality_errors(
            "Sure, we will include the additional dashboard.",
            opportunity=opportunity,
            latest_message="Please add the additional dashboard.",
            language="en",
            intent=ClientIntent.SCOPE_CHANGE,
            context_complete=True,
        )
        self.assertIn("scope_inclusion_without_explicit_approval", errors)

    async def test_call_reply_matches_exact_approved_window(self):
        result = await self.answer(
            "Can we schedule a call?",
            "APPROVED_WINDOWS | 2026-09-04 10:00-10:30 Europe/Kyiv",
        )
        self.assertIn(
            "2026-09-04 10:00-10:30 Europe/Kyiv", result.reply_turn.content
        )

    async def test_price_and_timeline_match_canonical_terms(self):
        price = await self.answer(
            "The price is too expensive.",
            "COUNTER_PRICE | 950 USD",
            project_id="920101",
        )
        timeline = await self.answer(
            "Can you deliver sooner?",
            "EARLIEST_TIMELINE | 3 days",
            project_id="920102",
        )
        self.assertIn("950 USD", price.reply_turn.content)
        self.assertIn("3 days", timeline.reply_turn.content)

    async def test_no_direct_case_never_claims_completed_client_case(self):
        job = _job()
        job.selected_evidence = ""
        job.evidence_case_id = ""
        opportunity = await self.service.ensure_from_validated_job(job)
        await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
        )
        waiting = await self.service.process_client_message(
            _email("910001", "Please show a direct client case.", email_id="proof-none")
        )
        result = await self.service.answer_human_request(
            waiting.human_request.id,
            "NO_DIRECT_CASE",
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.assertIn("do not have a confirmed direct client case", result.reply_turn.content)


class TestSafetyAndStatesV2(V2Case):
    async def test_access_reply_never_requests_password_otp_or_api_secret(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email(
                "910001",
                "Please use password: topsecret, OTP: 123456, API secret: abcdef.",
                email_id="access-secret",
            )
        )
        reply = result.reply_turn.content
        self.assertEqual(access_or_contract_errors(reply, "ACCESS_REQUEST"), [])
        self.assertIn("must not be sent", reply)
        self.assertNotIn("topsecret", result.incoming_turn.content)
        self.assertNotIn("123456", result.incoming_turn.content)

    def test_word_safe_in_technical_message_is_not_contract_intent(self):
        self.assertEqual(
            classify_client_intent("Is this API safe for retry handling?"),
            ClientIntent.TECHNICAL_QUESTION,
        )

    async def test_ready_to_start_does_not_become_formal_selected(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "We choose you and are ready to start.", email_id="ready")
        )
        self.assertEqual(result.opportunity.state, OpportunityState.SELECTION_REVIEW.value)

    async def test_contract_reply_cannot_accept_terms(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "The contract was created.", email_id="contract")
        )
        self.assertEqual(result.opportunity.state, OpportunityState.CONTRACT_REVIEW.value)
        self.assertEqual(
            access_or_contract_errors(
                result.reply_turn.content, "SELECTED_OR_CONTRACT_STEP"
            ),
            [],
        )
        self.assertNotIn("we accept", result.reply_turn.content.casefold())

    def test_stage4_contact_guard_blocks_all_named_surfaces(self):
        samples = (
            "example.com/contact",
            "+1 (202) 555-0199",
            "Discord user name",
            "join our Slack",
            "linkedin.com/in/person",
            "Instagram @person",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(contains_external_contact(sample))

    def test_model_authored_amplified_case_claim_is_blocked(self):
        self.assertTrue(
            contains_unsupported_case_or_capability_claim(
                "We previously delivered this integration for 40% growth."
            )
        )

    async def test_exact_application_owned_evidence_clause_passes(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please show a portfolio example.", email_id="proof-exact")
        )
        exact = approved_evidence_text("GMAIL_JOB_AGENT", "en")
        self.assertIn(exact, result.reply_turn.content)
        self.assertEqual(result.validation_errors, ())

    async def test_illegal_terminal_transition_is_blocked(self):
        opportunity = await self.seed()
        terminal = await self.repository.transition(
            opportunity.id,
            OpportunityState.CLOSED.value,
            source="synthetic",
            reason="test terminal",
            actor="system",
        )
        with self.assertRaises(IllegalTransitionError):
            await self.repository.transition(
                terminal.id,
                OpportunityState.NEGOTIATING.value,
                source="synthetic",
                reason="illegal reopen",
                actor="system",
            )

    async def test_late_terminal_message_is_audited_without_reopening(self):
        opportunity = await self.seed()
        await self.repository.transition(
            opportunity.id,
            OpportunityState.CLOSED.value,
            source="synthetic",
            reason="terminal",
            actor="system",
        )
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="late-terminal")
        )
        self.assertEqual(result.opportunity.state, OpportunityState.CLOSED.value)
        self.assertIsNone(result.reply_turn)
        self.assertIn("terminal_state_manual_review", result.validation_errors)


class TestContextAlertsAndResilienceV2(V2Case):
    async def test_needs_context_sync_creates_validated_reply_once(self):
        await self.bid()
        initial = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="sync-incoming")
        )
        await self.repository.update_turn_fields(
            initial.reply_turn.id, {"direction": "OUTGOING_SUPERSEDED"}
        )
        await self.repository.transition(
            initial.opportunity.id,
            OpportunityState.CLIENT_REPLIED.value,
            source="synthetic",
            reason="simulate context loss",
            actor="system",
        )
        await self.repository.transition(
            initial.opportunity.id,
            OpportunityState.NEEDS_CONTEXT.value,
            source="synthetic",
            reason="missing exact copied thread",
            actor="system",
        )
        await self.service.begin_context_sync(
            initial.opportunity.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.generator.reset_mock()
        result = await self.service.import_context(
            "Thread context\nhttps://freelancehunt.com/project/synthetic/910001.html\n"
            "password: topsecret",
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        self.assertIsNotNone(result.reply_turn)
        self.assertEqual(result.opportunity.state, OpportunityState.NEGOTIATING.value)
        self.assertEqual(self.generator.await_count, 1)
        imported = [
            turn
            for turn in await self.repository.list_turns(initial.opportunity.id)
            if turn.source == "OWNER_COPIED_THREAD"
        ]
        self.assertEqual(imported[0].direction, "UNKNOWN_DIRECTION")
        self.assertNotIn("topsecret", imported[0].content)

    async def test_context_sync_rejects_two_opportunity_identities(self):
        await self.bid()
        initial = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="sync-conflict")
        )
        await self.service.begin_context_sync(
            initial.opportunity.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        with self.assertRaisesRegex(SalesCloserError, "more than one opportunity"):
            await self.service.import_context(
                "https://freelancehunt.com/project/a/910001.html\n"
                "https://freelancehunt.com/project/b/910002.html",
                actor_role="ARTEM",
                actor_telegram_user_id=202,
            )

    async def test_five_minute_alert_fires_exactly_once_and_survives_restart(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="alert")
        )
        await self.service.mark_notified(result.incoming_turn.id)
        restarted = SalesCloserService(
            InMemorySalesRepository(self.state),
            reply_generator=_reply_generator,
            now=lambda: NOW + timedelta(minutes=6),
        )
        pending = await restarted.pending_escalations()
        self.assertEqual([turn.id for turn in pending], [result.incoming_turn.id])
        await restarted.mark_escalated(result.incoming_turn.id)
        self.assertEqual(await restarted.pending_escalations(), [])
        persisted = await restarted.repository.get_turn(result.incoming_turn.id)
        self.assertEqual(persisted.escalation_count, 1)

    async def test_ack_cancels_escalation(self):
        await self.bid()
        result = await self.service.process_client_message(
            _email("910001", "Please clarify authentication.", email_id="ack")
        )
        await self.service.mark_notified(result.incoming_turn.id)
        await self.service.acknowledge_lead(
            result.incoming_turn.id,
            actor_role="ARTEM",
            actor_telegram_user_id=202,
        )
        later = SalesCloserService(
            InMemorySalesRepository(self.state),
            reply_generator=_reply_generator,
            now=lambda: NOW + timedelta(minutes=10),
        )
        self.assertEqual(await later.pending_escalations(), [])

    async def test_sales_storage_failure_keeps_stage4_card_and_retryable_state(self):
        repository = InMemoryGmailRepository()
        job = stored(status="queued")
        await repository.save_job(job)
        bot = SimpleNamespace(send_message=AsyncMock())
        failing_sales = SimpleNamespace(
            ensure_from_validated_job=AsyncMock(side_effect=RuntimeError("temporary"))
        )
        processor = GmailJobProcessor(
            provider=SimpleNamespace(),
            bot=bot,
            chat_id=1,
            repository=repository,
            sales_closer=failing_sales,
        )
        stats = ProcessorStats()
        attempted = await processor.deliver_validated_proposal_version(
            processor._candidate_from_job(job),
            job,
            stats,
            live_status_already_checked=True,
        )
        self.assertTrue(attempted)
        sent_text = "\n".join(
            call.kwargs["text"] for call in bot.send_message.await_args_list
        )
        self.assertIn("SALES TRACKING TEMPORARILY UNAVAILABLE", sent_text)
        persisted = await repository.get_job(job.stable_key)
        self.assertEqual(persisted.status, "sales_tracking_pending")
        first_send_count = bot.send_message.await_count
        retried = await processor.deliver_validated_proposal_version(
            processor._candidate_from_job(persisted),
            persisted,
            stats,
            live_status_already_checked=True,
        )
        self.assertFalse(retried)
        self.assertEqual(bot.send_message.await_count, first_send_count)

    async def test_dialogue_failure_sends_sanitized_fallback_only_and_retries(self):
        email = _email(
            "910001",
            "Password: topsecret OTP: 123456 API secret: abcdef",
            email_id="dialogue-failure",
        )
        provider = SimpleNamespace(mark_as_processed=AsyncMock())
        bot = SimpleNamespace(send_message=AsyncMock())
        repository = InMemoryGmailRepository()
        failing_sales = SimpleNamespace(
            process_client_message=AsyncMock(side_effect=RuntimeError("temporary"))
        )
        processor = GmailJobProcessor(
            provider=provider,
            bot=bot,
            chat_id=1,
            repository=repository,
            sales_closer=failing_sales,
        )
        stats = ProcessorStats()
        attempted = await processor._process_sales_private_message(
            email, stats, allow_send=True
        )
        self.assertTrue(attempted)
        text = bot.send_message.await_args.kwargs["text"]
        self.assertIn("SALES TRACKING UNAVAILABLE", text)
        self.assertNotIn("topsecret", text)
        self.assertNotIn("123456", text)
        self.assertNotIn("Copy-ready", text)
        provider.mark_as_processed.assert_not_awaited()
        self.assertTrue(
            await repository.is_processed(
                "sales-fallback-notified:"
                + __import__("hashlib").sha256(email.id.encode()).hexdigest()
            )
        )


if __name__ == "__main__":
    unittest.main()
