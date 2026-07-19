"""Contract tests for Gmail persistence repositories and ORM schema.

The in-memory repository tests intentionally execute without SQLAlchemy.  When
that optional dependency is unavailable locally, the relevant definitions are
loaded from ``storage.py``'s AST while the PostgreSQL-only definitions remain
unevaluated.
"""

from __future__ import annotations

import ast
import asyncio
import sys
import types
import unittest
from collections.abc import Sequence
from dataclasses import dataclass, field as dataclass_field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_PATH = PROJECT_ROOT / "gmail_agent" / "storage.py"
MODELS_PATH = PROJECT_ROOT / "db" / "models.py"

sys.path.insert(0, str(PROJECT_ROOT))


def _load_storage_module() -> types.ModuleType:
    """Import storage normally, or AST-load its dependency-free definitions."""

    try:
        from gmail_agent import storage

        return storage
    except ModuleNotFoundError as exc:
        if exc.name != "sqlalchemy":
            raise

    tree = ast.parse(STORAGE_PATH.read_text(encoding="utf-8"), STORAGE_PATH.name)
    wanted_definitions = {
        "utc_now",
        "ProcessedItem",
        "StoredGmailJob",
        "ScanRun",
        "InMemoryGmailRepository",
    }
    wanted_assignments = {
        "TERMINAL_JOB_STATUSES",
        "DEFAULT_CLAIMABLE_STATUSES",
        "DEFAULT_SENDING_LEASE",
    }
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            selected.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            if node.name in wanted_definitions:
                selected.append(node)
        elif isinstance(node, ast.Assign):
            assigned_names = {
                target.id for target in node.targets if isinstance(target, ast.Name)
            }
            if assigned_names & wanted_assignments:
                selected.append(node)

    module_name = "_gmail_storage_without_sqlalchemy"
    module = types.ModuleType(module_name)
    module.__file__ = str(STORAGE_PATH)
    module.__dict__.update(
        {
            "asyncio": asyncio,
            "Sequence": Sequence,
            "dataclass": dataclass,
            "dataclass_field": dataclass_field,
            "replace": replace,
            "datetime": datetime,
            "timedelta": timedelta,
            "timezone": timezone,
        }
    )
    sys.modules[module_name] = module
    code = compile(ast.Module(body=selected, type_ignores=[]), STORAGE_PATH, "exec")
    exec(code, module.__dict__)
    return module


storage = _load_storage_module()
InMemoryGmailRepository = storage.InMemoryGmailRepository
ProcessedItem = storage.ProcessedItem
ScanRun = storage.ScanRun
StoredGmailJob = storage.StoredGmailJob


def _processed_item(
    stable_key: str,
    *,
    source_email_id: str = "digest-email-1",
) -> ProcessedItem:
    return ProcessedItem(
        stable_key=stable_key,
        source_email_id=source_email_id,
        platform="Freelancehunt",
        item_type="digest_job",
        title=f"Job {stable_key}",
        url=f"https://example.test/projects/{stable_key}",
        decision="sent",
        score=8.0,
    )


def _job(stable_key: str, *, status: str = "queued") -> StoredGmailJob:
    return StoredGmailJob(
        stable_key=stable_key,
        source_email_id="digest-email-1",
        platform="Freelancehunt",
        title=f"Job {stable_key}",
        score=8.0,
        reason="Strong match",
        budget="1000 USD",
        url=f"https://example.test/projects/{stable_key}",
        urgency="medium",
        why_relevant="Matches the supported stack",
        status=status,
    )


class TestInMemoryGmailRepository(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.repository = InMemoryGmailRepository()

    async def test_processed_dedup_uses_child_stable_key_not_parent_email_id(self):
        first = _processed_item("job-key-1")
        second = _processed_item("job-key-2")

        await self.repository.upsert_processed(first)
        await self.repository.upsert_processed(second)

        self.assertTrue(await self.repository.is_processed("job-key-1"))
        self.assertTrue(await self.repository.is_processed("job-key-2"))
        self.assertFalse(await self.repository.is_processed("digest-email-1"))
        self.assertEqual(
            await self.repository.get_processed("job-key-1"),
            first,
        )

    async def test_save_get_and_update_job(self):
        original = _job("job-key")

        saved = await self.repository.save_job(original)
        loaded = await self.repository.get_job("job-key")
        updated = await self.repository.update_job_status("job-key", "send_failed")

        self.assertEqual(saved, original)
        self.assertEqual(loaded, original)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, "send_failed")
        self.assertEqual(
            (await self.repository.get_job("job-key")).status,
            "send_failed",
        )
        self.assertIsNone(await self.repository.update_job_status("missing", "sent"))

    async def test_resaving_job_does_not_reset_terminal_status_to_queued(self):
        for terminal_status in ("sent", "skipped"):
            with self.subTest(status=terminal_status):
                repository = InMemoryGmailRepository()
                await repository.save_job(_job(f"job-{terminal_status}"))
                await repository.update_job_status(
                    f"job-{terminal_status}", terminal_status
                )

                resaved = await repository.save_job(
                    _job(f"job-{terminal_status}", status="queued")
                )

                self.assertEqual(resaved.status, terminal_status)

    async def test_telegram_send_failure_remains_retryable(self):
        await self.repository.save_job(_job("retryable-job"))
        self.assertTrue(await self.repository.claim_job("retryable-job"))

        failed = await self.repository.update_job_status(
            "retryable-job", "send_failed"
        )
        retried = await self.repository.claim_job("retryable-job")

        self.assertEqual(failed.status, "send_failed")
        self.assertTrue(retried)
        self.assertEqual(
            (await self.repository.get_job("retryable-job")).status,
            "sending",
        )

    async def test_concurrent_claim_is_atomic(self):
        await self.repository.save_job(_job("contended-job"))

        results = await asyncio.gather(
            *(self.repository.claim_job("contended-job") for _ in range(32))
        )

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 31)

    async def test_fresh_sending_claim_is_exclusive_but_stale_claim_is_recoverable(self):
        self.assertIn("status_updated_at", StoredGmailJob.__dataclass_fields__)
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        fresh = replace(
            _job("fresh-sending", status="sending"),
            status_updated_at=now - timedelta(minutes=14),
        )
        stale = replace(
            _job("stale-sending", status="sending"),
            status_updated_at=now - timedelta(minutes=16),
        )
        await self.repository.save_job(fresh)
        await self.repository.save_job(stale)

        fresh_results = await asyncio.gather(
            *(self.repository.claim_job("fresh-sending", now=now) for _ in range(8))
        )
        stale_results = await asyncio.gather(
            *(self.repository.claim_job("stale-sending", now=now) for _ in range(8))
        )

        self.assertEqual(fresh_results, [False] * 8)
        self.assertEqual(stale_results.count(True), 1)
        self.assertEqual(stale_results.count(False), 7)
        reclaimed = await self.repository.get_job("stale-sending")
        self.assertEqual(reclaimed.status, "sending")
        self.assertEqual(reclaimed.status_updated_at, now)

    async def test_retryable_jobs_include_fifo_queue_failures_and_stale_sending(self):
        self.assertIn("status_updated_at", StoredGmailJob.__dataclass_fields__)
        now = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)
        jobs = [
            replace(
                _job("queued-new", status="queued"),
                status_updated_at=now - timedelta(minutes=5),
            ),
            replace(
                _job("failed-old", status="send_failed"),
                status_updated_at=now - timedelta(minutes=30),
            ),
            replace(
                _job("sending-stale", status="sending"),
                status_updated_at=now - timedelta(minutes=16),
            ),
            replace(
                _job("sending-fresh", status="sending"),
                status_updated_at=now - timedelta(minutes=14),
            ),
            replace(
                _job("already-sent", status="sent"),
                status_updated_at=now - timedelta(hours=1),
            ),
        ]
        for job in jobs:
            await self.repository.save_job(job)

        retryable = await self.repository.list_retryable_jobs(limit=10, now=now)

        self.assertEqual(
            [job.stable_key for job in retryable],
            ["failed-old", "sending-stale", "queued-new"],
        )
        self.assertEqual(
            [job.status for job in retryable],
            ["send_failed", "sending", "queued"],
        )
        self.assertEqual(
            [job.stable_key for job in await self.repository.list_retryable_jobs(
                limit=2, now=now
            )],
            ["failed-old", "sending-stale"],
        )

    async def test_scan_runs_are_newest_first_and_capped_by_limit(self):
        base = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)
        oldest = await self.repository.append_scan_run(
            ScanRun(trigger="scheduler", started_at=base)
        )
        newer = await self.repository.append_scan_run(
            ScanRun(trigger="manual", started_at=base + timedelta(minutes=1))
        )
        newest_same_time = await self.repository.append_scan_run(
            ScanRun(trigger="backfill", started_at=base + timedelta(minutes=1))
        )

        recent = await self.repository.list_scan_runs(limit=2)

        self.assertEqual(
            [run.id for run in recent],
            [newest_same_time.id, newer.id],
        )
        self.assertNotIn(oldest.id, [run.id for run in recent])
        self.assertEqual(await self.repository.list_scan_runs(limit=0), [])

    async def test_scan_run_preserves_explicit_multi_job_telemetry(self):
        run = ScanRun(
            trigger="manual",
            started_at=datetime(2026, 7, 19, 18, 40, tzinfo=timezone.utc),
            finished_at=datetime(2026, 7, 19, 18, 41, tzinfo=timezone.utc),
            emails_inspected=8,
            candidates_found=3,
            ai_analyzed=1,
            relevant=1,
            qualified=1,
            duplicates=3,
            sent=1,
            sent_from_queue=1,
            errors=0,
        )

        saved = await self.repository.append_scan_run(run)
        restarted = InMemoryGmailRepository(state=self.repository._state)
        loaded = (await restarted.list_scan_runs(limit=1))[0]

        self.assertEqual(loaded, saved)
        self.assertEqual(loaded.ai_analyzed, 1)
        self.assertEqual(loaded.qualified, 1)
        self.assertEqual(loaded.sent_from_queue, 1)

    async def test_legacy_scan_run_defaults_new_telemetry_to_zero(self):
        saved = await self.repository.append_scan_run(
            ScanRun(
                trigger="backfill",
                started_at=datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
            )
        )

        self.assertEqual(saved.ai_analyzed, 0)
        self.assertEqual(saved.qualified, 0)
        self.assertEqual(saved.sent_from_queue, 0)

    async def test_job_and_history_survive_repository_recreation_with_shared_state(self):
        shared_state: dict[str, object] = {}
        first_repository = InMemoryGmailRepository(state=shared_state)
        saved_job = await first_repository.save_job(_job("restart-job"))
        saved_run = await first_repository.append_scan_run(
            ScanRun(
                trigger="scheduler",
                started_at=datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
                sent=1,
            )
        )

        restarted_repository = InMemoryGmailRepository(state=shared_state)

        self.assertEqual(
            await restarted_repository.get_job("restart-job"),
            saved_job,
        )
        self.assertEqual(
            await restarted_repository.list_scan_runs(),
            [saved_run],
        )


class TestGmailOrmSchema(unittest.TestCase):
    REQUIRED_TABLE_COLUMNS = {
        "gmail_processed_items": {
            "stable_key",
            "source_email_id",
            "platform",
            "item_type",
            "title",
            "url",
            "decision",
            "score",
            "processed_at",
        },
        "gmail_scan_runs": {
            "id",
            "trigger",
            "started_at",
            "finished_at",
            "emails_inspected",
            "candidates_found",
            "ai_analyzed",
            "relevant",
            "qualified",
            "duplicates",
            "not_relevant",
            "below_threshold",
            "sent",
            "sent_from_queue",
            "errors",
        },
        "gmail_jobs": {
            "stable_key",
            "source_email_id",
            "platform",
            "title",
            "score",
            "reason",
            "budget",
            "url",
            "urgency",
            "why_relevant",
            "created_at",
            "status",
            "status_updated_at",
        },
    }

    def test_required_orm_table_names_and_columns_exist_without_live_database(self):
        tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"), MODELS_PATH.name)
        actual: dict[str, set[str]] = {}

        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            table_name = None
            columns: set[str] = set()
            for statement in node.body:
                if (
                    isinstance(statement, ast.Assign)
                    and any(
                        isinstance(target, ast.Name) and target.id == "__tablename__"
                        for target in statement.targets
                    )
                    and isinstance(statement.value, ast.Constant)
                    and isinstance(statement.value.value, str)
                ):
                    table_name = statement.value.value
                elif isinstance(statement, ast.AnnAssign) and isinstance(
                    statement.target, ast.Name
                ):
                    columns.add(statement.target.id)
            if table_name is not None:
                actual[table_name] = columns

        for table_name, required_columns in self.REQUIRED_TABLE_COLUMNS.items():
            with self.subTest(table=table_name):
                self.assertIn(table_name, actual)
                self.assertTrue(
                    required_columns <= actual[table_name],
                    f"{table_name} is missing {sorted(required_columns - actual[table_name])}",
                )

    def test_status_updated_at_uses_an_additive_non_destructive_migration(self):
        tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"), MODELS_PATH.name)
        sql_literals = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]

        matching = [
            sql
            for sql in sql_literals
            if "gmail_jobs" in sql.casefold() and "status_updated_at" in sql.casefold()
        ]

        self.assertTrue(matching, "gmail_jobs.status_updated_at migration is missing")
        self.assertTrue(
            any(
                all(
                    fragment in sql.casefold()
                    for fragment in (
                        "alter table gmail_jobs",
                        "add column if not exists status_updated_at",
                    )
                )
                for sql in matching
            ),
            "status_updated_at must be added with ADD COLUMN IF NOT EXISTS",
        )
        self.assertFalse(
            any(
                destructive in sql.casefold()
                for sql in matching
                for destructive in ("drop table", "drop column", "truncate")
            )
        )

    def test_scan_telemetry_uses_additive_non_destructive_migrations(self):
        source = MODELS_PATH.read_text(encoding="utf-8").casefold()
        for column in ("ai_analyzed", "qualified", "sent_from_queue"):
            self.assertIn(
                f"alter table gmail_scan_runs add column if not exists {column} "
                "integer not null default 0",
                source,
            )
        self.assertNotIn("drop table gmail_scan_runs", source)
        self.assertNotIn("truncate gmail_scan_runs", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
