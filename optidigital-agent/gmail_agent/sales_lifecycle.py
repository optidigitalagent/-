"""Pure 5B/5C rules, applied under the existing opportunity's transaction lock.

No network, model, payment or platform-write capability. Evidence entered by an
operator is always SELF_ATTESTED, including when a separate role ID is configured.
"""
from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from uuid import uuid4

from .commercial_terms import parse_money_terms, parse_timeline_terms
from .sales_storage import ConversationTurn, OpportunityTransition, _validate_transition

WAITING = {'BID_SUBMITTED', 'WAITING_CLIENT'}
STOPPED = {'LOST', 'CLOSED', 'MERGED', 'SELECTED', 'HANDOFF_READY', 'IN_DELIVERY'}
TERM_FIELDS = ('scope', 'deliverables', 'acceptance_criteria', 'boundaries', 'price',
               'timeline', 'payment_stages', 'start_condition', 'promises',
               'materials', 'access_location', 'risks', 'first_action',
               'start_requirements', 'payment_required_to_start')
OWNER_ACTIONS = {'dialogue', 'stop', 'terms', 'accept', 'select', 'start', 'payment',
                 'handoff', 'followup_sent'}
TEAM_ACTIONS = {'capacity', 'received'}
SYSTEM_ACTIONS = {'tick', 'platform_notice', 'notification_claim', 'notification_result'}


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def load(op):
    return json.loads(op.lifecycle_json or '{}')


def latest_incoming(turns):
    return max((t for t in turns if t.direction == 'INCOMING'),
               key=lambda t: (t.created_at, t.id), default=None)


def safe_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2400:
        raise ValueError('Concrete bounded text is required; no credentials.')
    if re.search(r'(?i)(?:sk-[a-z0-9_-]{8,}|bearer\s+\S+|-----BEGIN|'
                 r'(?:password|passwd|token|secret|пароль)\s*[:=]\s*\S+|'
                 r'https?://[^\s/]+@|https?://\S+[?]\S+)', value):
        raise ValueError('Secrets or credential-bearing links are forbidden; use a safe access location.')
    return value.strip()


def on_incoming(op, turns, incoming):
    """Atomic with the insert, before classification/generation can fail."""
    data = load(op)
    if not data and op.follow_up_status == 'DISABLED_5A':
        return
    op.next_follow_up_at = None
    op.follow_up_status = 'CANCELLED_CLIENT_REPLY'
    for t in turns:
        if t.intent == 'FOLLOW_UP' and t.direction == 'OUTGOING_DRAFT':
            t.direction = 'OUTGOING_SUPERSEDED'
    data.pop('dialogue', None)
    data.pop('pending_followup', None)
    for notice in data.get('followup_notifications', {}).values():
        if notice['status'] == 'PENDING':
            notice.update(status='CANCELLED', cancelled_at=incoming.created_at.isoformat(), reason='NEW_CLIENT_REPLY')
    terms = data.get('terms', [])
    if terms and op.state != 'IN_DELIVERY':
        # Even ambiguous new messages require reconfirmation, never inherit assent.
        terms[-1]['invalidated_by'] = incoming.id
        for key in ('accepted', 'capacity', 'selection', 'start'):
            terms[-1].pop(key, None)
        if data.get('handoff'):
            data['handoff']['valid'] = False
    if incoming.intent == 'REJECTION':
        op.do_not_follow_up = True
    data.setdefault('events', []).append({'id': 'incoming:' + incoming.id,
        'action': 'incoming', 'turn_id': incoming.id, 'source': incoming.source,
        'at': incoming.created_at.isoformat(), 'intent': incoming.intent})
    op.lifecycle_json = dump(data)
    if op.state == 'HANDOFF_READY':
        op.state = 'CONTRACT_REVIEW'
        return OpportunityTransition(id=uuid4().hex, opportunity_id=op.id,
            timestamp=incoming.created_at, source='sales_lifecycle:incoming',
            previous_state='HANDOFF_READY', new_state=op.state,
            reason='new client message invalidates unreceived handoff; explicit review required', actor='system')
    return None


def fresh_dialogue(op, data, turns, at):
    observation = data.get('dialogue', {})
    latest = latest_incoming(turns)
    if observation.get('status') != 'AVAILABLE_SYNCED_NO_NEW_REPLY':
        raise ValueError('DIALOGUE_NOT_VERIFIED: open the exact thread, sync missing turns and confirm availability.')
    checked = datetime.fromisoformat(observation['at'])
    if not 0 <= (at - checked).total_seconds() <= 120:
        raise ValueError('DIALOGUE_CHECK_STALE: confirm a fresh read (120 seconds).')
    if observation.get('incoming_id', '') != (latest.id if latest else ''):
        raise ValueError('NEW_CLIENT_REPLY: synchronize the thread; follow-up cancelled.')
    if (op.do_not_follow_up or op.state not in WAITING or data.get('selected_ever')
            or data.get('platform_notice') or observation.get('sales_status') != 'OPEN_WAITING_NO_SELECTION_NO_CONTRACT'):
        raise ValueError('FOLLOW_UP_FORBIDDEN: not an open waiting dialogue.')


def reconcile_sent(op, data, turns, confirmations, at, policy):
    """Recover timers from durable confirmations, including crash after send audit."""
    sent = sorted((c for c in confirmations if c.action in {'BID_SUBMITTED', 'BID_SENT', 'REPLY_SENT'}),
                  key=lambda c: (c.confirmed_at, c.id))
    for terms in data.get('terms', []):
        found = next((c for c in sent if c.reply_version == terms['reply_version']
                      and c.content_sha256 == terms['proposal_hash']), None)
        if found:
            terms['sent'] = {'confirmation_id': found.id, 'at': found.confirmed_at.isoformat()}
    if not sent or op.do_not_follow_up or op.state not in WAITING or data.get('selected_ever'):
        return
    anchor = sent[-1]
    incoming = latest_incoming(turns)
    if incoming and (incoming.detected_at or incoming.created_at) > anchor.confirmed_at:
        return
    if data.get('anchor_id') != anchor.id:
        data['anchor_id'] = anchor.id
        data['policy'] = policy
        data.pop('pending_followup', None)
        # Lifetime per-opportunity cap: client replies do not reset the count.
        op.next_follow_up_at = anchor.confirmed_at + timedelta(hours=policy['first_hours'])
        op.follow_up_status = 'SCHEDULED' if op.follow_up_count < policy['max_count'] else 'EXHAUSTED'
        if op.follow_up_status == 'EXHAUSTED':
            op.next_follow_up_at = None


def handoff_errors(op, data, requests):
    if not data.get('terms'):
        return ['record final terms with /deal terms']
    terms = data['terms'][-1]
    errors = [f'complete {key}' for key in TERM_FIELDS if not terms['values'].get(key)]
    for key in ('sent', 'accepted', 'capacity', 'selection', 'start'):
        if not terms.get(key):
            errors.append(f'confirm {key} for terms v{terms["version"]}')
    if terms.get('invalidated_by'):
        errors.append('reconfirm terms after the latest client message')
    if any(r.status == 'OPEN' for r in requests):
        errors.append('answer the open /answer_lead request')
    if op.unresolved_questions_json not in ('', '[]'):
        errors.append('resolve outstanding conversation questions through context sync')
    required = terms['values'].get('payment_required_to_start', 'UNKNOWN')
    payment = terms.get('payment', {}).get('status', 'UNKNOWN')
    if required == 'UNKNOWN' or required not in {'NONE', 'RESERVED', 'RECEIVED'}:
        errors.append('agree the payment prerequisite')
    elif required == 'RECEIVED' and payment != 'RECEIVED':
        errors.append('record actual receipt, not a promise or reserve')
    elif required == 'RESERVED' and payment not in {'RESERVED', 'RECEIVED'}:
        errors.append('record actual reserve/receipt, not a promise')
    if op.state in {'LOST', 'CLOSED', 'MERGED'}:
        errors.append('opportunity is closed')
    return errors


def current_handoff_errors(op, data, requests):
    """Check current facts, not the historical payment captured in the packet."""
    errors = handoff_errors(op, data, requests)
    packet = data.get('handoff', {})
    terms = (data.get('terms') or [{}])[-1]
    if not packet.get('valid'):
        errors.append('handoff invalidated; explicitly prepare it again')
    if (packet.get('version') != terms.get('version')
            or packet.get('terms_hash') != digest(dump(terms.get('values', {})))
            or packet.get('terms_hash') != digest(dump(packet.get('values', {})))
            or packet.get('proposal_hash') != terms.get('proposal_hash')):
        errors.append('handoff does not match current terms version/hash')
    return errors


def reconcile_notifications(op, data, turns, at):
    """Durable per-state/version internal outbox in the existing opportunity JSON."""
    from .sales_closer import notification_due_at
    key = ''
    draft = None
    eligible = (op.state in WAITING and not op.do_not_follow_up and not data.get('selected_ever')
        and not data.get('platform_notice') and op.next_follow_up_at and op.next_follow_up_at <= at
        and op.follow_up_count < data.get('policy', {}).get('max_count', 2))
    if eligible and op.follow_up_status in {'NEEDS_DIALOGUE_SYNC', 'DRAFT_AWAITING_OWNER'}:
        pending = data.get('pending_followup', {})
        draft = next((t for t in turns if t.id == pending.get('turn_id') and t.direction == 'OUTGOING_DRAFT'), None)
        # Recheck freshness at the locked claim boundary, not just on the earlier tick.
        needs_sync = False
        try:
            fresh_dialogue(op, data, turns, at)
        except ValueError:
            needs_sync = True
            op.follow_up_status = 'NEEDS_DIALOGUE_SYNC'
        else:
            if draft:
                op.follow_up_status = 'DRAFT_AWAITING_OWNER'
        # A fresh check can precede the draft-producing tick; its old status
        # must not keep an obsolete sync task eligible in that interval.
        if needs_sync or draft:
            key = ':'.join((str(data.get('anchor_id', '')), str(op.follow_up_count),
                op.follow_up_status, pending.get('version', ''), draft.content_sha256 if draft else ''))
            observation = data.get('dialogue', {})
            if (needs_sync and observation.get('status') == 'AVAILABLE_SYNCED_NO_NEW_REPLY'
                    and observation.get('sales_status') == 'OPEN_WAITING_NO_SELECTION_NO_CONTRACT'):
                # One renewal per expired check, not per tick/restart. Keep the
                # original no-observation and draft identities unchanged.
                key += ':check:' + (observation.get('event_id') or observation['at'])
    notices = data.setdefault('followup_notifications', {})
    for ident, notice in notices.items():
        if ident != key and notice['status'] == 'PENDING':
            notice.update(status='CANCELLED', cancelled_at=at.isoformat(), reason='STATE_OR_VERSION_CHANGED')
    if key:
        notice = notices.setdefault(key, {'id': key, 'kind': op.follow_up_status,
            'version': draft.reply_version if draft else '', 'hash': draft.content_sha256 if draft else '',
            'status': 'PENDING', 'created_at': at.isoformat(), 'due_at': notification_due_at(at).isoformat(),
            'attempts': 0})
        if notice['status'] == 'CANCELLED' and not notice.get('delivered_at'):
            notice.update(status='PENDING', due_at=notification_due_at(at).isoformat())
    return notices.get(key)


def apply_event(op, turns, requests, confirmations, event):
    """Mutate transaction-local dataclasses; caller commits all or nothing."""
    data = load(op)
    action, payload, at = event['action'], event['payload'], event['at']
    events = data.setdefault('events', [])
    signature = digest(dump({k: v for k, v in event.items() if k != 'at'}))
    old = next((e for e in events if e['id'] == event['id']), None)
    if old:
        if old.get('signature') != signature:
            raise ValueError('IDEMPOTENCY_CONFLICT: event ID was used for another action/payload/actor.')
        return None
    if action in OWNER_ACTIONS and event['actor_role'] != 'ADULT_OWNER':
        raise ValueError('ADULT_OWNER confirmation required')
    if action in TEAM_ACTIONS and event['actor_role'] not in {'ARTEM', 'VADIM'}:
        raise ValueError('ARTEM or VADIM fact source required')
    if action not in OWNER_ACTIONS | TEAM_ACTIONS | SYSTEM_ACTIONS:
        raise ValueError('Unknown lifecycle action')
    if action in SYSTEM_ACTIONS and event['actor_role'] != 'SYSTEM':
        raise ValueError('Application-only lifecycle action')
    if action not in SYSTEM_ACTIONS and (not event.get('actor_telegram_user_id') or not event.get('identity_assurance')):
        raise ValueError('Actor audit required')
    before = op.state
    allowed_payload = {
        'dialogue': {'thread', 'status', 'sales_status'}, 'stop': set(), 'tick': set(), 'platform_notice': set(),
        'terms': set(TERM_FIELDS), 'accept': {'version', 'turn', 'statement'},
        'select': {'version', 'turn', 'statement'}, 'capacity': {'version', 'statement'},
        'start': {'version', 'requirements', 'statement'}, 'payment': {'version', 'status'},
        'handoff': {'version'}, 'received': {'version', 'hash'}, 'followup_sent': {'version', 'hash'},
        'notification_claim': {'notice_id', 'lease'}, 'notification_result': {'notice_id', 'lease', 'outcome'},
    }[action] | {'reference'}
    if set(payload) - allowed_payload:
        raise ValueError('Unknown payload fields; use /deal help.')
    for value in payload.values():
        safe_text(value)
    if action not in {'tick', 'notification_claim', 'notification_result'} and not payload.get('reference'):
        raise ValueError('reference: name the concrete source personally checked (no credentials).')
    policy = event.get('policy', {'first_hours': 12, 'second_hours': 24, 'max_count': 2})
    if (not 0 < policy['first_hours'] <= 168 or not 0 < policy['second_hours'] <= 168
            or not 0 <= policy['max_count'] <= 2):
        raise ValueError('Invalid bounded follow-up policy')
    reconcile_sent(op, data, turns, confirmations, at, policy)
    evidence = {'event_id': event['id'], 'at': at.isoformat(),
                'source': 'OWNER_SELF_ATTESTED' if action in OWNER_ACTIONS else 'TEAM_SELF_ATTESTED',
                'actor_role': event['actor_role'], 'actor_telegram_user_id': event.get('actor_telegram_user_id'),
                'identity_assurance': event.get('identity_assurance'),
                'reference': safe_text(str(payload.get('reference', 'manual operator confirmation')))}
    if action in {'notification_claim', 'notification_result'}:
        current = reconcile_notifications(op, data, turns, at)
        notice = data.get('followup_notifications', {}).get(payload.get('notice_id'))
        if action == 'notification_claim':
            from .sales_closer import notification_due_at
            if (notice and notice is current and notice['status'] == 'PENDING'
                    and datetime.fromisoformat(notice['due_at']) <= at and notification_due_at(at) <= at
                    and (not notice.get('lease_until') or datetime.fromisoformat(notice['lease_until']) <= at)):
                notice.update(lease=payload['lease'], lease_until=(at + timedelta(minutes=2)).isoformat())
                notice['attempts'] += 1
        elif payload.get('outcome') not in {'DELIVERED', 'FAILED'}:
            raise ValueError('Explicit transport outcome required')
        elif notice and notice.get('lease') == payload.get('lease'):
            notice.pop('lease', None)
            notice.pop('lease_until', None)
            if payload['outcome'] == 'DELIVERED':
                # Keep even an in-flight cancellation's successful transport receipt.
                notice.update(status='DELIVERED', delivered_at=at.isoformat())
            else:
                notice['last_failure_at'] = at.isoformat()
    elif action == 'dialogue':
        if payload.get('thread') not in {op.thread_url, op.project_url} or not payload.get('thread'):
            raise ValueError('Exact opportunity thread/project URL required')
        status = payload.get('status')
        if status not in {'AVAILABLE_SYNCED_NO_NEW_REPLY', 'READ_FAILED', 'UNAVAILABLE', 'NEW_REPLY_SYNC_REQUIRED'}:
            raise ValueError('Explicit dialogue read status required')
        incoming = latest_incoming(turns)
        data['dialogue'] = dict(evidence, status=status, incoming_id=incoming.id if incoming else '',
                               sales_status=payload.get('sales_status', 'UNKNOWN'))
        if status == 'AVAILABLE_SYNCED_NO_NEW_REPLY' and payload.get('sales_status') == 'OPEN_WAITING_NO_SELECTION_NO_CONTRACT':
            data.pop('platform_notice', None)
            if not op.next_follow_up_at and data.get('anchor_id') and not data.get('pending_followup'):
                # Explicit fresh review may recover a paused timer, never reset its age/count.
                last = max((c for c in confirmations if c.action in {'BID_SENT', 'REPLY_SENT', 'FOLLOW_UP_SENT'}),
                           key=lambda c: c.confirmed_at, default=None)
                if last and op.follow_up_count < policy['max_count']:
                    hours = policy['second_hours'] if last.action == 'FOLLOW_UP_SENT' else policy['first_hours']
                    op.next_follow_up_at = last.confirmed_at + timedelta(hours=hours)
        if status != 'AVAILABLE_SYNCED_NO_NEW_REPLY':
            for t in turns:
                if t.intent == 'FOLLOW_UP' and t.direction == 'OUTGOING_DRAFT':
                    t.direction = 'OUTGOING_SUPERSEDED'
            data.pop('pending_followup', None)
            op.follow_up_status = 'NEEDS_DIALOGUE_SYNC'
    elif action in {'stop', 'platform_notice'}:
        if action == 'stop':
            op.do_not_follow_up = True
        else:
            data['platform_notice'] = dict(evidence, source='INGESTED_PLATFORM_NOTIFICATION_NOT_WIN_PROOF')
        op.next_follow_up_at = None
        op.follow_up_status = 'CANCELLED_OWNER' if action == 'stop' else 'PAUSED_PLATFORM_EVENT'
        for t in turns:
            if t.direction == 'OUTGOING_DRAFT' and t.intent == 'FOLLOW_UP':
                t.direction = 'OUTGOING_SUPERSEDED'
    elif action == 'tick':
        if (op.state in STOPPED or op.do_not_follow_up or data.get('selected_ever')):
            op.next_follow_up_at = None
            op.follow_up_status = 'STOPPED'
        elif op.follow_up_count >= policy['max_count']:
            op.next_follow_up_at = None
            op.follow_up_status = 'EXHAUSTED'
        elif op.next_follow_up_at and op.next_follow_up_at <= at:
            try:
                fresh_dialogue(op, data, turns, at)
            except ValueError:
                op.follow_up_status = 'NEEDS_DIALOGUE_SYNC'
            else:
                if data.get('pending_followup') and any(t.id == data['pending_followup']['turn_id'] and
                        t.direction == 'OUTGOING_DRAFT' for t in turns):
                    op.follow_up_status = 'DRAFT_AWAITING_OWNER'
                if not any(t.direction == 'OUTGOING_DRAFT' for t in turns):
                    incoming = latest_incoming(turns)
                    # A neutral reminder to choose a next step; no new price, discount or work promise.
                    from .sales_closer import _detected_reply_language
                    language = incoming.language if incoming else _detected_reply_language(op.initial_proposal)
                    content = {
                        'ru': 'Возвращаюсь к нашей пропозиции. Какой из описанных результатов нужно уточнить для вашего решения? Если задача больше не актуальна, сообщите, пожалуйста.',
                        'uk': 'Повертаюся до нашої пропозиції. Який із описаних результатів потрібно уточнити для вашого рішення? Якщо завдання більше не актуальне, повідомте, будь ласка.',
                        'en': 'Following up on our proposal. Which of the described deliverables needs clarification for your decision? Please let us know if the task is no longer relevant.',
                        'pl': 'Wracam do naszej propozycji. Który z opisanych rezultatów wymaga wyjaśnienia przed decyzją? Proszę dać znać, jeśli zadanie nie jest już aktualne.',
                    }.get(language)
                    if not content:
                        raise ValueError('Known client language required before preparing a follow-up.')
                    version = f'r{op.next_reply_sequence}'
                    op.next_reply_sequence += 1
                    turn = ConversationTurn(id=uuid4().hex, opportunity_id=op.id,
                        direction='OUTGOING_DRAFT', content=content, content_sha256=digest(content),
                        canonical_turn_identity=f'followup:{op.id}:{data["anchor_id"]}:{version}',
                        reply_version=version, source='APPLICATION_TEMPLATE_5B', intent='FOLLOW_UP', language=language,
                        source_reference_id=incoming.id if incoming else '',
                        incoming_gmail_message_id=incoming.gmail_message_id if incoming else '',
                        incoming_canonical_identity=incoming.canonical_turn_identity if incoming else '',
                        generated_at=at, created_at=at)
                    turns.append(turn)
                    data['pending_followup'] = {'turn_id': turn.id, 'version': version,
                        'anchor_id': data['anchor_id'], 'incoming_id': incoming.id if incoming else ''}
                    op.follow_up_status = 'DRAFT_AWAITING_OWNER'
    elif action == 'followup_sent':
        fresh_dialogue(op, data, turns, at)
        pending = data.get('pending_followup', {})
        turn = next((t for t in turns if t.id == pending.get('turn_id')), None)
        if (not turn or turn.direction != 'OUTGOING_DRAFT' or payload.get('version') != turn.reply_version
                or payload.get('hash') != turn.content_sha256 or digest(turn.content) != turn.content_sha256
                or pending.get('anchor_id') != data.get('anchor_id')):
            raise ValueError('STALE_FOLLOW_UP: exact current version/hash required')
        turn.direction = 'OUTGOING_CONFIRMED'
        turn.sent_at = at
        op.last_owner_message_at = at
        op.follow_up_count += 1
        data.pop('pending_followup', None)
        data.setdefault('followup_sends', []).append(dict(evidence, version=turn.reply_version, hash=turn.content_sha256))
        from .sales_storage import OwnerActionConfirmation, _verify_confirmation_identity_audit
        confirmation = OwnerActionConfirmation(id=uuid4().hex, opportunity_id=op.id,
            action='FOLLOW_UP_SENT', idempotency_key=f'FOLLOW_UP_SENT:{op.id}:{turn.reply_version}:{turn.content_sha256}',
            actor=event['actor'], actor_role=event['actor_role'], actor_telegram_user_id=event['actor_telegram_user_id'],
            reply_version=turn.reply_version, content_sha256=turn.content_sha256, confirmed_at=at,
            operator_mode=event['operator_mode'], identity_assurance=event['identity_assurance'],
            claimed_actor_role=event['actor_role'], attestation_version=event['attestation_version'],
            actual_telegram_user_id=event['actor_telegram_user_id'], claimed_at=at, action_confirmed_at=at)
        _verify_confirmation_identity_audit(confirmation)
        confirmations.append(confirmation)
        op.next_follow_up_at = (at + timedelta(hours=policy['second_hours'])
                               if op.follow_up_count < policy['max_count'] else None)
        op.follow_up_status = 'SCHEDULED' if op.next_follow_up_at else 'EXHAUSTED'
    elif action == 'terms':
        if op.state in STOPPED or op.state not in {'NEGOTIATING', 'SELECTION_REVIEW', 'CONTRACT_REVIEW'}:
            raise ValueError('Use current conversation/context and answer human input before final terms.')
        incoming = latest_incoming(turns)
        if not incoming or not op.bid_submitted_at:
            raise ValueError('Sync the exact submitted bid and current conversation first.')
        if any(r.status == 'OPEN' for r in requests):
            raise ValueError('Answer the open /answer_lead request before composing final terms.')
        values = {k: safe_text(payload[k]) for k in TERM_FIELDS if k in payload}
        if set(values) != set(TERM_FIELDS):
            raise ValueError('Missing final terms: ' + ', '.join(sorted(set(TERM_FIELDS) - set(values))))
        money, timeline = parse_money_terms(values['price']), parse_timeline_terms(values['timeline'])
        if money is None or timeline is None:
            raise ValueError('Explicit valid price/currency and timeline required')
        values['price'], values['timeline'] = money.canonical_model_text(), timeline.canonical_model_text()
        if values['payment_required_to_start'] not in {'NONE', 'RESERVED', 'RECEIVED'}:
            raise ValueError('Choose payment_required_to_start NONE, RESERVED or RECEIVED.')
        public_fields = ('scope', 'deliverables', 'acceptance_criteria', 'boundaries', 'price',
                         'payment_stages', 'timeline', 'start_condition', 'promises')
        content = '\n'.join(f'{k}: {values[k]}' for k in public_fields)
        from .quality_gate import contains_external_contact, contains_unsupported_case_or_capability_claim
        if contains_external_contact(content) or contains_unsupported_case_or_capability_claim(content):
            raise ValueError('Final terms violate existing contact/truthfulness guard')
        from .sales_closer import reply_quality_errors, ClientIntent
        # Owner-authored proposed terms are the explicit price/timeline source for
        # this composition only. The persisted original bid and acceptance stay unchanged.
        errors = reply_quality_errors(content,
            opportunity=replace(op, actual_submitted_price=values['price'], actual_submitted_timeline=values['timeline']),
            latest_message=incoming.content, language=incoming.language, intent=ClientIntent.NEGOTIATION,
            context_complete=bool(op.source_description and op.description_completeness == 'FULL'),
            confirmed_history=[t.content for t in turns if t.direction in {'INCOMING', 'OUTGOING_CONFIRMED'}])
        if errors:
            raise ValueError('FINAL_TERMS_QUALITY: ' + ', '.join(errors))
        history = data.setdefault('terms', [])
        version = len(history) + 1
        reply_version = f'r{op.next_reply_sequence}'
        op.next_reply_sequence += 1
        for t in turns:
            if t.direction == 'OUTGOING_DRAFT':
                t.direction = 'OUTGOING_SUPERSEDED'
        turn = ConversationTurn(id=uuid4().hex, opportunity_id=op.id, direction='OUTGOING_DRAFT',
            content=content, content_sha256=digest(content), canonical_turn_identity=f'terms:{op.id}:{version}',
            reply_version=reply_version, source_reference_id=incoming.id,
            incoming_gmail_message_id=incoming.gmail_message_id,
            incoming_canonical_identity=incoming.canonical_turn_identity,
            source='OWNER_CONFIRMED_TERMS', intent='FINAL_TERMS', generated_at=at, created_at=at)
        turns.append(turn)
        history.append({'version': version, 'values': values, 'proposed': evidence,
                        'reply_version': reply_version, 'proposal_hash': turn.content_sha256,
                        'quality_status': 'DETERMINISTIC_OWNER_TERMS_VALID'})
        op.state = 'NEGOTIATING'
        op.next_follow_up_at = None
        op.follow_up_status = 'CANCELLED_TERMS_REVISION'
    else:
        if not data.get('terms'):
            raise ValueError('Record concrete final terms first with /deal terms.')
        terms = data['terms'][-1]
        if str(payload.get('version')) != str(terms['version']):
            raise ValueError('STALE_TERMS: confirmation must name the current terms version.')
        if op.state in {'LOST', 'CLOSED', 'MERGED'}:
            raise ValueError('Closed opportunity cannot accept agreements or handoff.')
        if action in {'accept', 'select'}:
            if not terms.get('sent'):
                raise ValueError('Final terms must be confirmed sent, not just drafted.')
            turn = next((t for t in turns if t.id == payload.get('turn') and t.direction == 'INCOMING'), None)
            latest = latest_incoming(turns)
            if (not turn or not latest or turn.id != latest.id
                    or (turn.detected_at or turn.created_at) < datetime.fromisoformat(terms['sent']['at'])):
                raise ValueError('Use the current client message from this opportunity, after confirmed send.')
            evidence['turn_id'] = turn.id
            if action == 'accept':
                if payload.get('statement') != 'CLIENT_ACCEPTED_EXACT_TERMS':
                    raise ValueError('Explicit CLIENT_ACCEPTED_EXACT_TERMS owner attestation required; interest is not acceptance.')
                terms['accepted'] = evidence
                terms.pop('invalidated_by', None)
            else:
                if payload.get('statement') != 'CLIENT_SELECTED_OUR_TEAM' or not terms.get('accepted'):
                    raise ValueError('Explicit selected-our-team evidence and accepted final terms required.')
                terms['selection'] = evidence
                data['selected_ever'] = True
                op.state = 'CONTRACT_REVIEW'
                op.next_follow_up_at = None
                op.follow_up_status = 'STOPPED_SELECTED'
                for t in turns:
                    if t.direction == 'OUTGOING_DRAFT':
                        t.direction = 'OUTGOING_SUPERSEDED'
        elif action == 'capacity':
            if payload.get('statement') != 'TEAM_CAN_DELIVER_THIS_VERSION':
                raise ValueError('Explicit capacity confirmation for this exact version required.')
            terms['capacity'] = evidence
        elif action == 'payment':
            if payload.get('status') not in {'UNKNOWN', 'PROMISED', 'RESERVED', 'RECEIVED', 'REFUNDED'}:
                raise ValueError('Payment status must distinguish unknown, promise, reserve and receipt.')
            terms['payment'] = dict(evidence, status=payload['status'])
        elif action == 'start':
            if (payload.get('statement') != 'START_REQUIREMENTS_SATISFIED'
                    or payload.get('requirements') != terms['values']['start_requirements']):
                raise ValueError('Confirm the exact agreed start requirements, with an evidence reference.')
            terms['start'] = evidence
        elif action == 'handoff':
            if op.state == 'IN_DELIVERY' or data.get('handoff', {}).get('receipts'):
                raise ValueError('Handoff already received; retain historical receipt, record later facts separately.')
            errors = handoff_errors(op, data, requests)
            if errors:
                raise ValueError('HANDOFF_BLOCKED: ' + '; '.join(errors))
            if not data.get('handoff') or not data['handoff'].get('valid'):
                if data.get('handoff'):
                    data.setdefault('handoff_history', []).append(deepcopy(data['handoff']))
                data['handoff'] = {'id': f'handoff:{op.id}:v{terms["version"]}',
                    'version': terms['version'], 'terms_hash': digest(dump(terms['values'])),
                    'proposal_hash': terms['proposal_hash'], 'evidence': evidence, 'valid': True,
                    'values': deepcopy(terms['values']), 'payment': deepcopy(terms.get('payment', {'status': 'UNKNOWN'})),
                    'confirmation_snapshot': {k: deepcopy(terms[k]) for k in ('sent', 'accepted', 'capacity', 'selection', 'start')}}
            op.state = 'HANDOFF_READY'
            op.do_not_follow_up = True
            op.next_follow_up_at = None
            op.follow_up_status = 'STOPPED_HANDOFF'
            for t in turns:
                if t.direction == 'OUTGOING_DRAFT':
                    t.direction = 'OUTGOING_SUPERSEDED'
        elif action == 'received':
            handoff = data.get('handoff', {})
            if not handoff.get('valid') or op.state not in {'HANDOFF_READY', 'IN_DELIVERY'}:
                raise ValueError('No valid handoff package to receive.')
            if payload.get('hash') != handoff['terms_hash']:
                raise ValueError('Confirm the exact handoff version/hash.')
            if not handoff.get('receipts'):
                errors = current_handoff_errors(op, data, requests)
                if errors:
                    raise ValueError('HANDOFF_BLOCKED: ' + '; '.join(errors))
            handoff.setdefault('receipts', {}).setdefault(event['actor_role'], evidence)
            op.state = 'IN_DELIVERY'
    packet = data.get('handoff')
    if packet and packet.get('valid') and not packet.get('receipts'):
        errors = current_handoff_errors(op, data, requests)
        if errors:
            packet.update(valid=False, invalidated_at=at.isoformat(), invalidated_by=event['id'], invalidation_reasons=errors)
            if op.state == 'HANDOFF_READY':
                op.state = 'CONTRACT_REVIEW'
    reconcile_notifications(op, data, turns, at)
    if op.state != before:
        _validate_transition(before, op.state)
    if action not in {'tick', 'notification_claim', 'notification_result'}:
        events.append({'id': event['id'], 'signature': signature, 'action': action,
            'at': at.isoformat(), 'payload': payload, **{k: event[k] for k in
             ('actor_role', 'actor_telegram_user_id', 'identity_assurance', 'operator_mode', 'attestation_version')}})
    op.lifecycle_json = dump(data)
    op.updated_at = at
    if op.state != before:
        return OpportunityTransition(id=uuid4().hex, opportunity_id=op.id, timestamp=at,
            source='sales_lifecycle:' + action, previous_state=before, new_state=op.state,
            reason=action + ' / explicit local audit', actor=event['actor'],
            actor_role=event['actor_role'], actor_telegram_user_id=event.get('actor_telegram_user_id'))
    return None
