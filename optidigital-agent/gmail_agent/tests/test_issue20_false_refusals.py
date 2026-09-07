"""SYNTHETIC/MUTATION paired controls; no live completion or source refresh."""
import unittest

from gmail_agent.quality_gate import validate_analysis
from gmail_agent.tests import test_issue20_review_fix as review_fix
from gmail_agent.tests.test_issue20_review_fix import basis
from gmail_agent.tests.test_quality_gate_v2 import analysis


SOURCE = ('Нужны описания товаров до 1000 символов и отдельный текст о компании. '
          'Объём текста о компании не указан.')
BOT_SOURCE = ('Нужен телеграм-бот для уведомлений о заявках. Нужно принимать название, '
              'описание и дату заявки и отправлять уведомление в выбранный чат.')


async def controls():
    result = {}
    async def ask(**kw):
        return await review_fix.TestReviewFix.item(None, **kw)
    result['f1_client_mentions_team'] = await ask(
        action='Ask the client to confirm the reference our team must follow.')
    result['f1_wrong_recipient'] = await ask(action='Ask the team to supply the reference.')
    result['f1_wrong_recipient_mentions_client'] = await ask(
        action='Ask the team to supply the reference the client must follow.')
    result['f1_empty'] = await ask(action='')
    result['f1_recipient_only'] = await ask(action='client')
    result['f1_team_mentions_client'] = await ask(
        ask_basis=basis(owner='TEAM', fact_kind='TEAM_FACT', missing_fact='Available working hours',
                        source_quote='', absence_reason='Current capacity is not recorded.'),
        action='Ask the team to confirm working hours for the client.')
    result['f1_team_mentions_client'].clarification_question = 'How many working hours can the team allocate?'
    for name, fact, source, quote in (
        ('f2_company_unknown', 'Объём текста о компании', SOURCE, 'Объём текста о компании не указан.'),
        ('f2_product_known', 'Объём описания товара', SOURCE, ''),
        ('f2_company_known_despite_absence', 'Объём текста о компании',
         'Нужен текст о компании до 1000 символов.', ''),
    ):
        item = await ask(source=source, ask_basis=basis(missing_fact=fact, source_quote=quote,
            absence_reason='Объём не указан.', estimate_impact='Объём определяет часы работы.'),
            action=f'Уточнить у клиента {fact.lower()}.')
        item.language = 'ru'
        item.clarification_question = f'Какой {fact.lower()} нужен?'
        result[name] = item
    for name, source, case in (
        ('f3_cyrillic', BOT_SOURCE, 'BELLA_DENT'),
        ('f3_latin', BOT_SOURCE.replace('телеграм', 'Telegram'), 'BELLA_DENT'),
        ('f3_unrelated_audio', BOT_SOURCE, 'AUDIOBOOK_CLEANER'),
        ('f3_unrelated_shared_token', BOT_SOURCE + ' Нужен QA результата.', 'AUDIOBOOK_CLEANER'),
    ):
        result[name] = analysis(title='Бот уведомлений о заявках', full_description=source,
            evidence_case_id=case, evidence=source,
            why_relevant='The source requests a notification bot.',
            language='ru',
            proposal_draft='Здравствуйте! Реализую бот для уведомлений о заявках: название, описание '
                'и дату заявки проверю перед отправкой в выбранный чат. Добавлю проверку входных '
                'полей и проверю формат уведомления на согласованных примерах.')
    return result


EXPECTED = {
    'f1_client_mentions_team': (),
    'f1_wrong_recipient': ('ask_action_recipient_mismatch',),
    'f1_wrong_recipient_mentions_client': ('ask_action_recipient_mismatch',),
    'f1_empty': ('next_action_not_actionable', 'ask_action_recipient_mismatch'),
    'f1_recipient_only': ('next_action_not_actionable',),
    'f1_team_mentions_client': (),
    'f2_company_unknown': (),
    'f2_product_known': ('ask_fact_already_known',),
    'f2_company_known_despite_absence': ('ask_fact_already_known',),
    'f3_cyrillic': (),
    'f3_latin': (),
    'f3_unrelated_audio': ('evidence_selection_not_source_related',),
    'f3_unrelated_shared_token': ('evidence_selection_not_source_related',),
}


class TestFalseRefusals(unittest.IsolatedAsyncioTestCase):
    async def test_paired_full_gate_controls(self):
        for name, item in (await controls()).items():
            with self.subTest(synthetic_mutation=name):
                outcome = validate_analysis(item)
                self.assertEqual(set(outcome.errors), set(EXPECTED[name]))
                if not EXPECTED[name]:
                    expected = 'QUALITY_VALID' if name.startswith('f3') else 'QUALITY_NEEDS_CLARIFICATION'
                    self.assertEqual(outcome.status, expected)
                elif name.startswith('f3'):
                    self.assertEqual(outcome.status, 'QUALITY_MANUAL_REVIEW')
