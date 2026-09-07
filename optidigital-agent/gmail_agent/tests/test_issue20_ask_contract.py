"""Commercial-contract regressions; real saved completions stay bad fixtures."""
import json
import os
from pathlib import Path
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
from openai import AsyncOpenAI
from pydantic import ValidationError
from gmail_agent import email_analyzer as analyzer
from gmail_agent.quality_gate import (
    apply_validation, compose_application_owned_proposal, validate_analysis,
    is_proposal_ready,
)
from gmail_agent.tests.test_issue20_decision_first import _completion, _take_payload
from gmail_agent.digest_parser import DigestJobCandidate, enrich_candidate_scope
from gmail_agent.processor import GmailJobProcessor
from gmail_agent import storage
from gmail_agent.tests import test_nullable_score_fit_metadata_postgres as pg_fixture

FIXTURES = Path(__file__).parent / 'fixtures' / 'issue20_real_ask'


def real_payload(sequence):
    return json.loads(json.loads((FIXTURES / f'completion_{sequence}.json').read_text(encoding='utf-8'))['content'])


def correct_ask():
    data = _take_payload()
    data.update(commercial_decision='ASK', executable='maybe', recommended_price='',
        realistic_timeline='', proposal_draft='', needs_context=True,
        clarification_question='Подскажите, какой объём описания требуется для каждого товара?',
        decision_reason='В исходнике не указан объём одного описания.',
        next_action='Уточнить у клиента объём одного описания.', score=0.0, fit_score=0.0,
        ask_basis=dict(missing_fact='Объём одного описания', owner='CLIENT',
            fact_kind='CLIENT_REQUIREMENT', source_quote='',
            absence_reason='В исходнике не указан объём одного описания.',
            required_for_estimate=True, estimate_impact='Объём определяет часы работы и стоимость.'))
    return data


def synthetic_candidate():
    return enrich_candidate_scope(DigestJobCandidate(
        source_email_id='synthetic-contract', platform='Freelancehunt',
        title='SEO descriptions for 10 products', description='SEO descriptions for 10 products, 1000 characters each.',
        budget='', url='https://freelancehunt.com/project/synthetic/990020098.html',
        category='SEO', received_at=datetime.now(timezone.utc), stable_key='synthetic-contract',
        project_id='990020098', discovery_source='synthetic_test'),
        description='Нужны SEO описания 10 товаров, до 1000 символов каждое.',
        source_kind='SYNTHETIC_TEST', main_text_completeness='FULL',
        materials_status='UNAVAILABLE_EXECUTION_INPUTS_ONLY', scope_sufficiency='SUFFICIENT_FOR_FIXED_TERMS')


class TestAskContract(unittest.IsolatedAsyncioTestCase):
    async def parse(self, payload):
        item = await analyzer.analyze_email('synthetic-ask-contract', 'SEO descriptions', 'Freelancehunt',
            'Нужны SEO описания товаров.', client=_completion(payload))
        item.live_status='ACTIVE_BIDDABLE'
        item.live_status_checked_at=datetime.now(timezone.utc)
        item.biddable=True
        return item

    def test_prompt_has_no_forced_example_terms_or_zero(self):
        self.assertNotIn('1200 USD', analyzer._SYSTEM_PROMPT)
        self.assertNotIn('4-6 weeks', analyzer._SYSTEM_PROMPT)
        self.assertNotIn('"score": 0.0', analyzer._SYSTEM_PROMPT)

    async def test_real_bad_responses_remain_rejected_without_composition(self):
        for seq in (3,4):
            item=await self.parse(real_payload(seq))
            self.assertTrue(item.analysis_succeeded)
            self.assertEqual((item.score_state,item.fit_score_state),('VALID','VALID'))
            self.assertEqual((item.score,item.fit_score),(0.0,0.0))
            validation=validate_analysis(item)
            self.assertIn('ask_has_price', validation.errors)
            self.assertIn('ask_has_timeline', validation.errors)
            self.assertIn('ask_has_proposal', validation.errors)
            self.assertEqual(compose_application_owned_proposal(item),'')
            apply_validation(item,validation)
            self.assertFalse(is_proposal_ready(item))
            self.assertEqual(item.proposal_draft,'')

    async def test_correct_ask_and_valid_zero_survive_gate(self):
        item=await self.parse(correct_ask())
        validation=validate_analysis(item)
        self.assertEqual(validation.errors,())
        apply_validation(item,validation)
        self.assertEqual(item.commercial_decision,'ASK')
        self.assertEqual(item.analysis_quality_status,'QUALITY_NEEDS_CLARIFICATION')
        self.assertEqual(item.score_state,'VALID')
        self.assertEqual(item.budget,'1000 UAH')
        self.assertFalse(is_proposal_ready(item))

    async def test_wrong_question_language_rejected(self):
        data=correct_ask(); data['clarification_question']='Could you specify the required length?'
        item=await self.parse(data)
        self.assertIn('clarification_language_mismatch',validate_analysis(item).errors)

    async def test_unapproved_experience_rejected_for_ask(self):
        data=correct_ask(); data['why_relevant']='We have experience in creating visual content.'
        item=await self.parse(data)
        self.assertIn('structured_field_contains_unapproved_capability_claim',validate_analysis(item).errors)

    async def test_historical_ask_is_not_actionable(self):
        item=await self.parse(correct_ask()); item.live_status='LIVE_STATUS_UNKNOWN'; item.biddable=None
        validation=validate_analysis(item)
        self.assertIn('live_status_not_active_biddable',validation.errors)
        apply_validation(item,validation)
        self.assertFalse(is_proposal_ready(item))

    async def test_absent_budget_is_not_replaced_with_model_budget(self):
        result=await analyzer.analyze_candidate(synthetic_candidate(),client=_completion(_take_payload()))
        self.assertEqual(result.budget_provenance,'UNAVAILABLE')
        self.assertEqual(result.budget,'не вказано')
        self.assertEqual(result.recommended_price,'1000 UAH as one milestone')

    async def test_synthetic_take_without_budget_or_direct_case_remains_possible(self):
        payload=_take_payload(); payload['evidence_case_id']='NO_DIRECT_CASE'
        item=await analyzer.analyze_candidate(synthetic_candidate(),client=_completion({'analysis':payload}))
        self.assertTrue(item.analysis_succeeded)
        item.live_status='ACTIVE_BIDDABLE'; item.biddable=True
        item.live_status_checked_at=datetime.now(timezone.utc)
        validation=validate_analysis(item)
        self.assertEqual(validation.errors,())
        apply_validation(item,validation)
        self.assertTrue(is_proposal_ready(item))
        self.assertIn('после получения', item.proposal_draft)

    async def test_repair_clears_old_offer_without_restoring_snapshot(self):
        original=await self.parse(real_payload(3))
        original.budget='1000 UAH'; original.budget_provenance='SOURCE_CANDIDATE'
        data=correct_ask(); data['language']='uk'
        data['clarification_question']='Який обсяг опису потрібен для кожного товару?'
        client=_completion(data)
        fixed=await analyzer.repair_analysis(original,['ask_has_price','live_status_not_active_biddable'],client=client)
        self.assertEqual((fixed.recommended_price,fixed.realistic_timeline,fixed.proposal_draft),('','',''))
        self.assertEqual(fixed.budget,'1000 UAH')
        prompt=client.chat.completions.create.await_args.kwargs['messages'][-1]['content']
        errors=prompt.split('Validation errors: ',1)[1].split('\n',1)[0]
        self.assertNotIn('live_status_not_active_biddable',json.loads(errors))

    async def test_no_repair_for_only_immutable_live_error(self):
        item=await self.parse(correct_ask()); client=MagicMock()
        client.chat.completions.create=AsyncMock()
        with self.assertRaises(ValueError):
            await analyzer.repair_analysis(item,['live_status_not_active_biddable'],client=client)
        client.chat.completions.create.assert_not_awaited()

    async def test_serialized_sdk_wire_schema_branches_reject_contradictory_ask(self):
        requests=[]
        async def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'offline','object':'chat.completion','created':0,
                'model':'gpt-4o-mini','choices':[{'index':0,'finish_reason':'stop',
                    'message':{'role':'assistant','content':json.dumps({'analysis':correct_ask()})}}]})
        async with AsyncOpenAI(api_key='offline-test', max_retries=0,
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))) as sdk:
            result=await analyzer.analyze_email('offline','SEO','Freelancehunt','Описания товаров',client=sdk)
        self.assertTrue(result.analysis_succeeded)
        schema=requests[0]['response_format']['json_schema']['schema']
        self.assertEqual(schema['type'],'object')
        self.assertNotIn('anyOf',schema)
        self.assertIn('anyOf',schema['properties']['analysis'])
        for seq in (3,4):
            with self.assertRaises(ValidationError):
                analyzer.OpportunityWireOutput.model_validate({'analysis':real_payload(seq)})
        for node in schema['$defs'].values():
            self.assertEqual(set(node['required']),set(node['properties']))
            self.assertFalse(node['additionalProperties'])
        take_schema = schema['$defs']['TakeOutput']['properties']
        for name in ('score','fit_score'):
            self.assertEqual(take_schema[name]['minimum'],0)
            self.assertEqual(take_schema[name]['maximum'],10)
            self.assertEqual(take_schema[name]['type'],'number')
        for name in ('recommended_price','realistic_timeline','proposal_draft'):
            self.assertEqual(take_schema[name]['pattern'],r'\S')
        self.assertEqual(result.recommended_price,'')


@unittest.skipUnless(os.environ.get('PQG_TEST_DATABASE_URL'), 'isolated PostgreSQL opt-in')
class TestContractRoundTripPostgres(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = pg_fixture.TestNullableScoreFitMetadataPostgres.asyncSetUp
    asyncTearDown = pg_fixture.TestNullableScoreFitMetadataPostgres.asyncTearDown

    async def test_wire_to_flat_ask_and_take_roundtrip(self):
        for index,payload in enumerate((correct_ask(), _take_payload())):
            candidate=synthetic_candidate()
            from dataclasses import replace
            candidate=replace(candidate,stable_key=f'synthetic-contract-{index}')
            if index == 0:
                # Synthetic ASK source actually lacks the requested quantity.
                candidate=enrich_candidate_scope(candidate,
                    description='Нужны SEO описания 10 товаров; объём каждого не указан.',
                    source_kind='SYNTHETIC_TEST',main_text_completeness='FULL',
                    materials_status='NOT_REFERENCED',scope_sufficiency='UNKNOWN')
            item=await analyzer.analyze_candidate(candidate,client=_completion({'analysis':payload}))
            self.assertTrue(item.analysis_succeeded)
            item.live_status='ACTIVE_BIDDABLE'; item.biddable=True
            item.live_status_checked_at=datetime.now(timezone.utc)
            validation=validate_analysis(item); self.assertEqual(validation.errors,())
            apply_validation(item,validation)
            await self.repository.save_job(GmailJobProcessor._stored_job(candidate,item))
            loaded=await storage.PostgresGmailRepository(self.sessions).get_job(candidate.stable_key)
            restored=GmailJobProcessor._analysis_from_job(loaded)
            for field in ('commercial_decision','clarification_question','recommended_price','realistic_timeline',
                'proposal_draft','proposal_version','proposal_content_sha256','score','fit_score',
                'score_state','fit_score_state','budget','budget_provenance','model_output_json'):
                self.assertEqual(getattr(restored,field),getattr(item,field),field)
            self.assertEqual(is_proposal_ready(restored), index==1)
            if index == 0:
                from gmail_agent.quality_gate import ask_basis
                from gmail_agent.telegram_notifier import format_job_card_parts
                self.assertEqual(ask_basis(restored),payload['ask_basis'])
                self.assertIn(restored.next_action,'\n'.join(format_job_card_parts(restored)))
