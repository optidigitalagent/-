"""Offline reviewer regressions. All positive/mutated controls are synthetic."""
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError
from gmail_agent import email_analyzer as analyzer
from gmail_agent.quality_gate import validate_analysis, apply_validation, approved_evidence_text
from gmail_agent.telegram_notifier import format_job_card_parts
from gmail_agent.tests.test_issue20_ask_contract import correct_ask, real_payload, FIXTURES
from gmail_agent.tests.test_issue20_decision_first import _completion, _take_payload


def basis(**changes):
    result = dict(missing_fact='required client reference', owner='CLIENT',
        fact_kind='CLIENT_REQUIREMENT', source_quote='Match the mandatory client reference exactly.',
        absence_reason='No reference was supplied.', required_for_estimate=True,
        estimate_impact='The reference determines animation complexity and work hours.')
    result.update(changes)
    return result


class TestReviewFix(unittest.IsolatedAsyncioTestCase):
    async def item(self, *, source='Match the mandatory client reference exactly.',
                   ask_basis=None, action='Ask the client to supply the mandatory reference.'):
        payload=correct_ask()
        payload.update(language='en', reason='The reference determines animation complexity.',
            why_relevant='The source requests photo animation.',
            decision_reason='The required reference is missing and determines the animation work.',
            clarification_question='Which reference must the animation match?', next_action=action,
            evidence_case_id='NO_DIRECT_CASE')
        payload.pop('ask_basis',None)
        item=await analyzer.analyze_email('synthetic-review','Photo animation','Freelancehunt',source,
            client=_completion(payload))
        # Synthetic mutation, also runnable against the pre-fix parser.
        saved=json.loads(item.model_output_json); saved['ask_basis']=ask_basis or basis()
        item.model_output_json=json.dumps(saved,ensure_ascii=False)
        item.live_status='ACTIVE_BIDDABLE'; item.biddable=True
        item.live_status_checked_at=datetime.now(timezone.utc)
        return item

    async def test_a_executor_preference_cannot_become_client_requirement(self):
        source='Бажано відправити приклади з подібним завданням - рілз для товарки без відео.'
        item=await self.item(source=source,ask_basis=basis(source_quote=source))
        self.assertIn('ask_source_perspective_mismatch',validate_analysis(item).errors)

    async def test_b_required_client_reference_is_useful_ask(self):
        item=await self.item()
        self.assertEqual(validate_analysis(item).errors,())
        apply_validation(item,validate_analysis(item))
        self.assertEqual(item.commercial_decision,'ASK')
        self.assertEqual(item.proposal_draft,'')

    async def test_c_known_quantity_not_asked_again(self):
        item=await self.item(source='Нужны описания 10 товаров, до 1000 символов каждое.',
            ask_basis=basis(missing_fact='объём описания', source_quote='',
                absence_reason='Объём не указан.',estimate_impact='Объём влияет на оценку.'))
        item.language='ru'; item.clarification_question='Какой объём описания требуется для каждого товара?'
        self.assertIn('ask_fact_already_known',validate_analysis(item).errors)

    async def test_d_internal_fact_renderer_and_action(self):
        item=await self.item(ask_basis=basis(owner='TEAM',fact_kind='TEAM_FACT',source_quote='',
            missing_fact='Available animation capacity this week',
            absence_reason='No current team availability is recorded.',
            estimate_impact='Availability determines whether we can meet the requested deadline.'),
            action='Ask the team to confirm available animation hours this week.')
        item.clarification_question='How many animation hours can the team allocate this week?'
        self.assertEqual(validate_analysis(item).errors,())
        apply_validation(item,validate_analysis(item))
        text='\n'.join(format_job_card_parts(item))
        self.assertIn('Адресат:</b> команда',text)
        self.assertIn(item.next_action,text)
        self.assertIn('Внутренний вопрос',text)

    async def test_d_empty_and_recipient_only_actions_rejected(self):
        for action in ('','клієнт','client','team'):
            with self.subTest(action=action):
                item=await self.item(action=action)
                self.assertIn('next_action_not_actionable',validate_analysis(item).errors)

    async def test_e_repaired_evidence_not_pinned_to_old_selection(self):
        item=await self.item(); item.evidence_case_id='DEMO_REQUIRED'
        payload=correct_ask(); payload['evidence_case_id']='NO_DIRECT_CASE'
        payload['selected_evidence']='Invented fabricated evidence'; payload['language']='en'
        fixed=await analyzer.repair_analysis(item,['structured_field_contains_unapproved_capability_claim'],
            client=_completion(payload))
        self.assertEqual(fixed.evidence_case_id,'NO_DIRECT_CASE')
        self.assertEqual(fixed.selected_evidence,approved_evidence_text('NO_DIRECT_CASE','en'))
        self.assertEqual(fixed.full_description,item.full_description)
        self.assertEqual(fixed.live_status_checked_at,item.live_status_checked_at)
        self.assertEqual(fixed.budget,item.budget)

    async def test_f_single_rejected_payload_and_field_diagnostics(self):
        item=await self.item(); item.why_relevant='We have experience in imaginary-animation.'
        raw=json.loads(item.model_output_json); raw['why_relevant']=item.why_relevant
        item.model_output_json=json.dumps(raw)
        client=_completion(correct_ask())
        await analyzer.repair_analysis(item,['structured_field_contains_unapproved_capability_claim',
            'next_action_not_actionable','live_status_not_fresh'],client=client)
        prompt=client.chat.completions.create.await_args.kwargs['messages'][1]['content']
        self.assertIn('"rejected_response"',prompt)
        context=json.loads(prompt.split('Repair context JSON:\n')[1])
        self.assertNotIn('model_output_json',context['rejected_response'])
        self.assertNotIn('normalized_analysis',context)
        matches=[d for d in context['diagnostics'] if d['path']=='why_relevant']
        self.assertEqual(len(matches),1)
        self.assertIn('imaginary-animation',matches[0]['fragment'])
        self.assertTrue(matches[0]['rule'])
        self.assertFalse(any(d['code']=='live_status_not_fresh' for d in context['diagnostics']))
        self.assertEqual(context['source_facts']['full_description'],item.full_description)

    def test_g_take_wire_scores_and_offer_required(self):
        for field in ('score','fit_score'):
            for value in (None,-1,11):
                with self.subTest(field=field,value=value):
                    payload=_take_payload(); payload[field]=value
                    with self.assertRaises(ValidationError):
                        analyzer.OpportunityWireOutput.model_validate({'analysis':payload})
        for field in ('recommended_price','realistic_timeline','proposal_draft'):
            for value in ('','  '):
                payload=_take_payload(); payload[field]=value
                with self.assertRaises(ValidationError):
                    analyzer.OpportunityWireOutput.model_validate({'analysis':payload})
        payload=_take_payload(); payload['score']=payload['fit_score']=0.0
        parsed=analyzer.OpportunityWireOutput.model_validate({'analysis':payload})
        self.assertEqual(parsed.analysis.score,0.0)

    async def test_h_stale_active_ask_cannot_reach_client_card(self):
        item=await self.item(); apply_validation(item,validate_analysis(item))
        item.live_status_checked_at-=timedelta(days=1)
        self.assertIn('live_status_not_fresh',validate_analysis(item).errors)
        text='\n'.join(format_job_card_parts(item))
        self.assertNotIn('<b>Решение:</b> ASK',text)

    async def test_real_5_6_remain_negative_without_rewriting(self):
        source=json.loads((FIXTURES/'source_1651774.json').read_text(encoding='utf-8'))['original_snapshot']
        for sequence in (5,6):
            raw=real_payload(sequence)
            # Legacy shape replay is not a new provider success under the new schema.
            item=await analyzer.analyze_email('historical-real','reels','Freelancehunt',source['full_description'],
                client=_completion(copy.deepcopy(raw['analysis'])))
            self.assertIn('structured_field_contains_unapproved_capability_claim',validate_analysis(item).errors)
            self.assertNotEqual(validate_analysis(item).status,'QUALITY_NEEDS_CLARIFICATION')

    async def test_mutation_real_5_neutral_claims_fresh_flag_still_not_useful_ask(self):
        source=json.loads((FIXTURES/'source_1651774.json').read_text(encoding='utf-8'))['original_snapshot']
        payload=copy.deepcopy(real_payload(5)['analysis'])
        payload.update(reason='The source requires three photo-based reels.',
            why_relevant='The task requires composing product photos in Canva.')
        item=await analyzer.analyze_email('synthetic-mutation','reels','Freelancehunt',source['full_description'],
            client=_completion(payload))
        item.live_status='ACTIVE_BIDDABLE'; item.biddable=True
        item.live_status_checked_at=datetime.now(timezone.utc)
        errors=validate_analysis(item).errors
        self.assertIn('ask_basis_missing_or_invalid',errors)
        self.assertIn('next_action_not_actionable',errors)
        self.assertNotIn('structured_field_contains_unapproved_capability_claim',errors)

    async def test_basis_quote_owner_and_requirement_guards(self):
        for changes, expected in (
            ({'source_quote':'Invented mandatory condition'},'ask_source_quote_not_grounded'),
            ({'required_for_estimate':False},'ask_not_estimate_blocking'),
            ({'fact_kind':'EXECUTION_INPUT'},'ask_not_estimate_blocking'),
            ({'fact_kind':'EXECUTOR_PREFERENCE'},'ask_not_estimate_blocking'),
            ({'fact_kind':'TEAM_FACT'},'ask_fact_owner_mismatch'),
            ({'source_quote':'','absence_reason':''},'ask_missing_source_gap_reason'),
        ):
            with self.subTest(changes=changes):
                item=await self.item(ask_basis=basis(**changes))
                self.assertIn(expected,validate_analysis(item).errors)

    async def test_repaired_irrelevant_case_is_not_claimed_or_restored(self):
        item=await self.item(); item.evidence_case_id='DEMO_REQUIRED'
        payload=correct_ask(); payload.update(evidence_case_id='AUDIOBOOK_CLEANER',language='en')
        fixed=await analyzer.repair_analysis(item,['structured_field_contains_unapproved_capability_claim'],
            client=_completion(payload))
        self.assertEqual(fixed.evidence_case_id,'AUDIOBOOK_CLEANER')
        self.assertEqual(fixed.selected_evidence,'')
        self.assertIn('evidence_selection_not_source_related',validate_analysis(fixed).errors)

    async def test_internal_historical_question_is_not_client_action(self):
        item=await self.item(ask_basis=basis(owner='TEAM',fact_kind='TEAM_FACT',source_quote='',
            missing_fact='Available team hours',absence_reason='Current capacity is not recorded.'),
            action='Ask the team to confirm available hours.')
        item.clarification_question='How many hours can the team allocate?'
        item.live_status='LIVE_STATUS_UNKNOWN'; item.biddable=None; item.live_status_checked_at=None
        self.assertEqual(validate_analysis(item).errors,())
        apply_validation(item,validate_analysis(item))
        self.assertFalse(item.qualified)
        self.assertEqual(item.proposal_draft,'')
        text='\n'.join(format_job_card_parts(item))
        self.assertIn('Внутренний вопрос',text)
        self.assertIn('не разрешает клиентское действие',text)

    async def test_unrelated_question_cannot_use_internal_fact_as_cover(self):
        item=await self.item(ask_basis=basis(owner='TEAM',fact_kind='TEAM_FACT',source_quote='',
            missing_fact='Available working hours',absence_reason='Capacity not known.'),
            action='Ask the team to confirm working hours.')
        self.assertIn('ask_question_fact_mismatch',validate_analysis(item).errors)

    async def test_reason_expertise_not_authorized_by_no_direct_case(self):
        item=await self.item(); item.evidence_case_id='NO_DIRECT_CASE'
        item.reason='Це відповідає нашій експертизі в області відео-контенту.'
        self.assertIn('structured_field_contains_unapproved_capability_claim',validate_analysis(item).errors)
