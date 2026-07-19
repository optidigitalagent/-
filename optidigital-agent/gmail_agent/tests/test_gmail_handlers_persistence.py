"""RED behavioural contracts for durable Gmail command wiring.

The handlers are loaded from their AST so these tests do not require aiogram.
Production dependencies are replaced at the repository/processor boundary.
"""

from __future__ import annotations

import ast
import logging
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bot.html_utils import escape_html, safe_http_url
from gmail_agent.storage import ScanRun, StoredGmailJob


HANDLERS_PATH = PROJECT_ROOT / "bot" / "handlers.py"


def _load_handler(name: str, extra_globals: dict | None = None):
    """Load a handler plus any top-level helper functions it calls."""
    tree = ast.parse(HANDLERS_PATH.read_text(encoding="utf-8"), str(HANDLERS_PATH))
    definitions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if name not in definitions:
        raise AssertionError(f"Missing handler function: {name}")

    selected = {name}
    pending = [name]
    while pending:
        node = definitions[pending.pop()]
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in definitions and child.id not in selected:
                selected.add(child.id)
                pending.append(child.id)

    nodes = [node for node in tree.body if getattr(node, "name", None) in selected]
    for node in nodes:
        node.decorator_list = []
    namespace = {
        "Message": object,
        "datetime": datetime,
        "logger": logging.getLogger(__name__),
        "escape_html": escape_html,
        "safe_http_url": safe_http_url,
        "__file__": str(HANDLERS_PATH),
    }
    namespace.update(extra_globals or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(HANDLERS_PATH), "exec"), namespace)
    return namespace[name]


def _settings(enabled: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        GMAIL_ENABLED=enabled,
        GMAIL_USE_MOCK=False,
        GMAIL_CREDENTIALS_FILE="unused-credentials.json",
        GMAIL_TOKEN_FILE="unused-token.json",
        GMAIL_MIN_SCORE=6.0,
        TELEGRAM_CHAT_ID=123,
        admin_chat_id=456,
    )


def _message(text: str) -> MagicMock:
    message = MagicMock(text=text)
    message.answer = AsyncMock()
    message.bot = MagicMock()
    message.bot.send_message = AsyncMock()
    return message


def _job(stable_key: str = "stable-key-1", status: str = "queued") -> StoredGmailJob:
    return StoredGmailJob(
        stable_key=stable_key,
        source_email_id="parent-redacted",
        platform="Freelancehunt",
        title="Python automation",
        score=8.5,
        reason="Strong Python match",
        budget="500 USD",
        url="https://freelancehunt.com/project/123.html",
        urgency="medium",
        why_relevant="Automation and APIs",
        status=status,
    )


class TestAdminDigestCommands(unittest.IsolatedAsyncioTestCase):
    def test_digest_commands_are_registered_only_on_admin_router(self):
        tree = ast.parse(HANDLERS_PATH.read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in ("cmd_gmail_digest_preview", "cmd_gmail_digest_backfill"):
            self.assertIn(name, functions)
            routers = []
            for decorator in functions[name].decorator_list:
                call = decorator if isinstance(decorator, ast.Call) else None
                func = call.func if call else None
                if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                    routers.append(func.value.id)
            self.assertIn("admin_router", routers, name)
            self.assertNotIn("router", routers, name)

    async def test_preview_calls_dry_run_and_formats_count_title_score_reason(self):
        preview = SimpleNamespace(
            items=[
                SimpleNamespace(title="Python automation", score=8.5, reason="Strong Python match"),
                SimpleNamespace(title="QA audit", score=5.0, reason="Below threshold"),
            ],
            stats=SimpleNamespace(candidates_found=2, errors=0),
        )
        processor = MagicMock()
        processor.run_digest_preview = AsyncMock(return_value=preview)
        processor.run_digest_backfill = AsyncMock()
        processor.run = AsyncMock()
        processor_type = MagicMock(return_value=processor)
        repository_type = MagicMock(return_value=MagicMock())
        message = _message("/gmail_digest_preview 7")
        handler = _load_handler(
            "cmd_gmail_digest_preview",
            {
                "settings": _settings(),
                "GmailJobProcessor": processor_type,
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with (
            patch("gmail_agent.gmail_provider.build_provider", return_value=MagicMock()),
            patch("gmail_agent.processor.GmailJobProcessor", processor_type),
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
        ):
            await handler(message)

        processor.run_digest_preview.assert_awaited_once_with(7)
        processor.run.assert_not_awaited()
        processor.run_digest_backfill.assert_not_awaited()
        message.bot.send_message.assert_not_awaited()  # no Telegram job cards
        output = "\n".join(call.args[0] for call in message.answer.await_args_list)
        for expected in ("2", "Python automation", "8.5", "Strong Python match"):
            self.assertIn(expected, output)

    async def test_backfill_calls_execution_and_reports_card_cap_stats(self):
        stats = SimpleNamespace(
            emails_fetched=2,
            candidates_found=14,
            relevant=11,
            duplicates_skipped=2,
            not_relevant=0,
            below_threshold=1,
            sent=10,
            errors=1,
            error_details=[],
        )
        processor = MagicMock()
        processor.run_digest_backfill = AsyncMock(return_value=stats)
        processor_type = MagicMock(return_value=processor)
        repository_type = MagicMock(return_value=MagicMock())
        message = _message("/gmail_digest_backfill 7")
        handler = _load_handler(
            "cmd_gmail_digest_backfill",
            {
                "settings": _settings(),
                "GmailJobProcessor": processor_type,
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with (
            patch("gmail_agent.gmail_provider.build_provider", return_value=MagicMock()),
            patch("gmail_agent.processor.GmailJobProcessor", processor_type),
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
        ):
            await handler(message)

        processor.run_digest_backfill.assert_awaited_once_with(7)
        constructor_kwargs = processor_type.call_args.kwargs
        self.assertEqual(constructor_kwargs.get("max_cards_per_scan"), 10)
        output = "\n".join(call.args[0] for call in message.answer.await_args_list)
        for expected in ("14", "11", "10", "2"):
            self.assertIn(expected, output)

    async def test_digest_days_are_validated_from_one_through_thirty(self):
        for command in ("preview", "backfill"):
            handler_name = f"cmd_gmail_digest_{command}"
            for raw_days in ("0", "31", "nope", ""):
                with self.subTest(command=command, days=raw_days):
                    processor_type = MagicMock()
                    message = _message(f"/gmail_digest_{command} {raw_days}".rstrip())
                    handler = _load_handler(
                        handler_name,
                        {
                            "settings": _settings(),
                            "GmailJobProcessor": processor_type,
                            "PostgresGmailRepository": MagicMock(),
                            "AsyncSessionLocal": MagicMock(),
                        },
                    )
                    await handler(message)
                    processor_type.assert_not_called()
                    output = "\n".join(call.args[0] for call in message.answer.await_args_list)
                    self.assertIn("1", output)
                    self.assertIn("30", output)


class TestPersistentHistoryAndJobs(unittest.IsolatedAsyncioTestCase):
    async def test_history_reads_latest_twenty_repository_scan_runs(self):
        repository = MagicMock()
        repository.list_scan_runs = AsyncMock(return_value=[
            ScanRun(
                id=9,
                trigger="scheduler",
                started_at=datetime(2026, 7, 19, 8, 30, tzinfo=timezone.utc),
                finished_at=datetime(2026, 7, 19, 8, 31, tzinfo=timezone.utc),
                emails_inspected=8,
                candidates_found=6,
                relevant=3,
                duplicates=2,
                sent=3,
                errors=1,
            )
        ])
        repository_type = MagicMock(return_value=repository)
        message = _message("/gmail_history")
        handler = _load_handler(
            "cmd_gmail_history",
            {
                "settings": _settings(),
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with patch("gmail_agent.storage.PostgresGmailRepository", repository_type):
            await handler(message)

        repository.list_scan_runs.assert_awaited_once_with(limit=20)
        output = "\n".join(call.args[0] for call in message.answer.await_args_list).lower()
        for expected in ("scheduler", "19.07", "8", "6", "3", "2", "1"):
            self.assertIn(expected, output)

    async def test_history_db_error_reports_unavailable_not_misleading_empty(self):
        repository = MagicMock()
        repository.list_scan_runs = AsyncMock(side_effect=RuntimeError("database offline"))
        repository_type = MagicMock(return_value=repository)
        message = _message("/gmail_history")
        handler = _load_handler(
            "cmd_gmail_history",
            {
                "settings": _settings(),
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with patch("gmail_agent.storage.PostgresGmailRepository", repository_type):
            await handler(message)

        output = "\n".join(call.args[0] for call in message.answer.await_args_list).lower()
        self.assertTrue("unavailable" in output or "недоступ" in output, output)
        self.assertNotIn("історія порожня", output)
        self.assertNotIn("history is empty", output)

    async def test_reply_loads_persistent_job_after_memory_cache_is_empty(self):
        repository = MagicMock()
        repository.get_job = AsyncMock(return_value=_job())
        repository_type = MagicMock(return_value=repository)
        message = _message("/reply_job stable-key-1")
        handler = _load_handler(
            "cmd_reply_job",
            {
                "_gmail_job_store": {},
                "settings": _settings(),
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with (
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
            patch("gmail_agent.reply_generator.generate_reply", AsyncMock(return_value="Draft reply")),
        ):
            await handler(message)

        repository.get_job.assert_awaited_once_with("stable-key-1")
        output = "\n".join(call.args[0] for call in message.answer.await_args_list)
        self.assertIn("Python automation", output)
        self.assertIn("Draft reply", output)

    async def test_skip_updates_persistent_status_without_deleting_job(self):
        repository = MagicMock()
        repository.update_job_status = AsyncMock(return_value=_job(status="skipped"))
        repository_type = MagicMock(return_value=repository)
        cache = {"stable-key-1": {"title": "Python automation"}}
        message = _message("/skip_job stable-key-1")
        handler = _load_handler(
            "cmd_skip_job",
            {
                "_gmail_job_store": cache,
                "settings": _settings(),
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
            },
        )

        with (
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
            patch("gmail_agent.job_store.delete_job") as legacy_delete,
        ):
            await handler(message)

        repository.update_job_status.assert_awaited_once_with("stable-key-1", "skipped")
        legacy_delete.assert_not_called()
        self.assertIn("stable-key-1", cache)


class TestRepositoryWiring(unittest.IsolatedAsyncioTestCase):
    async def test_manual_scan_passes_postgres_repository_and_manual_trigger(self):
        stats = SimpleNamespace(
            emails_fetched=0,
            candidates_found=0,
            duplicates_skipped=0,
            relevant=0,
            not_relevant=0,
            below_threshold=0,
            sent=0,
            errors=0,
            error_details=[],
            rejected_samples=[],
            below_score_samples=[],
            sent_analyses=[],
        )
        repository = MagicMock()
        repository_type = MagicMock(return_value=repository)
        processor = MagicMock()
        processor.run = AsyncMock(return_value=stats)
        processor_type = MagicMock(return_value=processor)
        message = _message("/gmail_scan")
        handler = _load_handler(
            "cmd_gmail_scan",
            {
                "settings": _settings(),
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
                "GmailJobProcessor": processor_type,
            },
        )

        with (
            patch("gmail_agent.gmail_provider.build_provider", return_value=MagicMock()),
            patch("gmail_agent.processor.GmailJobProcessor", processor_type),
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
        ):
            await handler(message)

        self.assertIs(processor_type.call_args.kwargs["repository"], repository)
        processor.run.assert_awaited_once_with(trigger="manual")

    async def test_scheduler_passes_postgres_repository_and_scheduler_trigger(self):
        from gmail_agent.scheduler import check_gmail_jobs

        settings = _settings()
        repository = MagicMock()
        repository_type = MagicMock(return_value=repository)
        processor = MagicMock()
        processor.run = AsyncMock(return_value=SimpleNamespace(
            emails_fetched=0,
            duplicates_skipped=0,
            not_relevant=0,
            sent=0,
            errors=0,
            error_details=[],
        ))
        processor_type = MagicMock(return_value=processor)
        with (
            patch.dict(sys.modules, {"config": SimpleNamespace(settings=settings)}),
            patch("gmail_agent.gmail_provider.build_provider", return_value=MagicMock()),
            patch("gmail_agent.processor.GmailJobProcessor", processor_type),
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
        ):
            await check_gmail_jobs(MagicMock())

        self.assertIs(processor_type.call_args.kwargs["repository"], repository)
        processor.run.assert_awaited_once_with(trigger="scheduler")

    async def test_disabled_gmail_has_no_provider_repository_or_scheduler_side_effects(self):
        from gmail_agent.scheduler import check_gmail_jobs, register_gmail_job

        disabled = _settings(enabled=False)
        scheduler = MagicMock()
        bot = MagicMock()
        provider = MagicMock()
        repository_type = MagicMock()
        handler = _load_handler(
            "cmd_gmail_scan",
            {
                "settings": disabled,
                "PostgresGmailRepository": repository_type,
                "AsyncSessionLocal": MagicMock(),
                "GmailJobProcessor": MagicMock(),
            },
        )
        message = _message("/gmail_scan")

        with (
            patch.dict(sys.modules, {"config": SimpleNamespace(settings=disabled)}),
            patch("gmail_agent.gmail_provider.build_provider", provider),
            patch("gmail_agent.storage.PostgresGmailRepository", repository_type),
        ):
            await handler(message)
            await check_gmail_jobs(bot)
            register_gmail_job(scheduler, bot)

        provider.assert_not_called()
        repository_type.assert_not_called()
        scheduler.add_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
