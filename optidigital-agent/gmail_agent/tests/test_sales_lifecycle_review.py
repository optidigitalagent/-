"""R1–R3 regression: real PG/reducer/registered scheduler/handler; fake delivery only."""
import html
import inspect
import json
import os
from pathlib import Path
import re
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from gmail_agent.tests import test_sales_lifecycle_postgres as base
from gmail_agent.sales_lifecycle import load
from gmail_agent.scheduler import register_sales_followup_job
from gmail_agent.telegram_notifier import format_lead_timeline


@unittest.skipUnless(base.ENABLED, 'explicit isolated PostgreSQL opt-in')
class TestReview(unittest.IsolatedAsyncioTestCase):
    # Reuse only setup and explicitly synthetic input fixtures, not inherited tests.
    asyncSetUp = base.TestMechanicalLifecycle.asyncSetUp
    asyncTearDown = base.TestMechanicalLifecycle.asyncTearDown
    restart = base.TestMechanicalLifecycle.restart
    message = base.TestMechanicalLifecycle.message
    record = base.TestMechanicalLifecycle.record
    deal = base.TestMechanicalLifecycle.deal
    start_deal = base.TestMechanicalLifecycle.start_deal
    incoming = base.TestMechanicalLifecycle.incoming
    prepare_terms = base.TestMechanicalLifecycle.prepare_terms
    agree = base.TestMechanicalLifecycle.agree

    async def ready(self, project='990015601'):
        op = await self.prepare_terms(await self.start_deal(project))
        op, _ = await self.agree(op)
        return (await self.deal(op, 'handoff', {'version': '1'}))[0]

    def evidence(self, name, value):
        path = Path(os.environ['REVIEW_DELTA_EVIDENCE'])
        saved = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        saved[name] = value
        path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding='utf-8')

    async def test_r1_refund_before_receipt(self):
        op = await self.ready()
        snapshot = load(op)['handoff']
        op, _, _ = await self.deal(op, 'payment', {'version': '1', 'status': 'REFUNDED'})
        self.restart()
        op = await self.repo.get_opportunity(op.id)
        self.assertFalse(load(op)['handoff']['valid'], 'R1: refunded reserve must invalidate unreceived handoff')
        self.assertEqual(op.state, 'CONTRACT_REVIEW')
        await self.deal(op, 'received', {'version': '1', 'hash': snapshot['terms_hash']}, role='ARTEM', success=False)
        self.assertEqual(load(op)['handoff']['payment'], snapshot['payment'])
        card = '\n'.join(format_lead_timeline(*(await self.service.lead_timeline(op.id))))
        self.assertIn('Текущая оплата:</b> REFUNDED', card)
        self.assertIn('Исторический snapshot', card)
        self.evidence('R1_refunded_card', card)
        for bad_status in ('PROMISED', 'UNKNOWN'):
            await self.deal(op, 'payment', {'version': '1', 'status': 'RESERVED'})
            op, _, _ = await self.deal(op, 'handoff', {'version': '1'})
            await self.deal(op, 'payment', {'version': '1', 'status': bad_status})
            self.restart()
            await self.deal(op, 'received', {'version': '1', 'hash': snapshot['terms_hash']}, role='ARTEM', success=False)
            current = await self.repo.get_opportunity(op.id)
            self.assertFalse(load(current)['handoff']['valid'])
        await self.deal(op, 'payment', {'version': '1', 'status': 'RESERVED'})
        op, _, _ = await self.deal(op, 'handoff', {'version': '1'})
        self.assertEqual(len(load(op)['handoff_history']), 3)
        await self.deal(op, 'payment', {'version': '1', 'status': 'RECEIVED'})
        self.restart()
        op, _, _ = await self.deal(op, 'received', {'version': '1', 'hash': snapshot['terms_hash']}, role='ARTEM')
        receipt = load(op)['handoff']['receipts']
        self.assertEqual(op.state, 'IN_DELIVERY')
        op, _, _ = await self.deal(op, 'payment', {'version': '1', 'status': 'REFUNDED'})
        self.restart()
        op = await self.repo.get_opportunity(op.id)
        self.assertEqual(op.state, 'IN_DELIVERY')
        self.assertEqual(load(op)['handoff']['receipts'], receipt)
        self.assertEqual(load(op)['handoff']['payment']['status'], 'RESERVED')
        self.assertEqual(load(op)['terms'][-1]['payment']['status'], 'REFUNDED')
        self.evidence('R1_received_then_refunded', '\n'.join(format_lead_timeline(*(await self.service.lead_timeline(op.id)))))

    async def due(self, project='990015602'):
        op = await self.start_deal(project)
        await self.service.followup_tick()
        op = await self.repo.get_opportunity(op.id)
        # Deterministic Kyiv office hours on the following day, past the due time.
        self.at = (op.next_follow_up_at + timedelta(days=1)).replace(hour=9, minute=0, second=0)
        return op

    def registered(self, bot):
        scheduler = AsyncIOScheduler()
        kwargs = {'enabled': True, 'service': self.service}
        # Allows the before-fix run to reach the actual missing-delivery assertion.
        if 'bot' in inspect.signature(register_sales_followup_job).parameters:
            kwargs.update(bot=bot, chat_id=777)
        register_sales_followup_job(scheduler, **kwargs)
        job = scheduler.get_job('sales_followups')
        self.assertEqual(job.max_instances, 1)
        return job

    async def test_r2_registered_callback(self):
        op = await self.due()
        bot = type('FakeTransport', (), {'send_message': AsyncMock()})()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 1, 'R2: registered callback must notify without /lead')
        text = bot.send_message.await_args.kwargs['text']
        self.assertIn(op.project_url, text)
        self.assertIn('диалог', text)
        self.evidence('R2_automatic_check_card', text)
        self.restart()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)
        op, _, _ = await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 2)
        self.assertIn('followup_sent', bot.send_message.await_args.kwargs['text'])
        self.evidence('R2_automatic_draft_card', bot.send_message.await_args.kwargs['text'])
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 2)

    async def test_r2_restart_freshness_generation(self):
        op = await self.due('990015608')
        bot = type('FakeTransport', (), {'send_message': AsyncMock()})()
        trace = []

        async def checkpoint(phase):
            self.restart()
            current = await self.repo.get_opportunity(op.id)
            notices = load(current).get('followup_notifications', {})
            trace.append(dict(phase=phase, status=current.follow_up_status,
                observation=load(current).get('dialogue'), notices=notices,
                cards=[c.kwargs['text'] for c in bot.send_message.await_args_list]))
            self.evidence('R2_restart_freshness_generation', trace)
            return notices

        async def callback():
            self.restart()
            job = self.registered(bot)
            await job.func(**job.kwargs)

        await callback()
        notices = await checkpoint('initial due sync delivered')
        first_id = next(iter(notices))
        self.assertEqual(notices[first_id]['status'], 'DELIVERED')
        self.assertEqual(bot.send_message.await_count, 1)

        # A/B/D: each genuinely new check may expire once, but repeated ticks
        # for that same stale check must never create a new notification cycle.
        for cycle in (1, 2):
            await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
            notices = await checkpoint(f'fresh check {cycle}; no tick yet')
            self.assertFalse(any(n['status'] == 'PENDING' for n in notices.values()),
                             'Fresh dialogue must not enqueue a spurious sync task')
            self.at += timedelta(seconds=121)
            await callback()
            notices = await checkpoint(f'check {cycle} stale after restart')
            self.assertEqual(bot.send_message.await_count, 1 + cycle,
                             'Expired new observation must produce exactly one new sync card')
            self.assertEqual(notices[first_id]['status'], 'DELIVERED')
            for _ in range(3):
                self.at += timedelta(seconds=60)
                await callback()
            await checkpoint(f'repeated stale ticks {cycle}')
            self.assertEqual(bot.send_message.await_count, 1 + cycle)

        # C/D: a timely tick still creates/delivers the existing draft, not a
        # sync card. No state/version/transport implementation is mocked.
        await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        await checkpoint('fresh final check before timely tick')
        self.at += timedelta(seconds=30)
        await callback()
        await checkpoint('timely draft delivered')
        self.assertEqual(bot.send_message.await_count, 4)
        self.assertIn('followup_sent', bot.send_message.await_args.kwargs['text'])
        await callback()
        self.assertEqual(bot.send_message.await_count, 4)

        # Also cover a fresh check while the old sync notice is still pending:
        # it must cancel that obsolete task even before the draft-producing tick.
        other = await self.due('990015609')
        await self.service.followup_tick()  # persistence only; deliberate pending window
        self.restart()
        pending = load(await self.repo.get_opportunity(other.id))['followup_notifications']
        self.assertTrue(any(n['status'] == 'PENDING' for n in pending.values()))
        await self.deal(other, 'dialogue', {'thread': other.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        self.restart()
        notices = load(await self.repo.get_opportunity(other.id))['followup_notifications']
        self.assertFalse(any(n['status'] == 'PENDING' for n in notices.values()))
        self.evidence('R2_fresh_cancels_pending_sync', notices)

    async def test_r3_literal_renderer_action(self):
        op = await self.due('990015603')
        await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        await self.service.followup_tick()
        card = '\n'.join(format_lead_timeline(*(await self.service.lead_timeline(op.id))))
        literal = next(html.unescape(c) for c in re.findall(r'<code>(.*?)</code>', card, re.S) if 'followup_sent' in c)
        message = self.message(literal)
        await self.handlers.cmd_deal(message)  # deliberately NO deal helper and NO injected reference
        output = '\n'.join(c.args[0] for c in message.answer.await_args_list)
        self.assertIn('Шаг 2', output, 'R3: literal card action must request its missing evidence explicitly')
        self.assertNotIn('Действие не записано', output)
        self.assertEqual((await self.repo.get_opportunity(op.id)).follow_up_count, 0)
        # Explicit operator input, never an inferred source or a hidden helper default.
        supplied = literal.replace(' | OWNER_CONFIRMS', '\nreference=SYNTHETIC: владелица лично проверила отправленный текст в этом диалоге | OWNER_CONFIRMS')
        message = self.message(supplied)
        await self.handlers.cmd_deal(message)
        self.assertIn('Записано локальное подтверждение', message.answer.await_args_list[0].args[0])
        self.assertEqual((await self.repo.get_opportunity(op.id)).follow_up_count, 1)
        self.evidence('R3_literal_action', {'card': card, 'literal': literal, 'prompt': output, 'explicit_synthetic_input': supplied})

    async def test_r2_retry_restart_and_cancellation(self):
        op = await self.due('990015604')
        bot = type('FakeTransport', (), {'send_message': AsyncMock(side_effect=RuntimeError('SYNTHETIC transport failure'))})()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)
        current = await self.repo.get_opportunity(op.id)
        entries = list(load(current)['followup_notifications'].values())
        self.assertEqual([e['status'] for e in entries], ['PENDING'])
        self.assertNotIn('delivered_at', entries[0])
        self.restart()
        bot.send_message.side_effect = None
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 2)
        self.restart()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 2)
        await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        bot.send_message.side_effect = RuntimeError('SYNTHETIC failed draft delivery')
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 3)
        cached = await self.service.followup_tick()
        await self.incoming(op, 'We chose another freelancer. Not interested.')
        self.restart()
        bot.send_message.side_effect = None
        await self.service.deliver_followup_notifications(bot, 777, cached)
        self.assertEqual(bot.send_message.await_count, 3, 'Locked claim must reject a stale pre-cancellation batch')
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 3)
        self.assertFalse(any(e['status'] == 'PENDING' for e in load(await self.repo.get_opportunity(op.id))['followup_notifications'].values()))

    async def test_r2_office_window_and_owner_cancel(self):
        op = await self.due('990015605')
        # Kyiv 22:00 in September: keep pending until 08:00 local next morning.
        self.at = self.at.replace(hour=19)
        bot = type('FakeTransport', (), {'send_message': AsyncMock()})()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 0)
        self.assertTrue(load(await self.repo.get_opportunity(op.id))['followup_notifications'])
        self.restart()
        self.at += timedelta(hours=9)
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 0)
        self.at += timedelta(hours=1)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)
        await self.deal(op, 'dialogue', {'thread': op.project_url, 'status': 'AVAILABLE_SYNCED_NO_NEW_REPLY'})
        await self.service.followup_tick()
        await self.deal(op, 'stop', {})
        self.restart()
        job = self.registered(bot)
        await job.func(**job.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)

    async def test_r1_no_prepayment_required(self):
        values = dict(base.TERMS, payment_required_to_start='NONE',
            payment_stages='1200 UAH after acceptance; no advance payment or reserve required',
            start_condition='3 days after product cards received',
            start_requirements='12 product cards and keywords received')
        with patch.dict(base.TERMS, values):
            op = await self.prepare_terms(await self.start_deal('990015606'))
        result, _ = await self.incoming(op, 'We selected your team and accept the exact final proposal: '
            '12 descriptions, 1200 UAH, 3 days after product cards; no advance payment or reserve required.')
        for action, payload, role in (
            ('accept', dict(turn=result.incoming_turn.id, statement='CLIENT_ACCEPTED_EXACT_TERMS'), 'OWNER_CONFIRMS'),
            ('select', dict(turn=result.incoming_turn.id, statement='CLIENT_SELECTED_OUR_TEAM'), 'OWNER_CONFIRMS'),
            ('capacity', dict(statement='TEAM_CAN_DELIVER_THIS_VERSION'), 'VADIM'),
            ('start', dict(requirements=values['start_requirements'], statement='START_REQUIREMENTS_SATISFIED'), 'OWNER_CONFIRMS'),
            ('handoff', {}, 'OWNER_CONFIRMS')):
            op, _, _ = await self.deal(op, action, dict(payload, version='1'), role=role)
        self.assertNotIn('payment', load(op)['terms'][-1])
        self.restart()
        op, _, _ = await self.deal(op, 'received', {'version': '1', 'hash': load(op)['handoff']['terms_hash']}, role='VADIM')
        self.assertEqual(op.state, 'IN_DELIVERY')
        self.evidence('R1_no_prepayment', '\n'.join(format_lead_timeline(*(await self.service.lead_timeline(op.id)))))


class TestReceiptAtomicGuards(unittest.IsolatedAsyncioTestCase):
    """Explicit synthetic legacy/corrupt snapshots; no direct SQL or real opportunity state edits."""
    async def fixture(self):
        from copy import deepcopy
        from gmail_agent.sales_lifecycle import dump, digest
        from gmail_agent.sales_storage import InMemorySalesRepository, SalesOpportunity
        values = dict(base.TERMS)
        evidence = {'source': 'SYNTHETIC_FIXTURE'}
        terms = dict(version=1, values=values, proposal_hash=digest('SYNTHETIC final proposal'), reply_version='r1',
            **{k: evidence for k in ('sent', 'accepted', 'selection', 'capacity', 'start')},
            payment={'status': 'RESERVED'})
        packet = dict(id='SYNTHETIC legacy packet', version=1, values=deepcopy(values), valid=True,
            terms_hash=digest(dump(values)), proposal_hash=terms['proposal_hash'], payment={'status': 'RESERVED'})
        op = SalesOpportunity(id='SYNTHETIC_UNIT', identity_key='SYNTHETIC_UNIT', title='SYNTHETIC legacy snapshot',
            state='HANDOFF_READY', lifecycle_json=dump({'terms': [terms], 'handoff': packet}))
        repo = InMemorySalesRepository()
        await repo.ensure_opportunity(op, reason='explicit synthetic unit input', actor='system')
        return repo, op, terms, packet

    async def test_received_rechecks_legacy_valid_flag_and_all_current_prerequisites(self):
        from datetime import datetime, timezone
        from gmail_agent.sales_lifecycle import dump
        # Deliberately inconsistent INPUT fixtures exercise receipt's independent guard,
        # rather than relying only on the payment event's invalidation.
        for defect in ('REFUNDED', 'PROMISED', 'UNKNOWN', 'sent', 'accepted', 'capacity', 'selection', 'start',
                       'version', 'terms_hash', 'proposal_hash', 'valid', 'unresolved'):
            with self.subTest(defect=defect):
                repo, op, terms, packet = await self.fixture()
                if defect in {'REFUNDED', 'PROMISED', 'UNKNOWN'}:
                    terms['payment']['status'] = defect
                elif defect in {'sent', 'accepted', 'capacity', 'selection', 'start'}:
                    terms.pop(defect)
                elif defect == 'version':
                    packet['version'] = 0
                elif defect in {'terms_hash', 'proposal_hash'}:
                    packet[defect] = 'SYNTHETIC_MISMATCH'
                elif defect == 'valid':
                    packet['valid'] = False
                else:
                    op.unresolved_questions_json = '["SYNTHETIC unanswered question"]'
                op.lifecycle_json = dump({'terms': [terms], 'handoff': packet})
                # Separate fixture repository: immutable inputs, not a state-transition shortcut.
                from gmail_agent.sales_storage import InMemorySalesRepository
                repo = InMemorySalesRepository()
                await repo.ensure_opportunity(op, reason='explicit negative unit fixture', actor='system')
                card = '\n'.join(format_lead_timeline(op, [], [], []))
                self.assertIn('NOT_READY', card)
                self.assertIn('текущая готовность не подтверждена', card)
                before = (await repo.get_opportunity(op.id)).lifecycle_json
                with self.assertRaises(ValueError):
                    await repo.apply_lifecycle_event(op.id, dict(id='synthetic-receipt', action='received',
                        payload={'version': '1', 'hash': packet['terms_hash'], 'reference': 'SYNTHETIC team receipt'},
                        at=datetime.now(timezone.utc), actor='Artem', actor_role='ARTEM', actor_telegram_user_id=123,
                        identity_assurance='SYNTHETIC', operator_mode='SEPARATE_ROLES', attestation_version=''))
                restarted = InMemorySalesRepository(repo.state)
                self.assertEqual((await restarted.get_opportunity(op.id)).state, 'HANDOFF_READY')
                self.assertEqual((await restarted.get_opportunity(op.id)).lifecycle_json, before)

    async def test_notification_claim_recovery_and_known_success(self):
        from datetime import datetime, timezone
        from gmail_agent.sales_lifecycle import dump
        from gmail_agent.sales_storage import InMemorySalesRepository, SalesOpportunity
        from gmail_agent.sales_closer import SalesCloserService
        at = datetime(2026, 9, 7, 9, tzinfo=timezone.utc)
        op = SalesOpportunity(id='SYNTHETIC_NOTICE', identity_key='SYNTHETIC_NOTICE', title='SYNTHETIC recovery',
            state='BID_SUBMITTED', project_url='https://freelancehunt.com/project/synthetic/990015607.html',
            bid_submitted_at=at-timedelta(days=1), next_follow_up_at=at-timedelta(hours=1),
            follow_up_status='NEEDS_DIALOGUE_SYNC', lifecycle_json=dump({'anchor_id': 'SYNTHETIC_ANCHOR'}))
        repo = InMemorySalesRepository()
        await repo.ensure_opportunity(op, reason='SYNTHETIC recovery fixture', actor='system')
        service = SalesCloserService(repo, now=lambda: at, followup_enabled=True)
        ops = await service.followup_tick()
        ident = next(iter(load(ops[0])['followup_notifications']))
        await repo.apply_lifecycle_event(op.id, dict(id='synthetic-claim', action='notification_claim',
            payload={'notice_id': ident, 'lease': 'SYNTHETIC_CRASHED_WORKER'}, at=at, actor='system',
            actor_role='SYSTEM', identity_assurance='APPLICATION'))
        repo = InMemorySalesRepository(repo.state)
        service = SalesCloserService(repo, now=lambda: at, followup_enabled=True)
        bot = type('FakeTransport', (), {'send_message': AsyncMock()})()
        job = AsyncIOScheduler()
        register_sales_followup_job(job, enabled=True, service=service, bot=bot, chat_id=777)
        callback = job.get_job('sales_followups')
        await callback.func(**callback.kwargs)
        self.assertEqual(bot.send_message.await_count, 0)
        at += timedelta(minutes=2)
        await callback.func(**callback.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)
        await callback.func(**callback.kwargs)
        self.assertEqual(bot.send_message.await_count, 1)
