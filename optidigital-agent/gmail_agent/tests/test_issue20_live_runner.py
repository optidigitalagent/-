"""Offline enforcement tests for the bounded issue #20 live runner."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from openai import APIConnectionError, AsyncOpenAI, APITimeoutError

from ops import issue20_live_e2e as live


class TestPersistentLiveBudget(unittest.IsolatedAsyncioTestCase):
    async def test_isolated_schema_uses_existing_additive_migrations(self):
        connection = SimpleNamespace(
            run_sync=AsyncMock(),
            execute=AsyncMock(),
        )
        engine = MagicMock()
        engine.begin.return_value.__aenter__ = AsyncMock(return_value=connection)
        engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
        create_all = MagicMock()
        base = SimpleNamespace(metadata=SimpleNamespace(create_all=create_all))

        await live._prepare_isolated_schema(
            engine,
            base,
            ("ALTER TABLE example ADD COLUMN IF NOT EXISTS value TEXT",),
        )

        connection.run_sync.assert_awaited_once_with(create_all)
        connection.execute.assert_awaited_once()
        self.assertIn("ADD COLUMN IF NOT EXISTS", str(connection.execute.call_args.args[0]))

    def test_new_provider_failure_is_detected_without_reissuing_request(self):
        historical = {"sequence": 1, "status": "FAILED"}
        current = {"sequence": 2, "status": "FAILED", "http_status": 429}
        ledger = {"calls": [historical, current]}

        self.assertIs(live._new_failed_provider_call(ledger, 1), current)
        self.assertIsNone(live._new_failed_provider_call(ledger, 2))

    def test_live_runner_accepts_only_dedicated_loopback_database(self):
        allowed = (
            "postgresql+asyncpg://issue20e2e@127.0.0.1:55432/issue20e2e"
        )
        self.assertEqual(live._validate_isolated_database_url(allowed), allowed)
        rejected = (
            "postgresql+asyncpg://issue20e2e@127.0.0.1:5432/issue20e2e",
            "postgresql+asyncpg://issue20e2e@example.com:55432/issue20e2e",
            "postgresql+asyncpg://issue20e2e@127.0.0.1:55432/production",
            "postgresql+asyncpg://issue20e2e:secret@127.0.0.1:55432/issue20e2e",
            "postgresql+asyncpg://issue20e2e@127.0.0.1:55432/issue20e2e?ssl=1",
        )
        for database_url in rejected:
            with self.subTest(database_url=database_url):
                with self.assertRaisesRegex(RuntimeError, "dedicated loopback"):
                    live._validate_isolated_database_url(database_url)

    def test_live_runner_requires_bounded_verified_private_scope_snapshot(self):
        verified_at = datetime.now(timezone.utc).isoformat()
        description = "Synthetic verified public scope."
        valid = {
            "project_id": "990020003",
            "url": (
                "https://freelancehunt.com/project/synthetic/990020003.html"
            ),
            "full_description": description,
            "verified_at": verified_at,
            "description_completeness": "FULL",
            "materials_status": "UNAVAILABLE_EXECUTION_INPUTS_ONLY",
            "scope_sufficiency": "SUFFICIENT_FOR_FIXED_TERMS",
            "source_kind": "PUBLIC_PAGE_VERIFIED",
            "rss_source_url": "https://freelancehunt.com/projects.rss",
            "rss_source_identity": "official-public-rss:990020003",
            "rss_fetched_at": verified_at,
            "rss_feed_timestamp": verified_at,
            "rss_entry_sha256": "a" * 64,
            "rss_budget": "",
            "rss_budget_currency": "",
            "full_text_source_url": (
                "https://freelancehunt.com/project/synthetic/990020003.html"
            ),
            "full_text_fetched_at": verified_at,
            "full_text_sha256": hashlib.sha256(
                description.encode("utf-8")
            ).hexdigest(),
            "source_budget": "",
            "source_budget_currency": "",
            "source_budget_status": "NOT_SPECIFIED",
            "source_budget_source": "NOT_SPECIFIED",
            "materials_evidence": (
                "Synthetic execution inputs are unavailable before start."
            ),
            "scope_sufficiency_basis": "Synthetic bounded test scope.",
            "remaining_unknowns": ["Synthetic execution input."],
            "manual_scope_assessment": True,
            "manual_scope_assessment_basis": (
                "Synthetic test fixture judgment."
            ),
            "live_status": "ACTIVE_BIDDABLE",
            "live_status_biddable": True,
            "live_status_source": "Synthetic checker",
            "live_status_checked_at": verified_at,
            "live_status_evidence": "Synthetic current RSS membership.",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "candidate.json"
            path.write_text(json.dumps(valid), encoding="utf-8")
            with patch.object(live, "ARTIFACT_DIR", root):
                loaded = live._load_verified_candidate_scope(str(path))
                self.assertEqual(loaded["project_id"], "990020003")

                unsafe = dict(valid, source_kind="SYNTHETIC_TEST")
                path.write_text(json.dumps(unsafe), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "PUBLIC_PAGE_VERIFIED"):
                    live._load_verified_candidate_scope(str(path))

                unsafe = dict(
                    valid,
                    materials_status="UNAVAILABLE_SCOPE_RELEVANT",
                    scope_sufficiency="SUFFICIENT_FOR_FIXED_TERMS",
                )
                path.write_text(json.dumps(unsafe), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "cannot authorize terms"):
                    live._load_verified_candidate_scope(str(path))

                unsafe = dict(
                    valid,
                    url=(
                        "https://user:secret@freelancehunt.com/project/"
                        "synthetic/990020003.html"
                    ),
                )
                path.write_text(json.dumps(unsafe), encoding="utf-8")
                with self.assertRaisesRegex(RuntimeError, "safe matching"):
                    live._load_verified_candidate_scope(str(path))

    def test_truthful_non_take_outcomes_do_not_require_proposal_or_5a(self):
        rendered = ["decision card"]
        for decision, quality, status in (
            ("ASK", "NEEDS_CLARIFICATION", "needs_clarification"),
            ("SKIP", "NON_EXECUTABLE", "skipped"),
        ):
            with self.subTest(decision=decision):
                record = SimpleNamespace(
                    commercial_decision=decision,
                    analysis_quality_status=quality,
                    status=status,
                    proposal_draft="",
                    recommended_price="",
                    realistic_timeline="",
                    proposal_content_sha256="",
                    proposal_version="",
                )
                checks = live._outcome_checks(
                    record,
                    proposal_ready=False,
                    rendered=rendered,
                    telegram_messages=rendered,
                    opportunity=None,
                )
                self.assertTrue(all(checks.values()), checks)

    async def test_authorized_call_limit_survives_new_wrapper_and_blocks_next(self):
        response = SimpleNamespace(
            model="gpt-4o-mini-2024-07-18",
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
        )
        create = AsyncMock(return_value=response)
        inner = SimpleNamespace(create=create)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(live, "ARTIFACT_DIR", root),
                patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                patch.object(live, "COMPLETION_REPLAY_PATH", root / "completion.json"),
                patch.object(live, "STEP_CALL_CEILING", live.MAX_CALLS),
            ):
                for _ in range(live.MAX_CALLS // 2):
                    await live.BudgetedCompletions(inner).create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "bounded"}],
                        max_tokens=100,
                    )
                # A new process-equivalent wrapper reads the same ledger.
                restarted = live.BudgetedCompletions(inner)
                for _ in range(live.MAX_CALLS - live.MAX_CALLS // 2):
                    await restarted.create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "bounded"}],
                        max_tokens=100,
                    )
                with self.assertRaisesRegex(RuntimeError, "call limit exhausted"):
                    await live.BudgetedCompletions(inner).create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "blocked"}],
                        max_tokens=100,
                    )
                ledger = live._load_ledger()
                self.assertEqual(len(ledger["calls"]), live.MAX_CALLS)
                self.assertEqual(create.await_count, live.MAX_CALLS)
                self.assertLess(
                    sum(item["upper_bound_usd"] for item in ledger["calls"]),
                    live.MAX_USD,
                )

    async def test_current_step_ceiling_blocks_more_than_two_new_calls(self):
        response = SimpleNamespace(
            model="gpt-4o-mini-2024-07-18",
            usage=SimpleNamespace(
                prompt_tokens=100,
                completion_tokens=50,
                total_tokens=150,
            ),
            choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))],
        )
        create = AsyncMock(return_value=response)
        inner = SimpleNamespace(create=create)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            historical = {
                "version": 1,
                "model": live.MODEL,
                "max_calls": live.MAX_CALLS,
                "max_usd": live.MAX_USD,
                "sdk_max_retries": 0,
                "pricing": {
                    "source": live.PRICING_SOURCE,
                    "input_usd_per_million": live.INPUT_USD_PER_MILLION,
                    "output_usd_per_million": live.OUTPUT_USD_PER_MILLION,
                },
                "calls": [
                    {
                        "sequence": 1,
                        "status": "FAILED",
                        "upper_bound_usd": 0.001,
                    },
                    {
                        "sequence": 2,
                        "status": "FAILED",
                        "upper_bound_usd": 0.001,
                    },
                ],
            }
            ledger_path = root / "ledger.json"
            historical["calls"] = [dict(sequence=i, status="FAILED", upper_bound_usd=0.001) for i in range(1, live.STEP_BASELINE_CALLS + 1)]
            ledger_path.write_text(json.dumps(historical), encoding="utf-8")
            with (
                patch.object(live, "ARTIFACT_DIR", root),
                patch.object(live, "LEDGER_PATH", ledger_path),
                patch.object(live, "COMPLETION_REPLAY_PATH", root / "completion.json"),
            ):
                wrapper = live.BudgetedCompletions(inner)
                for _ in range(2):
                    await wrapper.create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "bounded"}],
                        max_tokens=100,
                    )
                with self.assertRaisesRegex(RuntimeError, "current-step|call limit"):
                    await wrapper.create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "blocked"}],
                        max_tokens=100,
                    )
                self.assertEqual(create.await_count, 2)
                self.assertEqual(len(live._load_ledger()["calls"]), live.STEP_CALL_CEILING)

    async def test_new_step_failure_blocks_retry_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                  patch.object(live, "REPORT_PATH", root / "report.json")):
                ledger = live._load_ledger()
                ledger["calls"] = [dict(sequence=i, status="FAILED", upper_bound_usd=0.001) for i in range(1, live.STEP_BASELINE_CALLS + 1)]
                live._write_json(live.LEDGER_PATH, ledger)
                inner = SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("offline transport failure")))
                with self.assertRaisesRegex(RuntimeError, "offline transport failure"):
                    await live.BudgetedCompletions(inner).create(model=live.MODEL, max_tokens=16, messages=[])
                with self.assertRaisesRegex(RuntimeError, "closed after"):
                    await live.BudgetedCompletions(inner).create(model=live.MODEL, max_tokens=16, messages=[])
                self.assertEqual(inner.create.await_count, 1)
                self.assertEqual(len(live._load_ledger()["calls"]), live.STEP_BASELINE_CALLS + 1)

    async def test_live_client_blocks_wrong_host_and_redirect(self):
        observed = []
        def handler(request):
            observed.append(str(request.url))
            return httpx.Response(302, headers={"location": "https://example.invalid/steal"}, request=request)
        with patch.object(live.httpx, "AsyncHTTPTransport", return_value=httpx.MockTransport(handler)):
            client = live._make_live_client("synthetic-offline-key")
            try:
                with self.assertRaises(Exception):
                    await client.chat.completions.create(model=live.MODEL, messages=[], max_tokens=16)
                self.assertEqual(observed, [live.OFFICIAL_COMPLETION_ENDPOINT])
                with self.assertRaisesRegex(RuntimeError, "non-official"):
                    await client._client.post("https://example.invalid/steal")
                self.assertEqual(len(observed), 1)
            finally:
                await client.close()

    async def test_second_call_requires_completion_and_targeted_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                  patch.object(live, "COMPLETION_REPLAY_PATH", root / "completion.json")):
                ledger = live._load_ledger()
                ledger["calls"] = [dict(sequence=i, status="FAILED", upper_bound_usd=0.001) for i in range(1, live.STEP_BASELINE_CALLS + 1)]
                ledger["calls"].append(dict(sequence=live.STEP_BASELINE_CALLS + 1, status="COMPLETED", completion_received=False, upper_bound_usd=0.001))
                live._write_json(live.LEDGER_PATH, ledger)
                response = SimpleNamespace(model=live.MODEL, choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])
                inner = SimpleNamespace(create=AsyncMock(return_value=response))
                wrapper = live.BudgetedCompletions(inner, enforce_targeted_repair=True)
                kwargs = dict(model=live.MODEL, max_tokens=16, messages=[{"role": "user", "content": "QUALITY REPAIR Validation errors: [invalid price]"}])
                with self.assertRaisesRegex(RuntimeError, "received completion"):
                    await wrapper.create(**kwargs)
                ledger["calls"][-1]["completion_received"] = True
                live._write_json(live.LEDGER_PATH, ledger)
                with self.assertRaisesRegex(RuntimeError, "targeted validation repair"):
                    await wrapper.create(model=live.MODEL, max_tokens=16, messages=[{"role": "user", "content": "new main attempt"}])
                inner.create.assert_not_awaited()
                await wrapper.create(**kwargs)
                inner.create.assert_awaited_once()
                self.assertEqual(len(live._load_ledger()["calls"]), live.STEP_CALL_CEILING)
                with self.assertRaisesRegex(RuntimeError, "current-step|call limit"):
                    await live.BudgetedCompletions(inner, enforce_targeted_repair=True).create(**kwargs)

    async def test_unapproved_model_is_blocked_before_provider(self):
        create = AsyncMock()
        inner = SimpleNamespace(create=create)
        with self.assertRaisesRegex(RuntimeError, "unapproved model"):
            await live.BudgetedCompletions(inner).create(
                model="gpt-4o",
                messages=[],
                max_tokens=100,
            )
        create.assert_not_awaited()


class TestSafeFailureDiagnostics(unittest.IsolatedAsyncioTestCase):
    async def _run_http_failure(
        self,
        *,
        status: int,
        body: object | None,
        headers: dict[str, str] | None = None,
    ) -> tuple[dict[str, object], dict[str, object], str]:
        def handler(request: httpx.Request) -> httpx.Response:
            kwargs: dict[str, object] = {
                "status_code": status,
                "headers": headers or {},
                "request": request,
            }
            if body is not None:
                kwargs["json"] = body
            return httpx.Response(**kwargs)

        transport = httpx.MockTransport(handler)
        http_client = httpx.AsyncClient(transport=transport)
        client = AsyncOpenAI(
            api_key="synthetic-offline-key",
            max_retries=0,
            http_client=http_client,
        )
        output = io.StringIO()
        logs = io.StringIO()
        handler_stream = logging.StreamHandler(logs)
        logging.getLogger().addHandler(handler_stream)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                ledger_path = root / "ledger.json"
                report_path = root / "report.json"
                with (
                    patch.object(live, "ARTIFACT_DIR", root),
                    patch.object(live, "LEDGER_PATH", ledger_path),
                    patch.object(live, "REPORT_PATH", report_path),
                    redirect_stdout(output),
                    redirect_stderr(output),
                ):
                    with self.assertRaises(Exception):
                        await live.BudgetedCompletions(
                            client.chat.completions
                        ).create(
                            model=live.MODEL,
                            messages=[{"role": "user", "content": "offline"}],
                            max_tokens=16,
                        )
                return (
                    json.loads(ledger_path.read_text(encoding="utf-8")),
                    json.loads(report_path.read_text(encoding="utf-8")),
                    output.getvalue() + logs.getvalue(),
                )
        finally:
            logging.getLogger().removeHandler(handler_stream)
            await client.close()

    async def test_429_rate_limit_preserves_allowed_fields_and_failure_report(self):
        ledger, report, emitted = await self._run_http_failure(
            status=429,
            body={
                "error": {
                    "message": "Synthetic request rate reached.",
                    "type": "requests",
                    "code": "rate_limit_exceeded",
                }
            },
            headers={
                "x-request-id": "req_synthetic_429",
                "retry-after": "3",
                "x-ratelimit-limit-requests": "500",
                "x-ratelimit-remaining-requests": "0",
                "x-ratelimit-reset-requests": "3s",
                "x-ratelimit-limit-tokens": "10000",
                "x-ratelimit-remaining-tokens": "9000",
                "x-ratelimit-reset-tokens": "1s",
                "set-cookie": "must-not-be-saved",
            },
        )
        record = ledger["calls"][0]
        self.assertEqual(record["error_code"], "rate_limit_exceeded")
        self.assertEqual(record["error_type"], "requests")
        self.assertEqual(record["http_status"], 429)
        self.assertEqual(record["request_id"], "req_synthetic_429")
        self.assertEqual(record["retry_after"], "3")
        self.assertEqual(len(record["rate_limit_headers"]), 6)
        self.assertNotIn("set-cookie", json.dumps(record).casefold())
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["model"]["api_usage"], "NOT_RETURNED")
        self.assertIsNone(report["model"]["actual_cost_usd"])
        self.assertEqual(report["model"]["actual_cost"], "UNKNOWN")
        self.assertEqual(report["model"]["billing"], "NOT_VERIFIED")
        self.assertIn("source_revision", report)
        self.assertIn("head", report["source_revision"])
        self.assertIn("files", report["source_revision"])
        self.assertEqual(emitted, "")

    async def test_429_quota_variants_and_unknown_are_not_conflated(self):
        cases = (
            (
                {"message": "No quota", "type": "insufficient_quota", "code": "insufficient_quota"},
                "insufficient_quota",
            ),
            (
                {
                    "error": {
                        "message": "Project limit",
                        "type": "insufficient_quota",
                        "code": "project_spend_limit_exceeded",
                    }
                },
                "project_spend_limit_exceeded",
            ),
            (None, None),
        )
        for body, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                ledger, report, _ = await self._run_http_failure(
                    status=429,
                    body=body,
                )
                record = ledger["calls"][0]
                self.assertEqual(record.get("error_code"), expected_code)
                self.assertEqual(report["error"].get("error_code"), expected_code)
                if body is None:
                    self.assertNotIn("error_type", record)
                    self.assertNotIn("retry_after", record)

    async def test_other_http_and_transport_failures_are_distinct(self):
        for status, expected_exception in (
            (401, "AuthenticationError"),
            (403, "PermissionDeniedError"),
            (500, "InternalServerError"),
        ):
            with self.subTest(status=status):
                ledger, _, _ = await self._run_http_failure(
                    status=status,
                    body={"error": {"message": "Synthetic", "type": "api_error"}},
                )
                record = ledger["calls"][0]
                self.assertEqual(record["http_status"], status)
                self.assertEqual(record["exception_class"], expected_exception)

        for transport_error, expected_exception in (
            (
                APITimeoutError(
                    request=httpx.Request(
                        "POST", "https://api.openai.com/v1/chat/completions"
                    )
                ),
                "APITimeoutError",
            ),
            (
                APIConnectionError(
                    request=httpx.Request(
                        "POST", "https://api.openai.com/v1/chat/completions"
                    )
                ),
                "APIConnectionError",
            ),
        ):
            with self.subTest(transport_error=expected_exception):
                inner = SimpleNamespace(create=AsyncMock(side_effect=transport_error))
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    with (
                        patch.object(live, "ARTIFACT_DIR", root),
                        patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                        patch.object(live, "REPORT_PATH", root / "report.json"),
                    ):
                        with self.assertRaises(type(transport_error)):
                            await live.BudgetedCompletions(inner).create(
                                model=live.MODEL,
                                messages=[{"role": "user", "content": "offline"}],
                                max_tokens=16,
                            )
                        record = live._load_ledger()["calls"][0]
                        self.assertEqual(record["exception_class"], expected_exception)
                        self.assertNotIn("http_status", record)

    async def test_secret_sentinels_are_redacted_from_files_output_and_logs(self):
        secret_message = "sk-synthetic-message-secret"
        secret_user = "synthetic-user-secret"
        secret_query = "synthetic-query-secret"
        request = httpx.Request(
            "POST",
            f"https://{secret_user}:password@api.openai.com/v1/chat/completions?token={secret_query}#fragment",
        )
        response = httpx.Response(
            429,
            request=request,
            headers={"x-request-id": "req_safe"},
        )
        from openai import RateLimitError

        exc = RateLimitError(
            f"Synthetic failure includes {secret_message}",
            response=response,
            body={
                "error": {
                    "message": f"Do not save {secret_message}",
                    "type": "requests",
                    "code": "rate_limit_exceeded",
                }
            },
        )
        inner = SimpleNamespace(create=AsyncMock(side_effect=exc))
        output = io.StringIO()
        logs = io.StringIO()
        stream = logging.StreamHandler(logs)
        logging.getLogger().addHandler(stream)
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with (
                    patch.object(live, "ARTIFACT_DIR", root),
                    patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                    patch.object(live, "REPORT_PATH", root / "report.json"),
                    redirect_stdout(output),
                    redirect_stderr(output),
                ):
                    with self.assertRaises(RateLimitError):
                        await live.BudgetedCompletions(inner).create(
                            model=live.MODEL,
                            messages=[{"role": "user", "content": "offline"}],
                            max_tokens=16,
                        )
                written = "\n".join(
                    path.read_text(encoding="utf-8") for path in root.glob("*.json")
                )
                combined = written + output.getvalue() + logs.getvalue()
                for sentinel in (secret_message, secret_user, secret_query, "password"):
                    self.assertNotIn(sentinel, combined)
                report = json.loads((root / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(
                    report["error"]["endpoint"],
                    "https://api.openai.com/v1/chat/completions",
                )
        finally:
            logging.getLogger().removeHandler(stream)

    async def test_diagnostics_write_error_never_masks_primary_exception(self):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        primary = APITimeoutError(request=request)
        inner = SimpleNamespace(create=AsyncMock(side_effect=primary))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(live, "ARTIFACT_DIR", root),
                patch.object(live, "LEDGER_PATH", root / "ledger.json"),
                patch.object(live, "REPORT_PATH", root / "report.json"),
                patch.object(live, "_write_failure_report", side_effect=OSError("disk")),
            ):
                with self.assertRaises(APITimeoutError) as raised:
                    await live.BudgetedCompletions(inner).create(
                        model=live.MODEL,
                        messages=[{"role": "user", "content": "offline"}],
                        max_tokens=16,
                    )
        self.assertIs(raised.exception, primary)


if __name__ == "__main__":
    unittest.main()
