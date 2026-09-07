"""Build one allowlisted review delta; never collect env, pgdata or runtime logs."""
import ast
import difflib
import hashlib
import html
import json
import re
import subprocess
import zipfile

from issue15_review_delta import ROOT, OUT, FILES, STATE, LEDGER, ORIGINAL, sha, write

NEW = ['optidigital-agent/gmail_agent/tests/test_sales_lifecycle_review.py',
       'optidigital-agent/ops/issue15_review_delta.py', 'optidigital-agent/ops/issue15_package_delta.py']


def main():
    baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
    assert sha(LEDGER) == baseline['ledger_sha256']
    assert sha(ORIGINAL) == baseline['original_package_sha256']
    results = {mode: json.loads((OUT / (mode + '_results.json')).read_text(encoding='utf-8'))
               for mode in ('before', 'after', 'final', 'mechanical', 'neighbors', 'presentation')}
    assert results['before']['failures'] == 3 and results['before']['errors'] == 0
    for mode, report in results.items():
        if mode != 'before':
            assert report['result'] == 'PASS', mode
        assert report['ledger_unchanged'] and report['original_package_unchanged'] and not report['external_attempts']
    cleanup = json.loads((OUT / 'cleanup.json').read_text(encoding='utf-8'))
    assert cleanup['cluster_stopped'] and cleanup['remaining_test_schemas'] == 0
    changes = []
    diff = []
    for name in FILES + NEW + STATE:
        path = ROOT / name
        assert not path.is_symlink()
        value = path.read_text(encoding='utf-8')
        old = OUT / 'before' / name
        previous = old.read_text(encoding='utf-8') if old.exists() else ''
        delta = list(difflib.unified_diff(previous.splitlines(True), value.splitlines(True),
                                         fromfile='a/' + name if old.exists() else '/dev/null', tofile='b/' + name))
        diff.extend(delta)
        changes.append(dict(path=name, sha256=sha(path), added=sum(l.startswith('+') and not l.startswith('+++') for l in delta),
                            removed=sum(l.startswith('-') and not l.startswith('---') for l in delta)))
        if path.suffix == '.py':
            ast.parse(value)
    (OUT / 'review_delta.patch').write_text(''.join(diff), encoding='utf-8')
    git = lambda *args: subprocess.check_output(['git', '-c', 'core.quotepath=false', *args], cwd=ROOT, stderr=subprocess.DEVNULL).decode('utf-8')
    branch, head = git('branch', '--show-current').strip(), git('rev-parse', 'HEAD').strip()
    assert branch == baseline['branch'] and head == baseline['head']
    write('source_state.json', dict(root=str(ROOT), branch=branch, head=head, changes=changes,
        git_status=git('status', '--short'), full_dirty_diff_stat=git('diff', '--stat'),
        scope='delta against saved dirty pre-review sources, NOT all pre-existing HEAD changes',
        ledger_unchanged=True, original_package_unchanged=True))
    cards = json.loads((OUT / 'cards.json').read_text(encoding='utf-8'))
    def plain(value):
        return html.unescape(re.sub('<[^>]+>', '', value))
    card_sections = []
    for key, value in cards.items():
        if isinstance(value, str):
            card_sections.append('## ' + key + '\n\n```text\n' + plain(value) + '\n```\n')
        else:
            card_sections.append('## ' + key + '\n\n' + '\n'.join('### ' + field + '\n\n```text\n' + plain(content) + '\n```\n'
                                 for field, content in value.items()))
    (OUT / 'SYNTHETIC_CARDS.md').write_text('# Actual captured synthetic renderer/transport output\n\n'
        'Source: cards.json. These are synthetic fixtures, not live messages or sales proof.\n\n'
        + '\n'.join(card_sections), encoding='utf-8')
    checks = '\n'.join(f'| {mode} | {r["tests"]} | {r["failures"]}/{r["errors"]}/{r["skipped"]} | {r["result"]} |' for mode, r in results.items())
    file_list = '\n'.join('- `' + c['path'] + f'` (+{c["added"]}/−{c["removed"]})' for c in changes)
    report = f'''1. Оператор теперь автоматически получает внутреннюю задачу открыть точный диалог, когда follow-up наступил без свежего просмотра; после свежего подтверждения — черновик и следующий шаг. Доставка подключена к существующему bot/chat через зарегистрированный callback. В этом запуске получатель — только fake transport; production-флаг не включён.

2. «Можно начинать» не остаётся действующим после утраты обязательного условия: payment=REFUNDED/PROMISED/UNKNOWN при required=RESERVED инвалидирует ещё не полученный пакет и переводит HANDOFF_READY → CONTRACT_REVIEW в той же транзакции. Первый received независимо перепроверяет текущие условия, версию, hashes и подтверждения. Исторический snapshot/receipt не заменяется текущей оплатой.

# R1–R3 — локальный delta-отчёт

## 1. Цель и итог

COMPLETED — только три запрошенных механических исправления issue #15/#20.
Затронуты follow-up и передача согласованной работы команде, не продажи/модель.
Ожидаемый эффект — не терять внутреннее следующее действие и не начинать работу по утратившим силу prerequisites. Реальное увеличение выручки не измерялось.
Общий статус: IMPLEMENTED_WITH_VALIDATION_BLOCKERS.

## 2. Источник истины и границы

Root: `{ROOT}`.
Branch: `{branch}`. HEAD: `{head}`; не изменены.
Основание — собственный pasted request a14295f0; REVIEW_RU (3).md, probe_results (1).json и CODEX_NEXT_TASK (2).txt использованы как проверяемое ревью, не как расширение полномочий.
Сверены AGENTS.md и project-brain/legacy/reporting инструкции.
Сохранены грязный worktree и исходный a_to_b_review.zip. Delta считается относительно снимка перед R1–R3, а не относительно чистого HEAD. Полный накопленный git diff отдельно в source_state.json; прежние изменения не приписаны этому заданию.
Identity/публичное имя/профиль/скиллы/портфолио/аккаунты не проверялись и не менялись: вне этого локального задания. Роли и SINGLE_SHARED_OPERATOR проверяются существующими guards и соседними тестами, не означают независимую идентификацию человека.

## 3. Что изменено

R1: current_handoff_errors вызван атомарно перед первым receipt. Изменение фактов инвалидирует готовность; восстановление резерва само не оживляет invalid packet — нужен явный handoff. Предыдущий пакет переносится в handoff_history; сохранены events и confirmation snapshot. После receipt payment меняется отдельно, receipt/state IN_DELIVERY не переписывается. NONE допускается без оплаты. Renderer разделяет текущую оплату, исторический snapshot, статус готовности и последующие проблемы.

R2: pending/delivered и lease находятся в существующем lifecycle_json. Идентичность уведомления включает anchor/count/state/draft version/hash. Tick не посылает одну и ту же успешную карточку каждую минуту. Claim под opportunity-lock повторно проверяет актуальность и окно 08:00–21:00 Europe/Kyiv непосредственно перед транспортом. Сбой не ставит delivered; restart сохраняет pending. Новый ответ/отказ/stop отменяет отложенную работу. Устаревший ранее выбранный batch также перепроверяется при claim. Main передаёт существующие bot и TELEGRAM_CHAT_ID, второй бот/CRM/таблица/сервис не добавлены.

Ограничение сети: acknowledged success не повторяется, но crash после принятия Telegram до локального ack либо истечение lease при неопределённом ответе могут дать повтор. Универсальная exactly-once гарантия НЕ заявляется. Изменение состояния после последней DB-проверки уже в процессе внешней отправки невозможно атомарно отменить без общей транзакции с Telegram.

R3: буквальная команда из renderer остаётся с OWNER_CONFIRMS и version/hash. Если reference отсутствует, авторизованному оператору предлагается явный шаг 2; пока нет записи. Затем человек сам добавляет конкретный reference. Источник не выдумывается. Тест получает команду из настоящего HTML и вызывает cmd_deal напрямую, без deal-helper.

## 4. Проверки и фактические карточки

| Набор | Тесты | failures/errors/skips | Результат |
|---|---:|---:|---|
{checks}

before — три настоящих ожидаемых FAIL до исправления: valid после refund; 0 доставок callback; отказ буквальной команды из-за reference. after — первые 5 положительных проверок. final — расширенный набор: PostgreSQL-контроли и отдельные synthetic legacy/in-memory атомарные контроли. mechanical — повтор именно трёх прежних PostgreSQL-сценариев. neighbors — 55 shared-operator/v4/false-refusal проверок.
После основного запуска уточнены только подписи исторической ставки/старого snapshot и next-action при новых блокерах; presentation отдельно проверяет актуальный renderer на 13 отрицательных legacy-входах и recovery/dedup. Ранее захваченные PostgreSQL-карточки сохранены как фактический вывод того запуска, не отредактированы задним числом.
Полные карточки: SYNTHETIC_CARDS.md и исходный cards.json. Повтор исходной A→B истории: mechanical_evidence.json. Карточки получены реальным formatter; уведомления R2 — непосредственно из fake send_message, без ручного /lead.
R1 покрывает RESERVED→receipt (старые сценарии), RESERVED→RECEIVED→receipt, REFUNDED/PROMISED/UNKNOWN с restart, новый refund после receipt и NONE без payment записи. Отдельные 13 отрицательных входов проверяют stale legacy valid, отсутствующие подтверждения/вопросы/version/hash; отклонённый receipt не меняет сохранённые данные. Прямых SQL state hacks нет.
R2 покрывает зарегистрированный APScheduler callback, уведомление проверки/черновика, failure→pending→restart→success, отсутствие повторов подтверждённой доставки, рабочее окно, owner stop, новый incoming/rejection, stale batch, истечение crash lease.
R3 покрывает буквальный HTML action → handler prompt → явное синтетическое основание → сервисная запись; прежние owner/role/stale guards сохраняются.

Команды из worktree root (кэш зависимостей, offline):
```powershell
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py before
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py after
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py final
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py mechanical
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py neighbors
uv run --offline --python 3.12 --with-requirements optidigital-agent/requirements.txt python -X utf8 optidigital-agent/ops/issue15_review_delta.py presentation
```
before был выполнен до production-code edits; его нельзя воспроизвести как FAIL на исправленном коде без сохранённого before snapshot. Harness задаёт синтетические process settings, не читает env-файлы; сеть ограничена выделенной PostgreSQL 127.0.0.1:55432 (и loopback self-pipe Windows). Доказательство точной БД/роли входит в setup каждого PG-теста. Схемы созданы/удалены только тестами. Кластер остановлен; cleanup.json.

Исторический **175-test FAIL сохранён**: 4 freshness subtest failures в одном тесте NOW-at-import. Этот полный набор не повторялся; 55 соседних тестов не являются его новым общим PASS. Сбой fixture здесь не повторился, production freshness и старый fixture не ослаблялись.

## 5. Точные файлы

{len(changes)} файлов этого delta (включая тесты/ops/state; отчёты отдельно в private):

{file_list}

AST проверен для всех Python-файлов delta. Ruff F/E9 и git diff --check — см. static_checks.json. Дифф review_delta.patch включает только эти изменения поверх сохранённого dirty baseline. Известных незакрытых R1–R3 противоречий не найдено; исторические данные не выдаются за текущие. Финальные terms пока вручную вводит человек (15 полей), follow-up использует существующий шаблон и свежий self-attested просмотр; автоматические переговоры этим не доказаны.

## 6. Неизменное и блокеры

Новых model calls=0. Ledger **8/8**, reserve **$0.03262905**, весь файл ledger byte-unchanged. Исходный архив byte-unchanged. SALES_LIFECYCLE_ENABLED=false по умолчанию. Нет новых ключей/мастеров/env-правок, /me, браузера/поиска, billing/OAuth/Railway/production, commit/push/PR/merge/deploy/backfill, реальных Telegram/клиентских сообщений, ставок, договоров или оплат.
LIVE_MODEL_E2E=NOT_RUN в этом задании; LIVE_SALES_QUALITY=NOT_VALIDATED; LIVE_CLIENT_CYCLE=NOT_RUN; PRODUCTION_CHANGED=NO.
Живые ответы №7/№8 остаются непринятыми; локальная синтетика не исправляет их и не подтверждает funded revenue. Это блокер качества живых продаж, не препятствие закрытию локальных механических дефектов. Для текущего review не нужен новый ключ или платёжное действие.
Readiness: NOT_MEASURED → NOT_MEASURED. Улучшена механическая надёжность follow-up/handoff, не заявлена готовность deploy или автоматическое получение заказа.

## 7. Единственное следующее действие

Провести независимое ревью одного нового a_to_b_r1_r3_delta.zip по R1–R3, сопоставив review_delta.patch, результаты и фактические карточки.
'''
    (OUT / 'RESULT_RU.md').write_text(report, encoding='utf-8')
    archive = OUT / 'a_to_b_r1_r3_delta.zip'
    if archive.exists():
        raise RuntimeError('Delta archive already exists; do not overwrite')
    names = {('code/' + name): ROOT / name for name in FILES + NEW}
    names.update({('state/' + name): ROOT / name for name in STATE})
    names.update({('before/' + name): OUT / 'before' / name for name in FILES + STATE})
    for name in ['RESULT_RU.md', 'SYNTHETIC_CARDS.md', 'cards.json', 'mechanical_evidence.json', 'baseline.json',
                 'source_state.json', 'review_delta.patch', 'cleanup.json', 'static_checks.json'] + [m + '_results.json' for m in results]:
        names[name] = OUT / name
    # Preserve original 175-test evidence as historical, without overwriting or reclassifying it.
    names['historical/175_regression_results.json'] = ROOT / 'artifacts/private/a_to_b/regression_results.json'
    manifest = {}
    for name, path in names.items():
        assert path.is_file() and not path.is_symlink()
        data = path.read_bytes()
        assert not re.search(rb'sk-[A-Za-z0-9_-]{24,}|-----BEGIN [A-Z ]*PRIVATE KEY-----', data), name
        assert not any(p in name.lower().split('/') for p in ('pgdata', '.env', 'logs')), name
        manifest[name] = dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    write('manifest.json', manifest)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, path in names.items():
            z.write(path, name)
        z.write(OUT / 'manifest.json', 'manifest.json')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name, entry in manifest.items():
            assert hashlib.sha256(z.read(name)).hexdigest() == entry['sha256']
    assert sha(LEDGER) == baseline['ledger_sha256'] and sha(ORIGINAL) == baseline['original_package_sha256']
    write('package_validation.json', dict(members=len(names) + 1, all_payload_hashes_verified=True,
        archive_bytes=archive.stat().st_size, archive_sha256=sha(archive), ledger_unchanged=True, original_package_unchanged=True))
    print(json.dumps(dict(archive=str(archive), files=len(names) + 1, bytes=archive.stat().st_size)))


if __name__ == '__main__':
    main()
