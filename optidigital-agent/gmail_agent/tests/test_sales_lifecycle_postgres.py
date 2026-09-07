"""One SYNTHETIC A→B deal plus negative controls; real isolated PostgreSQL.

External input/model/delivery only are fixtures. No production connection is
accepted. Run with ops/issue15_mechanical_e2e.py from the worktree root.
"""
from __future__ import annotations

import json
import os
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from gmail_agent.tests.test_issue20_ask_contract import synthetic_candidate
from gmail_agent.tests.test_issue20_decision_first import _take_payload, _completion
from gmail_agent.tests.test_sales_closer_5a import _email, _reply_generator
from gmail_agent.tests.test_sales_closer_5a_shared_operator import shared_settings, SHARED_ID
from gmail_agent.email_analyzer import analyze_candidate
from gmail_agent.quality_gate import apply_validation, validate_analysis
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.storage import PostgresGmailRepository
from gmail_agent.sales_closer import SalesCloserService
from gmail_agent.sales_storage import PostgresSalesRepository
from gmail_agent.sales_lifecycle import load, digest
from gmail_agent.scheduler import check_sales_followups, register_sales_followup_job
from gmail_agent.telegram_notifier import format_lead_timeline, format_pipeline_counts

ISOLATED = 'postgresql+asyncpg://issue20e2e@127.0.0.1:55432/issue20e2e'
ENABLED = os.environ.get('SALES_LIFECYCLE_TEST_DATABASE_URL') == ISOLATED
TERMS = dict(scope='SYNTHETIC: SEO descriptions for 12 products, up to 1000 characters each',
    deliverables='12 texts in a table with product IDs', acceptance_criteria='12 rows; up to 1000 characters; facts from product cards; one agreed revision round',
    boundaries='No publication, design or catalog management; additional products estimated separately',
    price='1200 UAH', timeline='3 days', payment_stages='One stage of 1200 UAH through the platform after acceptance; stage reserved before start',
    start_condition='3 days after stage reserve and receipt of 12 product cards',
    promises='One revision round against the agreed acceptance criteria', materials='12 product cards and keyword list received (SYNTHETIC)',
    access_location='Доступы к магазину не нужны; материалы у владелицы в приватном хранилище, запросить лично',
    risks='Недостоверные характеристики клиент уточняет до написания',
    first_action='Артём: сверить 12 карточек и ключи. Вадим: проверить формат таблицы и ID; начать после этой сверки',
    start_requirements='Резерв 1200 UAH; получены 12 карточек и ключи', payment_required_to_start='RESERVED')


@unittest.skipUnless(ENABLED, 'explicit isolated PostgreSQL opt-in')
class TestMechanicalLifecycle(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from db.models import Base, _MIGRATIONS
        self.schema = 'mechanical_5bc_' + uuid4().hex
        bootstrap = create_async_engine(ISOLATED)
        async with bootstrap.begin() as conn:
            proof = (await conn.execute(text('SELECT current_database(), inet_server_addr()::text, inet_server_port(), current_user'))).one()
            self.assertEqual(tuple(proof), ('issue20e2e', '127.0.0.1/32', 55432, 'issue20e2e')
                             if '/32' in proof[1] else ('issue20e2e', '127.0.0.1', 55432, 'issue20e2e'))
            await conn.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        await bootstrap.dispose()
        self.engine = create_async_engine(ISOLATED, connect_args={'server_settings': {'search_path': self.schema}})
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for _ in range(2):
                for statement in _MIGRATIONS:
                    await conn.execute(text(statement))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.at = datetime.now(timezone.utc)
        self.sequence = 0
        self.story = []
        self.restart()
        from bot import handlers
        self.handlers = handlers
        self.patches = [patch.object(handlers, 'settings', shared_settings(SALES_LIFECYCLE_ENABLED=True)),
                        patch.object(handlers, '_sales_closer_service', side_effect=lambda: self.service)]
        for p in self.patches:
            p.start()

    def restart(self):
        self.repo = PostgresSalesRepository(self.sessions)
        self.service = SalesCloserService(self.repo, reply_generator=AsyncMock(side_effect=_reply_generator),
                                         now=lambda: self.at, followup_enabled=True)

    async def asyncTearDown(self):
        for p in self.patches:
            p.stop()
        await self.engine.dispose()
        cleanup = create_async_engine(ISOLATED)
        async with cleanup.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        await cleanup.dispose()

    def message(self, content):
        self.sequence += 1
        return SimpleNamespace(text=content, message_id=self.sequence,
            chat=SimpleNamespace(id=777), from_user=SimpleNamespace(id=SHARED_ID, username='synthetic_operator'),
            answer=AsyncMock())

    async def record(self, op_id, event):
        op, transitions, turns, requests = await self.service.lead_timeline(op_id)
        for part in format_lead_timeline(op, transitions, turns, requests):
            self.assertLessEqual(len(part), 4096)
        self.story.append(dict(event=event, state=op.state, lifecycle=load(op),
            follow_up_status=op.follow_up_status, next_follow_up_at=str(op.next_follow_up_at),
            initial_proposal=op.initial_proposal, initial_version=op.proposal_version,
            initial_hash=op.proposal_content_sha256, source_description=op.source_description,
            turns=[dict(id=t.id, direction=t.direction, source=t.source, content=t.content,
                        version=t.reply_version, hash=t.content_sha256, sent_at=str(t.sent_at)) for t in turns],
            operator='\n'.join(format_lead_timeline(op, transitions, turns, requests))))
        return op

    async def deal(self, op, action, payload, role='OWNER_CONFIRMS', *, success=True, event_message=None):
        data = dict(payload, reference='SYNTHETIC fixture: owner checked this exact test deal')
        if action == 'dialogue' and data.get('status') == 'AVAILABLE_SYNCED_NO_NEW_REPLY':
            data['sales_status'] = 'OPEN_WAITING_NO_SELECTION_NO_CONTRACT'
        message = event_message or self.message('/deal ' + op.id + ' ' + action + '\n' +
                    '\n'.join(k + '=' + str(v) for k, v in data.items()) + ' | ' + role)
        await self.handlers.cmd_deal(message)
        output = '\n'.join(c.args[0] for c in message.answer.await_args_list)
        if success:
            self.assertIn('Записано локальное подтверждение', output, output)
        else:
            self.assertIn('Действие не записано', output, output)
        return await self.repo.get_opportunity(op.id), message, output

    async def start_deal(self, project_id):
        candidate = replace(synthetic_candidate(), project_id=project_id,
            stable_key=f'synthetic-mechanical:{project_id}', source_email_id=f'synthetic:{project_id}',
            url=f'https://freelancehunt.com/project/synthetic/{project_id}.html',
            title=f'SYNTHETIC SEO descriptions {project_id}')
        payload = _take_payload()
        payload.update(project_id=project_id, url=candidate.url, title=candidate.title, client_name='SYNTHETIC same client')
        item = await analyze_candidate(candidate, client=_completion({'analysis': payload}))
        item.live_status = 'ACTIVE_BIDDABLE'
        item.biddable = True
        item.live_status_checked_at = datetime.now(timezone.utc)
        validation = validate_analysis(item)
        self.assertEqual(validation.errors, ())
        apply_validation(item, validation)
        jobs = PostgresGmailRepository(self.sessions)
        await jobs.save_job(GmailJobProcessor._stored_job(candidate, item))
        job = await PostgresGmailRepository(self.sessions).get_job(candidate.stable_key)
        op = await self.service.ensure_from_validated_job(job)
        self.assertIsNotNone(op)
        await self.record(op.id, 'SYNTHETIC source → real analyzer with model fixture → gate/composition → PG → 5A')
        msg = self.message(f'/mark_bid_sent {op.id} {op.proposal_version} | 1000 UAH | 2 days | OWNER_CONFIRMS')
        await self.handlers.cmd_mark_bid_sent(msg)
        op = await self.repo.get_opportunity(op.id)
        self.assertEqual(op.state, 'BID_SUBMITTED', str(msg.answer.await_args_list))
        await self.record(op.id, 'Adult owner SYNTHETIC send confirmation through real Telegram handler')
        return op

    async def incoming(self, op, body, *, email_id=None):
        self.at += timedelta(seconds=2)
        email = _email(op.project_id, 'SYNTHETIC: ' + body, email_id=email_id or uuid4().hex,
                       client='SYNTHETIC same client')
        email.received_at = self.at
        result = await self.service.process_client_message(email)
        return result, email

    async def prepare_terms(self, op):
        result, _ = await self.incoming(op, 'Could you add two products? This is additional scope.')
        self.assertEqual(result.opportunity.state, 'NEEDS_HUMAN_INPUT')
        request = (await self.repo.list_human_requests(op.id))[-1]
        self.assertEqual(request.status, 'OPEN')
        await self.record(op.id, 'Client adds two products → concrete scope human request')
        self.restart()
        msg = self.message(f'/answer_lead {request.id} VADIM | SEPARATE_PAID_ESTIMATE')
        await self.handlers.cmd_answer_lead(msg)
        request = (await self.repo.list_human_requests(op.id))[-1]
        self.assertEqual(request.status, 'ANSWERED', str(msg.answer.await_args_list))
        op = await self.repo.get_opportunity(op.id)
        self.assertEqual(op.state, 'NEGOTIATING', str(msg.answer.await_args_list))
        await self.record(op.id, 'Restart → VADIM answers scope fact → real 5A reply resumes')
        op, _, _ = await self.deal(op, 'terms', TERMS)
        terms = load(op)['terms'][-1]
        self.assertNotIn('sent', terms)
        self.at += timedelta(seconds=2)
        msg = self.message(f'/mark_reply_sent {op.id} {terms["reply_version"]} | OWNER_CONFIRMS')
        await self.handlers.cmd_mark_reply_sent(msg)
        op = await self.repo.get_opportunity(op.id)
        self.assertEqual(op.state, 'WAITING_CLIENT', str(msg.answer.await_args_list))
        return op

    async def agree(self, op):
        result, email = await self.incoming(op, 'We selected your team. We accept exactly the final proposal: '
            '12 product descriptions, 1200 UAH, 3 days after reserve and product cards. One revision. Payment after acceptance.')
        turn = result.incoming_turn
        version = load(await self.repo.get_opportunity(op.id))['terms'][-1]['version']
        op, _, _ = await self.deal(op, 'accept', dict(version=str(version), turn=turn.id, statement='CLIENT_ACCEPTED_EXACT_TERMS'))
        op, _, _ = await self.deal(op, 'select', dict(version=str(version), turn=turn.id, statement='CLIENT_SELECTED_OUR_TEAM'))
        op, _, _ = await self.deal(op, 'capacity', dict(version=str(version), statement='TEAM_CAN_DELIVER_THIS_VERSION'), role='VADIM')
        op, _, _ = await self.deal(op, 'payment', dict(version=str(version), status='PROMISED'))
        op, _, _ = await self.deal(op, 'start', dict(version=str(version), requirements=TERMS['start_requirements'],
                                                   statement='START_REQUIREMENTS_SATISFIED'))
        await self.deal(op, 'handoff', dict(version=str(version)), success=False)
        op, _, _ = await self.deal(op, 'payment', dict(version=str(version), status='RESERVED'))
        return op, email

    async def test_a_to_b_and_negative_controls(self):
        op = await self.start_deal('990015501')
        self.assertEqual(op.follow_up_count, 0)
        scheduler = __import__('apscheduler.schedulers.asyncio', fromlist=['AsyncIOScheduler']).AsyncIOScheduler()
        register_sales_followup_job(scheduler, enabled=True, service=self.service)
        scheduled = scheduler.get_job('sales_followups')
        self.assertEqual(scheduled.max_instances, 1)
        await scheduled.func(**scheduled.kwargs)
        op = await self.repo.get_opportunity(op.id)
        self.assertEqual(op.next_follow_up_at, op.bid_submitted_at + timedelta(hours=12))
        self.at = op.next_follow_up_at + timedelta(seconds=1)
        self.restart()
        await check_sales_followups(self.service)
        self.assertEqual((await self.repo.get_opportunity(op.id)).follow_up_status, 'NEEDS_DIALOGUE_SYNC')
        op, _, _ = await self.deal(op, 'dialogue', dict(thread=op.project_url, status='READ_FAILED'))
        await check_sales_followups(self.service)
        self.assertFalse(any(t.intent == 'FOLLOW_UP' for t in await self.repo.list_turns(op.id)))
        op, _, _ = await self.deal(op, 'dialogue', dict(thread=op.project_url, status='AVAILABLE_SYNCED_NO_NEW_REPLY'))
        await check_sales_followups(self.service)
        drafts = [t for t in await self.repo.list_turns(op.id) if t.direction == 'OUTGOING_DRAFT']
        self.assertEqual(len(drafts), 1)
        followup = drafts[0]
        self.assertEqual(followup.intent, 'FOLLOW_UP')
        self.at += timedelta(seconds=121)
        await self.deal(op, 'followup_sent', dict(version=followup.reply_version, hash=followup.content_sha256), success=False)
        self.restart()
        await check_sales_followups(self.service)
        self.assertEqual(len([t for t in await self.repo.list_turns(op.id) if t.intent == 'FOLLOW_UP']), 1)
        await self.record(op.id, '12h since confirmed send + fresh SYNTHETIC dialogue read → one unsent follow-up, restart keeps it')
        result, _ = await self.incoming(op, 'Interesting. Can you clarify the authentication?')
        self.assertNotEqual(result.opportunity.state, 'HANDOFF_READY')
        self.assertEqual((await self.repo.get_turn(followup.id)).direction, 'OUTGOING_SUPERSEDED')
        await self.deal(op, 'followup_sent', dict(version=followup.reply_version, hash=followup.content_sha256), success=False)
        # Resolve the concrete fact created by this technical question through 5A.
        requests = await self.repo.list_human_requests(op.id)
        for req in requests:
            if req.status == 'OPEN':
                msg = self.message(f'/answer_lead {req.id} VADIM | YES')
                await self.handlers.cmd_answer_lead(msg)
        await self.record(op.id, 'Client reply cancels unsent follow-up atomically; interest alone is not a win')
        await self.deal(op, 'handoff', dict(version='1'), success=False)
        op = await self.prepare_terms(op)
        await self.record(op.id, 'Owner composes concrete revised terms → exact draft version manually confirmed sent')
        op, acceptance_email = await self.agree(op)
        saved_lifecycle = op.lifecycle_json
        rediscovered_job = await PostgresGmailRepository(self.sessions).get_job('synthetic-mechanical:' + op.project_id)
        refreshed = await self.service.ensure_from_validated_job(rediscovered_job)
        self.assertEqual(refreshed.lifecycle_json, saved_lifecycle)
        self.assertEqual(refreshed.state, 'CONTRACT_REVIEW')
        await self.record(op.id, 'Explicit acceptance + selected our team + team capacity + RESERVED/start evidence, not received revenue')
        op, _, _ = await self.deal(op, 'handoff', dict(version='1'))
        self.assertEqual(op.state, 'HANDOFF_READY')
        handoff = load(op)['handoff']
        self.assertEqual(handoff['payment']['status'], 'RESERVED')
        await self.record(op.id, 'Validated HANDOFF_READY package produced; awaits team receipt')
        self.restart()
        op, receipt_message, _ = await self.deal(op, 'received', dict(version='1', hash=handoff['terms_hash']), role='ARTEM')
        self.assertEqual(op.state, 'IN_DELIVERY')
        self.restart()
        refreshed = await self.service.ensure_from_validated_job(rediscovered_job)
        self.assertEqual(refreshed.state, 'IN_DELIVERY')
        self.assertEqual(refreshed.lifecycle_json, op.lifecycle_json)
        op, _, _ = await self.deal(op, 'received', {}, event_message=receipt_message)
        self.assertEqual(len(load(op)['handoff']['receipts']), 1)
        duplicate = await self.service.process_client_message(acceptance_email)
        self.assertTrue(duplicate.duplicate)
        later, _ = await self.incoming(op, 'SYNTHETIC delivery update: the second file is available.')
        self.assertEqual(later.opportunity.state, 'IN_DELIVERY')
        await check_sales_followups(self.service)
        op = await self.record(op.id, 'Team receipt → restart → duplicate ignored; later client message retained, sales stopped')
        self.assertIsNone(op.next_follow_up_at)
        self.assertTrue(op.do_not_follow_up)
        other = await self.start_deal('990015502')
        self.assertNotEqual(other.id, op.id)
        self.assertEqual(load(other).get('terms', []), [])
        rejection, _ = await self.incoming(other, 'We chose another freelancer. Not interested.')
        self.assertEqual(rejection.opportunity.state, 'LOST')
        self.restart()
        self.assertTrue((await self.repo.get_opportunity(other.id)).do_not_follow_up)
        self.assertEqual((await self.repo.get_opportunity(op.id)).state, 'IN_DELIVERY')
        await check_sales_followups(self.service)
        self.assertIsNone((await self.repo.get_opportunity(other.id)).next_follow_up_at)
        output = Path(os.environ['SALES_LIFECYCLE_EVIDENCE'])
        output.write_text(json.dumps({'source':'SYNTHETIC', 'model_calls':0, 'story':self.story,
            'handoff_card':'\n'.join(format_lead_timeline(*(await self.service.lead_timeline(op.id)))),
            'pipeline':format_pipeline_counts(await self.service.pipeline_counts()),
            'controls':['interest_not_win','incomplete_not_handoff','read_failure_not_silence','payment_promise_not_reserve','stale_dialogue_refused',
                        'unsent_blocks_second','stale_followup_rejected','restart_context',
                        'restart_handoff','duplicate_receipt','duplicate_incoming','rediscovery_preserves_handoff',
                        'same_client_two_projects','rejection_stops_sales']},
            ensure_ascii=False, indent=2), encoding='utf-8')

    async def test_followup_cadence_and_version_invalidation(self):
        op = await self.start_deal('990015503')
        await check_sales_followups(self.service)
        op = await self.repo.get_opportunity(op.id)
        for ordinal, hours in ((1, 12), (2, 24)):
            self.at = op.next_follow_up_at
            op, _, _ = await self.deal(op, 'dialogue', dict(thread=op.project_url, status='AVAILABLE_SYNCED_NO_NEW_REPLY'))
            await check_sales_followups(self.service)
            op = await self.repo.get_opportunity(op.id)
            pending = load(op)['pending_followup']
            draft = await self.repo.get_turn(pending['turn_id'])
            op, _, _ = await self.deal(op, 'followup_sent', dict(version=draft.reply_version, hash=draft.content_sha256))
            self.assertEqual(op.follow_up_count, ordinal)
            if ordinal == 1:
                self.assertEqual(op.next_follow_up_at, self.at + timedelta(hours=24))
            self.restart()
        self.assertIsNone(op.next_follow_up_at)
        self.at += timedelta(days=5)
        await check_sales_followups(self.service)
        self.assertEqual(len([t for t in await self.repo.list_turns(op.id) if t.intent == 'FOLLOW_UP']), 2)
        op = await self.prepare_terms(op)
        op, _ = await self.agree(op)
        op, _, _ = await self.deal(op, 'handoff', dict(version='1'))
        changed, _ = await self.incoming(op, 'Could you add three products? This is additional scope.')
        self.assertNotEqual(changed.opportunity.state, 'HANDOFF_READY')
        op = await self.repo.get_opportunity(op.id)
        self.assertFalse(load(op)['handoff']['valid'])
        self.assertNotIn('accepted', load(op)['terms'][-1])
        await self.deal(op, 'handoff', dict(version='1'), success=False)
        await self.deal(op, 'received', dict(version='1', hash=load(op)['handoff']['terms_hash']), role='VADIM', success=False)
        for req in await self.repo.list_human_requests(op.id):
            if req.status == 'OPEN':
                await self.handlers.cmd_answer_lead(self.message(f'/answer_lead {req.id} VADIM | SEPARATE_PAID_ESTIMATE'))
        op, _, _ = await self.deal(op, 'terms', dict(TERMS, scope='SYNTHETIC: SEO descriptions for 15 products',
            deliverables='15 texts with product IDs', acceptance_criteria='15 rows, up to 1000 characters, one revision',
            price='1500 UAH', payment_stages='One stage of 1500 UAH after acceptance',
            start_condition='3 days after stage reserve and 15 product cards',
            start_requirements='Reserve 1500 UAH; receive 15 product cards and keywords'))
        latest = load(op)['terms'][-1]
        self.assertEqual(latest['version'], 2)
        self.assertFalse(any(k in latest for k in ('sent','accepted','capacity','selection','start')))
        await self.deal(op, 'accept', dict(version='1', turn='old', statement='CLIENT_ACCEPTED_EXACT_TERMS'), success=False)
        self.assertEqual(digest(json.dumps(load(op)['terms'][0]['values'],ensure_ascii=False,sort_keys=True)),
                         load(op)['handoff']['terms_hash'])

    async def test_platform_pause_owner_guards_and_scope_isolation(self):
        op = await self.start_deal('990015504')
        await check_sales_followups(self.service)
        op = await self.repo.get_opportunity(op.id)
        self.at = op.next_follow_up_at
        notice = _email(op.project_id, 'SYNTHETIC: executor selected; workspace opened.', email_id='synthetic-status')
        await self.service.observe_platform_event(notice)
        self.restart()
        await check_sales_followups(self.service)
        paused = await self.repo.get_opportunity(op.id)
        self.assertIsNone(paused.next_follow_up_at)
        self.assertNotEqual(paused.state, 'HANDOFF_READY')
        self.assertFalse(load(paused).get('selected_ever'))
        self.assertFalse(any(t.intent == 'FOLLOW_UP' for t in await self.repo.list_turns(op.id)))
        # Read-only preview cannot record agreement or fabricate owner identity.
        preview = self.message(f'/deal {op.id} stop\nreference=SYNTHETIC no attestation')
        await self.handlers.cmd_deal(preview)
        self.assertFalse((await self.repo.get_opportunity(op.id)).do_not_follow_up)
        bad = self.message(f'/deal {op.id} stop\nreference=SYNTHETIC stranger | OWNER_CONFIRMS')
        bad.from_user.id = 123
        await self.handlers.cmd_deal(bad)
        self.assertFalse((await self.repo.get_opportunity(op.id)).do_not_follow_up)
        op, _, _ = await self.deal(op, 'stop', {})
        self.restart()
        op, _, _ = await self.deal(op, 'dialogue', dict(thread=op.project_url, status='AVAILABLE_SYNCED_NO_NEW_REPLY'))
        await check_sales_followups(self.service)
        self.assertTrue((await self.repo.get_opportunity(op.id)).do_not_follow_up)
        self.assertIsNone((await self.repo.get_opportunity(op.id)).next_follow_up_at)
