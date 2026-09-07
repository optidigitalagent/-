"""Offline review-delta harness; explicit file allowlist, isolated PostgreSQL only."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'artifacts/private/a_to_b_r1_r3'
FILES = ['optidigital-agent/' + p for p in (
    'gmail_agent/sales_lifecycle.py', 'gmail_agent/sales_closer.py',
    'gmail_agent/telegram_notifier.py', 'gmail_agent/scheduler.py',
    'bot/handlers.py', 'bot/main.py')]
STATE = ['.codex/project_brain/' + p + '.md' for p in ('DECISIONS', 'GOAL_PROGRESS', 'NEXT_ACTION')] + ['GOAL_PROGRESS.md']
LEDGER = ROOT / 'artifacts/private/issue20/live_model_budget.json'
ORIGINAL = ROOT / 'artifacts/private/a_to_b/a_to_b_review.zip'
URL = 'postgresql+asyncpg://issue20e2e@127.0.0.1:55432/issue20e2e'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def main():
    os.chdir(ROOT)
    OUT.mkdir(exist_ok=True, parents=True)
    if '--snapshot' in sys.argv:
        if (OUT / 'baseline.json').exists():
            raise RuntimeError('Snapshot already exists; never overwrite baseline')
        for name in FILES + STATE:
            dest = OUT / 'before' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8')
        write('baseline.json', dict(root=str(ROOT), branch=git('branch', '--show-current').strip(),
            head=git('rev-parse', 'HEAD').strip(), status=git('status', '--short'),
            diff_stat=git('diff', '--stat'), ledger_sha256=sha(LEDGER), original_package_sha256=sha(ORIGINAL)))
        return 0
    baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
    assert sha(LEDGER) == baseline['ledger_sha256'] and sha(ORIGINAL) == baseline['original_package_sha256']
    sys.path.insert(0, str(ROOT / 'optidigital-agent'))
    os.environ.update(DATABASE_URL=URL, TELEGRAM_TOKEN='123456789:synthetic_local_test_token_000000000',
        TELEGRAM_CHAT_ID='777', OPENAI_API_KEY='', GMAIL_ENABLED='false',
        FREELANCEHUNT_DISCOVERY_ENABLED='false', SALES_LIFECYCLE_ENABLED='false',
        SALES_LIFECYCLE_TEST_DATABASE_URL=URL, SALES_LIFECYCLE_EVIDENCE=str(OUT / 'mechanical_evidence.json'),
        REVIEW_DELTA_EVIDENCE=str(OUT / 'cards.json'))
    attempts = []
    real_connect = socket.socket.connect
    def local_only(sock, address):
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            attempts.append('blocked external socket')
            raise RuntimeError('External network forbidden')
        return real_connect(sock, address)
    real_async = asyncio.BaseEventLoop.create_connection
    async def isolated(loop, factory, host=None, port=None, **kw):
        if (host, port) != ('127.0.0.1', 55432):
            attempts.append('blocked external async connection')
            raise RuntimeError('Only isolated PostgreSQL permitted')
        return await real_async(loop, factory, host, port, **kw)
    mode = sys.argv[1]
    names = (['gmail_agent.tests.test_sales_lifecycle_postgres'] if mode == 'mechanical' else
        ['gmail_agent.tests.test_sales_closer_5a_shared_operator',
         'gmail_agent.tests.test_sales_closer_5a_v4', 'gmail_agent.tests.test_issue20_false_refusals'] if mode == 'neighbors' else
        ['gmail_agent.tests.test_sales_lifecycle_review'])
    if mode == 'before':
        names = ['gmail_agent.tests.test_sales_lifecycle_review.TestReview.' + n for n in
                 ('test_r1_refund_before_receipt', 'test_r2_registered_callback', 'test_r3_literal_renderer_action')]
    if mode == 'presentation':
        names = ['gmail_agent.tests.test_sales_lifecycle_review.TestReceiptAtomicGuards']
    with patch.object(socket.socket, 'connect', local_only), patch.object(asyncio.BaseEventLoop, 'create_connection', isolated):
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), skipped=len(result.skipped),
        external_attempts=attempts, ledger_unchanged=sha(LEDGER) == baseline['ledger_sha256'],
        original_package_unchanged=sha(ORIGINAL) == baseline['original_package_sha256'], model_calls=0,
        ledger='8/8', reserve_usd='0.03262905', result='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',
        details=[str(t) + '\n' + s for t, s in result.failures + result.errors])
    write(mode + '_results.json', report)
    print(json.dumps({k:v for k,v in report.items() if k != 'details'}))
    return 0 if report['result'] == 'PASS' else 1

if __name__ == '__main__':
    sys.exit(main())
