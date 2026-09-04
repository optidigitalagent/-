"""Issue #17 shared Telegram operator hotfix regressions; all data is synthetic."""

from __future__ import annotations

import ast
import hashlib
import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from gmail_agent.sales_closer import SalesCloserError, SalesCloserService
from gmail_agent.sales_storage import InMemorySalesRepository, OpportunityState
from gmail_agent.telegram_notifier import TELEGRAM_TEXT_LIMIT, format_job_card_parts
from gmail_agent.telegram_roles import (
    FACT_SOURCE_ATTESTATION_VERSION,
    OWNER_ATTESTATION_VERSION,
    SEPARATE_ROLE_IDENTITY_ASSURANCE,
    SHARED_IDENTITY_ASSURANCE,
    TelegramAuthorizationError,
    TelegramOperatorMode,
    TelegramRole,
    authorize_telegram_actor,
    format_whoami,
    resolve_telegram_actor,
    validate_operator_configuration,
)
from gmail_agent.tests.test_quality_gate_v2 import validated as stage4_validated
from gmail_agent.tests.test_sales_closer_5a import NOW, _email, _job, _reply_generator

SHARED_ID = 987654321


def shared_settings(**overrides):
    values = {
        "TELEGRAM_OPERATOR_MODE": "SINGLE_SHARED_OPERATOR",
        "TELEGRAM_SHARED_OPERATOR_USER_ID": SHARED_ID,
        "TELEGRAM_ADULT_OWNER_USER_ID": None,
        "TELEGRAM_ARTEM_USER_ID": None,
        "TELEGRAM_VADIM_USER_ID": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def separate_settings(**overrides):
    values = {
        "TELEGRAM_OPERATOR_MODE": "SEPARATE_ROLES",
        "TELEGRAM_SHARED_OPERATOR_USER_ID": None,
        "TELEGRAM_ADULT_OWNER_USER_ID": 101,
        "TELEGRAM_ARTEM_USER_ID": 202,
        "TELEGRAM_VADIM_USER_ID": 303,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def shared_actor(role: TelegramRole, version: str):
    return authorize_telegram_actor(
        SHARED_ID,
        "shared",
        shared_settings(),
        allowed_roles=(role,),
        required_settings=(),
        claimed_role=role,
        attestation_version=version,
        claimed_at=NOW,
    )


def audit_kwargs(actor):
    return {
        "operator_mode": actor.operator_mode.value,
        "identity_assurance": actor.identity_assurance,
        "claimed_actor_role": actor.claimed_actor_role,
        "attestation_version": actor.attestation_version,
        "claimed_at": actor.claimed_at,
    }


class TestSharedOperatorConfiguration(unittest.TestCase):
    def test_shared_mode_resolves_only_configured_account(self):
        actor = resolve_telegram_actor(SHARED_ID, "shared", shared_settings())
        self.assertEqual(actor.role, TelegramRole.SHARED_OPERATOR)
        self.assertEqual(actor.operator_mode, TelegramOperatorMode.SINGLE_SHARED_OPERATOR)

    def test_shared_whoami_has_required_truthful_labels_and_no_numeric_id(self):
        text = format_whoami(
            resolve_telegram_actor(SHARED_ID, "shared", shared_settings())
        )
        self.assertIn("Operator mode: <b>SINGLE_SHARED_OPERATOR</b>", text)
        self.assertIn("Telegram account: <b>configured shared operator</b>", text)
        self.assertIn("Identity assurance: <b>SELF-ATTESTED ACTION ROLE</b>", text)
        self.assertNotIn(str(SHARED_ID), text)

    def test_unknown_shared_account_is_read_only_and_not_disclosed(self):
        actor = resolve_telegram_actor(111222333, "unknown", shared_settings())
        text = format_whoami(actor)
        self.assertEqual(actor.role, TelegramRole.READ_ONLY_MEMBER)
        self.assertIn("read-only / not configured", text)
        self.assertNotIn("111222333", text)

    def test_unknown_shared_account_cannot_authorize_state_write(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "not allowed"):
            authorize_telegram_actor(
                111222333,
                "unknown",
                shared_settings(),
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=(),
                allow_shared_operator=True,
            )

    def test_missing_shared_id_fails_closed(self):
        with self.assertRaisesRegex(
            TelegramAuthorizationError, "TELEGRAM_SHARED_OPERATOR_USER_ID"
        ):
            validate_operator_configuration(
                shared_settings(TELEGRAM_SHARED_OPERATOR_USER_ID=None)
            )

    def test_zero_negative_boolean_and_malformed_shared_ids_fail_closed(self):
        for value in (0, -1, True, "987654321"):
            with self.subTest(value=value), self.assertRaises(
                TelegramAuthorizationError
            ):
                validate_operator_configuration(
                    shared_settings(TELEGRAM_SHARED_OPERATOR_USER_ID=value)
                )

    def test_unknown_operator_mode_fails_closed(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "Unknown"):
            validate_operator_configuration(
                shared_settings(TELEGRAM_OPERATOR_MODE="SHAREDISH")
            )

    def test_shared_plus_legacy_role_configuration_conflicts(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "Conflicting"):
            validate_operator_configuration(
                shared_settings(TELEGRAM_ARTEM_USER_ID=SHARED_ID)
            )

    def test_separate_plus_shared_configuration_conflicts(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "Conflicting"):
            validate_operator_configuration(
                separate_settings(TELEGRAM_SHARED_OPERATOR_USER_ID=SHARED_ID)
            )

    def test_missing_mode_keeps_backward_compatible_separate_roles(self):
        settings = SimpleNamespace(
            TELEGRAM_ADULT_OWNER_USER_ID=101,
            TELEGRAM_ARTEM_USER_ID=202,
            TELEGRAM_VADIM_USER_ID=303,
        )
        actor = authorize_telegram_actor(
            202,
            "artem",
            settings,
            allowed_roles=(TelegramRole.ARTEM,),
            required_settings=(),
        )
        self.assertEqual(actor.role, TelegramRole.ARTEM)
        self.assertEqual(actor.operator_mode, TelegramOperatorMode.SEPARATE_ROLES)

    def test_duplicate_separate_role_ids_still_fail_closed(self):
        settings = separate_settings(TELEGRAM_ARTEM_USER_ID=101)
        with self.assertRaisesRegex(TelegramAuthorizationError, "Conflicting"):
            authorize_telegram_actor(
                101,
                "ambiguous",
                settings,
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=("TELEGRAM_ADULT_OWNER_USER_ID",),
            )

    def test_malformed_separate_role_setting_fails_closed_globally(self):
        with self.assertRaisesRegex(
            TelegramAuthorizationError, "TELEGRAM_VADIM_USER_ID"
        ):
            validate_operator_configuration(
                separate_settings(TELEGRAM_VADIM_USER_ID=-303)
            )

    def test_shared_state_write_requires_explicit_action_role(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "explicitly attest"):
            authorize_telegram_actor(
                SHARED_ID,
                "shared",
                shared_settings(),
                allowed_roles=(TelegramRole.ADULT_OWNER,),
                required_settings=(),
            )

    def test_owner_claim_is_self_attested_not_technically_verified(self):
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        self.assertEqual(actor.role, TelegramRole.ADULT_OWNER)
        self.assertEqual(actor.claimed_actor_role, "ADULT_OWNER")
        self.assertEqual(actor.identity_assurance, SHARED_IDENTITY_ASSURANCE)
        self.assertEqual(actor.user_id, SHARED_ID)
        self.assertEqual(actor.claimed_at, NOW)

    def test_shared_generic_commands_use_neutral_operator_role(self):
        actor = authorize_telegram_actor(
            SHARED_ID,
            "shared",
            shared_settings(),
            allowed_roles=(TelegramRole.ADULT_OWNER, TelegramRole.ARTEM),
            required_settings=(),
            allow_shared_operator=True,
        )
        self.assertEqual(actor.role, TelegramRole.SHARED_OPERATOR)
        self.assertEqual(actor.claimed_actor_role, "")

    def test_invalid_shared_fact_source_role_fails_closed(self):
        with self.assertRaisesRegex(TelegramAuthorizationError, "not allowed"):
            authorize_telegram_actor(
                SHARED_ID,
                "shared",
                shared_settings(),
                allowed_roles=(TelegramRole.ARTEM, TelegramRole.VADIM),
                required_settings=(),
                claimed_role=TelegramRole.ADULT_OWNER,
                attestation_version=FACT_SOURCE_ATTESTATION_VERSION,
                claimed_at=NOW,
            )

    def test_configuration_errors_never_echo_secret_numeric_id(self):
        try:
            validate_operator_configuration(
                shared_settings(TELEGRAM_ADULT_OWNER_USER_ID=SHARED_ID)
            )
        except TelegramAuthorizationError as exc:
            self.assertNotIn(str(SHARED_ID), str(exc))
        else:
            self.fail("conflicting configuration was accepted")


class SharedServiceCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state: dict = {}
        self.repository = InMemorySalesRepository(self.state)
        self.generator = AsyncMock(side_effect=_reply_generator)
        self.service = SalesCloserService(
            self.repository, reply_generator=self.generator, now=lambda: NOW
        )

    async def seed(self, project_id: str = "980001"):
        opportunity = await self.service.ensure_from_validated_job(_job(project_id))
        self.assertIsNotNone(opportunity)
        return opportunity

    async def bid(self, project_id: str = "980001"):
        opportunity = await self.seed(project_id)
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        return await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
            confirmed_at=NOW,
            **audit_kwargs(actor),
        )

    async def reply_draft(self, project_id: str = "980001"):
        opportunity, _confirmation, _created = await self.bid(project_id)
        result = await self.service.process_client_message(
            _email(project_id, "Please clarify authentication.", email_id=f"reply-{project_id}")
        )
        self.assertIsNotNone(result.reply_turn)
        return opportunity, result

    async def human_request(self, project_id: str = "980001"):
        await self.bid(project_id)
        result = await self.service.process_client_message(
            _email(
                project_id,
                "Can you support the HubSpot API?",
                email_id=f"human-{project_id}",
            )
        )
        self.assertIsNotNone(result.human_request)
        return result

    async def test_bid_preview_is_read_only_and_canonical(self):
        opportunity = await self.seed()
        preview, price, timeline = await self.service.preview_bid_confirmation(
            opportunity.id, opportunity.proposal_version, "1 200 USD", "5 days"
        )
        persisted = await self.repository.get_opportunity(opportunity.id)
        self.assertEqual(preview.proposal_content_sha256, opportunity.proposal_content_sha256)
        self.assertEqual((price, timeline), ("1200 USD", "5 days"))
        self.assertEqual(persisted.state, OpportunityState.PROPOSAL_READY.value)
        self.assertEqual(self.state["confirmations"], {})

    async def test_shared_bid_without_owner_attestation_is_rejected_without_state_change(self):
        opportunity = await self.seed()
        with self.assertRaisesRegex(SalesCloserError, "attestation"):
            await self.service.mark_bid_sent(
                opportunity.id,
                opportunity.proposal_version,
                "1200 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role="ADULT_OWNER",
                claimed_at=NOW,
            )
        self.assertEqual(
            (await self.repository.get_opportunity(opportunity.id)).state,
            OpportunityState.PROPOSAL_READY.value,
        )

    async def test_shared_bid_requires_claim_timestamp(self):
        opportunity = await self.seed()
        with self.assertRaisesRegex(SalesCloserError, "timestamp"):
            await self.service.mark_bid_sent(
                opportunity.id,
                opportunity.proposal_version,
                "1200 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role="ADULT_OWNER",
                attestation_version=OWNER_ATTESTATION_VERSION,
            )

    async def test_valid_shared_bid_persists_exact_audit_and_terms(self):
        opportunity, confirmation, created = await self.bid()
        self.assertTrue(created)
        self.assertEqual(opportunity.state, OpportunityState.BID_SUBMITTED.value)
        self.assertEqual(confirmation.operator_mode, "SINGLE_SHARED_OPERATOR")
        self.assertEqual(confirmation.identity_assurance, SHARED_IDENTITY_ASSURANCE)
        self.assertEqual(confirmation.claimed_actor_role, "ADULT_OWNER")
        self.assertEqual(confirmation.attestation_version, OWNER_ATTESTATION_VERSION)
        self.assertEqual(confirmation.actual_telegram_user_id, SHARED_ID)
        self.assertEqual(confirmation.proposal_version, opportunity.proposal_version)
        self.assertEqual(confirmation.content_sha256, opportunity.proposal_content_sha256)
        self.assertTrue(confirmation.money_terms_json)
        self.assertTrue(confirmation.timeline_terms_json)
        self.assertEqual(confirmation.action_confirmed_at, NOW)

    async def test_shared_attestation_still_rejects_stale_proposal(self):
        original = await self.seed("980009")
        replacement = _job("980009")
        replacement.proposal_draft = "Replacement exact proposal body."
        replacement.proposal_version = "pqg-v3-shared-replacement"
        replacement.proposal_content_sha256 = hashlib.sha256(
            replacement.proposal_draft.encode()
        ).hexdigest()
        current = await self.service.ensure_from_validated_job(replacement)
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        with self.assertRaisesRegex(SalesCloserError, "stale"):
            await self.service.mark_bid_sent(
                original.id,
                original.proposal_version,
                "1200 USD",
                "5 days",
                actor_role=actor.role.value,
                actor_telegram_user_id=actor.user_id,
                confirmed_at=NOW,
                **audit_kwargs(actor),
            )
        self.assertEqual(current.state, OpportunityState.PROPOSAL_READY.value)
        self.assertEqual(self.state["confirmations"], {})

    async def test_duplicate_shared_bid_is_idempotent_with_same_audit(self):
        opportunity, first, created = await self.bid()
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        _saved, second, duplicated = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
            confirmed_at=NOW,
            **audit_kwargs(actor),
        )
        self.assertTrue(created)
        self.assertFalse(duplicated)
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.identity_assurance, SHARED_IDENTITY_ASSURANCE)

    async def test_legacy_separate_confirmation_remains_restart_idempotent(self):
        opportunity = await self.seed("980010")
        _saved, first, created = await self.service.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
        )
        legacy = self.state["confirmations"][first.id]
        legacy.claimed_actor_role = ""
        legacy.actual_telegram_user_id = None
        restarted = SalesCloserService(
            InMemorySalesRepository(self.state),
            reply_generator=self.generator,
            now=lambda: NOW,
        )
        _saved, repeated, duplicated = await restarted.mark_bid_sent(
            opportunity.id,
            opportunity.proposal_version,
            "1200 USD",
            "5 days",
            actor_role="ADULT_OWNER",
            actor_telegram_user_id=101,
            confirmed_at=NOW,
        )
        self.assertTrue(created)
        self.assertFalse(duplicated)
        self.assertEqual(repeated.id, first.id)

    async def test_shared_reply_without_owner_attestation_is_rejected(self):
        opportunity, result = await self.reply_draft()
        with self.assertRaisesRegex(SalesCloserError, "attestation"):
            await self.service.mark_reply_sent(
                opportunity.id,
                result.reply_turn.reply_version,
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role="ADULT_OWNER",
                claimed_at=NOW,
            )
        self.assertNotEqual(
            (await self.repository.get_opportunity(opportunity.id)).state,
            OpportunityState.WAITING_CLIENT.value,
        )

    async def test_reply_preview_is_read_only_and_returns_exact_hash(self):
        opportunity, result = await self.reply_draft()
        preview_opp, preview = await self.service.preview_reply_confirmation(
            opportunity.id, result.reply_turn.reply_version
        )
        self.assertEqual(preview_opp.id, opportunity.id)
        self.assertEqual(preview.content_sha256, result.reply_turn.content_sha256)
        self.assertEqual(preview.direction, "OUTGOING_DRAFT")
        self.assertEqual(len(self.state["confirmations"]), 1)

    async def test_valid_shared_reply_confirmation_persists_assurance(self):
        opportunity, result = await self.reply_draft()
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        saved, confirmation, created = await self.service.mark_reply_sent(
            opportunity.id,
            result.reply_turn.reply_version,
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
            confirmed_at=NOW,
            **audit_kwargs(actor),
        )
        self.assertTrue(created)
        self.assertEqual(saved.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual(confirmation.reply_version, result.reply_turn.reply_version)
        self.assertEqual(confirmation.content_sha256, result.reply_turn.content_sha256)
        self.assertEqual(confirmation.identity_assurance, SHARED_IDENTITY_ASSURANCE)
        self.assertEqual(confirmation.claimed_actor_role, "ADULT_OWNER")

    async def test_valid_shared_attestation_still_rejects_stale_reply(self):
        opportunity, first = await self.reply_draft()
        await self.service.process_client_message(
            _email("980001", "Please clarify authentication headers.", email_id="newer")
        )
        actor = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        with self.assertRaisesRegex(SalesCloserError, "stale"):
            await self.service.mark_reply_sent(
                opportunity.id,
                first.reply_turn.reply_version,
                actor_role=actor.role.value,
                actor_telegram_user_id=actor.user_id,
                confirmed_at=NOW,
                **audit_kwargs(actor),
            )
        self.assertNotEqual(
            (await self.repository.get_opportunity(opportunity.id)).state,
            OpportunityState.WAITING_CLIENT.value,
        )

    async def test_shared_fact_requires_explicit_artem_or_vadim_attestation(self):
        result = await self.human_request()
        with self.assertRaisesRegex(SalesCloserError, "action role"):
            await self.service.answer_human_request(
                result.human_request.id,
                "YES",
                actor_role="ARTEM",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_at=NOW,
                attestation_version=FACT_SOURCE_ATTESTATION_VERSION,
            )

    async def test_shared_fact_source_is_persisted_as_self_attested(self):
        result = await self.human_request()
        actor = shared_actor(TelegramRole.ARTEM, FACT_SOURCE_ATTESTATION_VERSION)
        answered = await self.service.answer_human_request(
            result.human_request.id,
            "YES",
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
            **audit_kwargs(actor),
        )
        request = answered.human_request
        self.assertEqual(request.claimed_actor_role, "ARTEM")
        self.assertEqual(request.actual_telegram_user_id, SHARED_ID)
        self.assertEqual(request.identity_assurance, SHARED_IDENTITY_ASSURANCE)
        self.assertEqual(request.source_turn_id, result.incoming_turn.id)
        self.assertEqual(request.subject_fingerprint, result.human_request.subject_fingerprint)
        self.assertEqual(request.answer_code, "YES")
        self.assertEqual(request.action_confirmed_at, NOW)
        acknowledged = await self.repository.get_turn(result.incoming_turn.id)
        self.assertEqual(acknowledged.acknowledged_by_role, "SHARED_OPERATOR")

    async def test_repeated_fact_with_different_claimed_source_conflicts(self):
        result = await self.human_request()
        artem = shared_actor(TelegramRole.ARTEM, FACT_SOURCE_ATTESTATION_VERSION)
        await self.service.answer_human_request(
            result.human_request.id,
            "YES",
            actor_role=artem.role.value,
            actor_telegram_user_id=artem.user_id,
            **audit_kwargs(artem),
        )
        vadim = shared_actor(TelegramRole.VADIM, FACT_SOURCE_ATTESTATION_VERSION)
        with self.assertRaisesRegex(SalesCloserError, "different fact source"):
            await self.service.answer_human_request(
                result.human_request.id,
                "YES",
                actor_role=vadim.role.value,
                actor_telegram_user_id=vadim.user_id,
                **audit_kwargs(vadim),
            )

    async def test_shared_fact_is_scoped_to_one_source_turn_and_fingerprint(self):
        first = await self.human_request("980020")
        artem = shared_actor(TelegramRole.ARTEM, FACT_SOURCE_ATTESTATION_VERSION)
        await self.service.answer_human_request(
            first.human_request.id,
            "YES",
            actor_role=artem.role.value,
            actor_telegram_user_id=artem.user_id,
            **audit_kwargs(artem),
        )
        second = await self.service.process_client_message(
            _email(
                "980020",
                "Can you support the Shopify API?",
                email_id="shared-second-fact",
            )
        )
        self.assertIsNotNone(second.human_request)
        self.assertNotEqual(second.human_request.source_turn_id, first.incoming_turn.id)
        self.assertNotEqual(
            second.human_request.subject_fingerprint,
            first.human_request.subject_fingerprint,
        )
        self.assertEqual(second.human_request.status, "OPEN")
        self.assertIsNone(second.reply_turn)

    async def test_restart_preserves_shared_confirmation_and_fact_audit(self):
        result = await self.human_request()
        actor = shared_actor(TelegramRole.VADIM, FACT_SOURCE_ATTESTATION_VERSION)
        await self.service.answer_human_request(
            result.human_request.id,
            "YES",
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
            **audit_kwargs(actor),
        )
        restarted = InMemorySalesRepository(self.state)
        confirmations = list(self.state["confirmations"].values())
        request = await restarted.get_human_request(result.human_request.id)
        self.assertEqual(confirmations[0].identity_assurance, SHARED_IDENTITY_ASSURANCE)
        self.assertEqual(request.claimed_actor_role, "VADIM")
        self.assertEqual(request.actual_telegram_user_id, SHARED_ID)

    async def test_neutral_shared_operator_can_acknowledge_and_sync(self):
        opportunity, result = await self.reply_draft()
        actor = authorize_telegram_actor(
            SHARED_ID,
            "shared",
            shared_settings(),
            allowed_roles=(TelegramRole.ADULT_OWNER, TelegramRole.ARTEM),
            required_settings=(),
            allow_shared_operator=True,
        )
        turn = await self.service.acknowledge_lead(
            result.incoming_turn.id,
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
        )
        sync, _ = await self.service.begin_context_sync(
            opportunity.id,
            actor_role=actor.role.value,
            actor_telegram_user_id=actor.user_id,
        )
        self.assertEqual(turn.acknowledged_by_role, "SHARED_OPERATOR")
        self.assertEqual(sync.requested_by_role, "SHARED_OPERATOR")
        self.assertTrue(
            await self.service.cancel_context_sync(
                actor.user_id, actor_role=actor.role.value
            )
        )

    async def test_synthetic_shared_operator_e2e(self):
        proposal = await self.seed("980099")
        await self.service.preview_bid_confirmation(
            proposal.id, proposal.proposal_version, "1200 USD", "5 days"
        )
        with self.assertRaisesRegex(SalesCloserError, "attestation"):
            await self.service.mark_bid_sent(
                proposal.id,
                proposal.proposal_version,
                "1200 USD",
                "5 days",
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role="ADULT_OWNER",
                claimed_at=NOW,
            )
        owner = shared_actor(TelegramRole.ADULT_OWNER, OWNER_ATTESTATION_VERSION)
        submitted, bid_confirmation, _ = await self.service.mark_bid_sent(
            proposal.id,
            proposal.proposal_version,
            "1200 USD",
            "5 days",
            actor_role=owner.role.value,
            actor_telegram_user_id=owner.user_id,
            confirmed_at=NOW,
            **audit_kwargs(owner),
        )
        technical = await self.service.process_client_message(
            _email("980099", "Can you support the HubSpot API?", email_id="e2e")
        )
        self.assertIsNotNone(technical.human_request)
        vadim = shared_actor(TelegramRole.VADIM, FACT_SOURCE_ATTESTATION_VERSION)
        reply = await self.service.answer_human_request(
            technical.human_request.id,
            "YES",
            actor_role=vadim.role.value,
            actor_telegram_user_id=vadim.user_id,
            **audit_kwargs(vadim),
        )
        await self.service.preview_reply_confirmation(
            submitted.id, reply.reply_turn.reply_version
        )
        with self.assertRaisesRegex(SalesCloserError, "attestation"):
            await self.service.mark_reply_sent(
                submitted.id,
                reply.reply_turn.reply_version,
                actor_role="ADULT_OWNER",
                actor_telegram_user_id=SHARED_ID,
                operator_mode="SINGLE_SHARED_OPERATOR",
                identity_assurance=SHARED_IDENTITY_ASSURANCE,
                claimed_actor_role="ADULT_OWNER",
                claimed_at=NOW,
            )
        waiting, reply_confirmation, _ = await self.service.mark_reply_sent(
            submitted.id,
            reply.reply_turn.reply_version,
            actor_role=owner.role.value,
            actor_telegram_user_id=owner.user_id,
            confirmed_at=NOW,
            **audit_kwargs(owner),
        )
        self.assertEqual(waiting.state, OpportunityState.WAITING_CLIENT.value)
        self.assertEqual(bid_confirmation.operator_mode, "SINGLE_SHARED_OPERATOR")
        self.assertEqual(reply_confirmation.operator_mode, "SINGLE_SHARED_OPERATOR")
        restarted = SalesCloserService(
            InMemorySalesRepository(self.state),
            reply_generator=self.generator,
            now=lambda: NOW,
        )
        persisted, transitions, turns, requests = await restarted.lead_timeline(
            waiting.id
        )
        self.assertEqual(persisted.state, OpportunityState.WAITING_CLIENT.value)
        self.assertTrue(any(item.new_state == "BID_SUBMITTED" for item in transitions))
        self.assertTrue(any(turn.direction == "OUTGOING_CONFIRMED" for turn in turns))
        self.assertEqual(requests[0].claimed_actor_role, "VADIM")
        self.assertEqual(len(self.state["confirmations"]), 2)


class TestSharedOperatorStaticSafety(unittest.TestCase):
    def test_cards_include_copy_ready_owner_and_fact_routes(self):
        analysis = stage4_validated()
        parts = format_job_card_parts(analysis)
        bid_card = "\n".join(parts)
        self.assertIn("OWNER_CONFIRMS", bid_card)
        self.assertIn("Platform action", bid_card.replace("platform action", "Platform action"))
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in parts))
        self.assertEqual(bid_card.count("<code>"), bid_card.count("</code>"))
        source = inspect.getsource(
            __import__("gmail_agent.sales_closer", fromlist=["SalesProcessResult"])
        )
        self.assertIn("ARTEM | <answer> (or VADIM)", source)

    def test_schema_migration_is_additive_and_restart_safe(self):
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
        for table in ("OWNER_ACTION_CONFIRMATIONS", "HUMAN_INFORMATION_REQUESTS"):
            for column in (
                "OPERATOR_MODE",
                "IDENTITY_ASSURANCE",
                "CLAIMED_ACTOR_ROLE",
                "ATTESTATION_VERSION",
                "ACTUAL_TELEGRAM_USER_ID",
                "CLAIMED_AT",
                "ACTION_CONFIRMED_AT",
            ):
                with self.subTest(table=table, column=column):
                    self.assertIn(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column}",
                        statements,
                    )
        self.assertNotIn("DROP TABLE", statements)
        self.assertNotIn("DELETE FROM", statements)

    def test_no_freelancehunt_write_capability_was_added(self):
        source = inspect.getsource(
            __import__("gmail_agent.sales_closer", fromlist=["SalesCloserService"])
        )
        self.assertNotIn("submit_bid", source)
        self.assertNotIn("send_platform_message", source)
        self.assertNotIn("accept_contract", source)

    def test_handler_whoami_does_not_print_raw_user_id(self):
        source = (Path(__file__).parents[2] / "bot" / "handlers.py").read_text(
            encoding="utf-8"
        )
        start = source.index("async def cmd_whoami")
        end = source.index('@router.message(Command("mark_bid_sent"))', start)
        whoami = source[start:end]
        self.assertNotIn("User ID:", whoami)
        self.assertNotIn("int(user.id)</code>", whoami)

    def test_bid_handler_separates_attestation_from_price_and_timeline(self):
        source = (Path(__file__).parents[2] / "bot" / "handlers.py").read_text(
            encoding="utf-8"
        )
        start = source.index("async def cmd_mark_bid_sent")
        end = source.index('@router.message(Command("answer_lead"))', start)
        handler = source[start:end]
        self.assertIn("price, timeline = parts[1:3]", handler)
        self.assertIn('parts[3] != OWNER_CONFIRMATION_PHRASE', handler)

    def test_settings_declare_both_mutually_exclusive_modes(self):
        source = (Path(__file__).parents[2] / "config.py").read_text(encoding="utf-8")
        self.assertIn('TELEGRAM_OPERATOR_MODE: str = "SEPARATE_ROLES"', source)
        self.assertIn("TELEGRAM_SHARED_OPERATOR_USER_ID: Optional[int] = None", source)
        self.assertEqual(SEPARATE_ROLE_IDENTITY_ASSURANCE, "CONFIGURED_ROLE_ID")


if __name__ == "__main__":
    unittest.main()
