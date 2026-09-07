"""Narrow freshness continuation of the existing isolated test harness."""
import asyncio
import json
import logging
import sys
import unittest
from unittest.mock import patch

import issue15_review_delta as runner

OUT = runner.ROOT / 'artifacts/private/a_to_b_r2_freshness'
PROTECTED = ['artifacts/private/a_to_b_r1_r3/a_to_b_r1_r3_delta.zip',
             'artifacts/private/a_to_b/regression_results.json']
CASE = 'gmail_agent.tests.test_sales_lifecycle_review.TestReview.'


def main():
    runner.OUT = OUT
    runner.FILES = ['optidigital-agent/gmail_agent/' + p for p in
                    ('sales_lifecycle.py', 'tests/test_sales_lifecycle_review.py')]
    mode = sys.argv[1]
    if mode == '--snapshot':
        result = runner.main()
        baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
        baseline['protected'] = {p: runner.sha(runner.ROOT / p) for p in PROTECTED}
        runner.write('baseline.json', baseline)
        return result
    baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
    assert all(runner.sha(runner.ROOT / p) == h for p, h in baseline['protected'].items())
    loader = unittest.defaultTestLoader.loadTestsFromNames
    names = [CASE + 'test_r2_restart_freshness_generation'] if mode == 'before' else [
        'gmail_agent.tests.test_sales_lifecycle_review']
    # Suppress only verbose asyncio scheduling diagnostics, never test failures.
    logging.getLogger('asyncio').setLevel(logging.ERROR)
    def load_suite(_):
        suite = loader(names)
        def quiet_loops(tests):
            for test in tests:
                if isinstance(test, unittest.TestSuite):
                    quiet_loops(test)
                elif isinstance(test, unittest.IsolatedAsyncioTestCase):
                    original = test.asyncSetUp
                    async def setup(original=original):
                        # Avoid costly Windows debug stack capture for every SQL
                        # await. Business validators, test clocks and TTL unchanged.
                        asyncio.get_running_loop().set_debug(False)
                        await original()
                    test.asyncSetUp = setup
        quiet_loops(suite)
        return suite
    with patch.object(unittest.defaultTestLoader, 'loadTestsFromNames', side_effect=load_suite):
        result = runner.main()
    assert all(runner.sha(runner.ROOT / p) == h for p, h in baseline['protected'].items())
    return result


if __name__ == '__main__':
    sys.exit(main())
