"""Bounded local synthetic integration. Never reads a secret env file or calls a model."""
import hashlib
import asyncio
import json
import os
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / 'optidigital-agent'
OUT = ROOT / 'artifacts/private/a_to_b'
URL = 'postgresql+asyncpg://issue20e2e@127.0.0.1:55432/issue20e2e'

def main():
    os.chdir(ROOT)  # BaseSettings must not discover the agent's .env.
    sys.path.insert(0, str(AGENT))
    os.environ.update(DATABASE_URL=URL, TELEGRAM_TOKEN='123456789:synthetic_local_test_token_000000000',
        TELEGRAM_CHAT_ID='777', OPENAI_API_KEY='', GMAIL_ENABLED='false',
        FREELANCEHUNT_DISCOVERY_ENABLED='false', SALES_LIFECYCLE_TEST_DATABASE_URL=URL,
        SALES_LIFECYCLE_EVIDENCE=str(OUT / 'mechanical_evidence.json'))
    ledger = ROOT / 'artifacts/private/issue20/live_model_budget.json'
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
    if before != baseline['ledger_sha256']:
        raise RuntimeError('Ledger changed since baseline; stop without modifying it.')
    attempts = []
    real_connect = socket.socket.connect
    def local_only(sock, address):
        # Windows asyncio.socketpair creates a loopback self-pipe on an ephemeral port.
        if not isinstance(address, tuple) or address[0] != '127.0.0.1':
            attempts.append(str(address))
            raise RuntimeError('External networking forbidden in mechanical test')
        return real_connect(sock, address)
    real_create_connection = asyncio.BaseEventLoop.create_connection
    async def isolated_async_connection(loop, factory, host=None, port=None, **kwargs):
        if (host, port) != ('127.0.0.1', 55432):
            attempts.append(str((host, port)))
            raise RuntimeError('Only the isolated PostgreSQL async connection is permitted')
        return await real_create_connection(loop, factory, host, port, **kwargs)
    regression = '--regression' in sys.argv
    focused = '--focused' in sys.argv
    if regression:
        os.environ['SALES_CLOSER_TEST_DATABASE_URL'] = URL
    with patch.object(socket.socket, 'connect', local_only), patch.object(
            asyncio.BaseEventLoop, 'create_connection', isolated_async_connection):
        suite = unittest.defaultTestLoader.loadTestsFromNames([
            'gmail_agent.tests.test_sales_closer_5a', 'gmail_agent.tests.test_sales_closer_5a_v2',
            'gmail_agent.tests.test_sales_closer_5a_v3', 'gmail_agent.tests.test_sales_closer_5a_v4',
            'gmail_agent.tests.test_sales_closer_5a_shared_operator', 'gmail_agent.tests.test_sales_closer_5a_postgres',
            'gmail_agent.tests.test_issue20_false_refusals', 'gmail_agent.tests.test_issue20_decision_first',
        ] if regression else ['gmail_agent.tests.test_issue20_false_refusals'] if focused
          else ['gmail_agent.tests.test_sales_lifecycle_postgres'])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = before == hashlib.sha256(ledger.read_bytes()).hexdigest()
    report = dict(tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        skipped=len(result.skipped), external_attempts=attempts, ledger_unchanged=unchanged,
        model_calls=0, ledger='8/8', reserve_usd='0.03262905',
        MECHANICAL_A_TO_B_TEST='PASS' if result.wasSuccessful() and result.testsRun and not result.skipped and unchanged and not attempts else 'FAIL',
        LIVE_SALES_QUALITY='NOT_VALIDATED', LIVE_CLIENT_CYCLE='NOT_RUN', PRODUCTION_CHANGED='NO',
        failures_detail=[str(test) + '\n' + detail for test, detail in result.failures + result.errors])
    if regression or focused:
        report['RELATED_REGRESSION'] = report.pop('MECHANICAL_A_TO_B_TEST')
    (OUT / ('focused_regression_results.json' if focused else 'regression_results.json' if regression else 'test_results.json')).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'failures_detail'},ensure_ascii=False))
    return 0 if report.get('MECHANICAL_A_TO_B_TEST', report.get('RELATED_REGRESSION')) == 'PASS' else 1

if __name__ == '__main__':
    sys.exit(main())
