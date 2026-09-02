"""Stage 2 acceptance contracts for the Antonov Digital revenue-alert flow."""

from __future__ import annotations

import ast
import asyncio
import logging
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from gmail_agent.email_analyzer import JobAnalysis
from gmail_agent.email_classifier import EmailType, classify_email
from gmail_agent.gmail_provider import EmailMessage, MockGmailProvider, RealGmailProvider
from gmail_agent.oauth_local import run_oauth
from gmail_agent.processor import GmailJobProcessor
from gmail_agent.reply_generator import generate_reply
from gmail_agent.security import redact_security_event, redact_sensitive_content
from gmail_agent.storage import InMemoryGmailRepository, StoredGmailJob
from gmail_agent.telegram_notifier import TELEGRAM_TEXT_LIMIT, format_job_card_parts


NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _analysis(email_id: str = "event-1", **overrides) -> JobAnalysis:
    values = {
        "email_id": email_id,
        "is_relevant": True,
        "title": "Інтеграція CRM і Telegram",
        "platform": "Freelancehunt",
        "score": 8.2,
        "reason": "Чіткий комерційний fit.",
        "budget": "20 000 UAH",
        "url": "https://freelancehunt.com/project/crm-telegram/123456.html",
        "urgency": "high",
        "why_relevant": "API, PostgreSQL і Telegram входять у підтверджений стек.",
        "event_type": EmailType.PROJECT_SINGLE.value,
        "source_email_id": email_id,
        "full_description": "Потрібно синхронізувати CRM, Telegram і звітність.",
        "description_completeness": "FULL",
        "language": "uk",
        "category": "Веб-програмування",
        "deadline": "14 днів",
        "bid_count": 4,
        "client_name": "Synthetic Client",
        "service_lane": "CRM та внутрішні системи",
        "executable": "yes",
        "fit_score": 8.2,
        "win_probability_signal": "medium — clear fit, some competition",
        "scope_clarity": "high — deliverables are explicit",
        "estimated_effort": "30–40 hours",
        "delivery_risk": "Access to the CRM API must be confirmed.",
        "client_payment_risk": "Use one funded milestone.",
        "project_mode": "CASH",
        "project_mode_reason": "Controlled paid integration scope.",
        "recommended_price": "20 000 UAH as one milestone",
        "realistic_timeline": "14 calendar days",
        "selected_evidence": "Gmail Job Agent — Gmail, Telegram, Railway, PostgreSQL",
        "proposal_draft": "Реалізуємо інтеграцію поетапно: API, синхронізація, тестування.",
        "next_action": "Відкрити проєкт і особисто подати підготовлений відгук.",
        "received_at": NOW,
    }
    values.update(overrides)
    return JobAnalysis(**values)


class TestMultilingualEventClassification(unittest.TestCase):
    def test_all_required_event_types_cover_uk_ru_en_pl_subjects(self):
        cases = {
            EmailType.PROJECT_SINGLE: (
                "Новий проєкт: CRM",
                "Новый проект: CRM",
                "New project: CRM",
                "Nowy projekt: CRM",
            ),
            EmailType.PROJECT_DIGEST: (
                "Підбірка проєктів за сьогодні",
                "Подборка проектов за сегодня",
                "Daily project digest",
                "Zestawienie projektów",
            ),
            EmailType.CLIENT_PRIVATE_MESSAGE: (
                "Нове особисте повідомлення від Олена",
                "Новое личное сообщение от Анна",
                "New private message from Alex",
                "Wiadomość prywatna od Jan",
            ),
            EmailType.PROJECT_STATUS_EVENT: (
                "Статус проєкту змінено",
                "Статус проекта изменён",
                "Project status changed",
                "Status projektu zmieniony",
            ),
            EmailType.WORKSPACE_OR_CONTRACT_EVENT: (
                "Робоча область проєкту відкрита",
                "Рабочая область проекта открыта",
                "Workspace milestone created",
                "Umowa projektu gotowa",
            ),
            EmailType.ACCOUNT_OR_SECURITY_EVENT: (
                "Новий вхід у ваш акаунт",
                "Новый вход в аккаунт",
                "Security alert: new sign-in",
                "Alert bezpieczeństwa: nowe logowanie",
            ),
            EmailType.MARKETING: (
                "Спеціальна пропозиція та знижка",
                "Распродажа и скидка",
                "Special offer and discount",
                "Promocja i rabat",
            ),
        }
        for expected, subjects in cases.items():
            for subject in subjects:
                with self.subTest(expected=expected.value, subject=subject):
                    self.assertEqual(
                        classify_email("notify@freelancehunt.com", subject), expected
                    )

    def test_copied_private_subject_from_untrusted_sender_is_unknown(self):
        self.assertEqual(
            classify_email("attacker@example.com", "New private message from Client"),
            EmailType.UNKNOWN,
        )


class TestSecurityRedaction(unittest.TestCase):
    def test_security_event_removes_otp_tokens_and_every_link(self):
        source = (
            "Your one-time code: 123456. reset_token=super-secret-token. "
            "Open https://freelancehunt.com/reset?token=secret123"
        )
        safe, changed = redact_security_event(source)
        self.assertTrue(changed)
        for secret in ("123456", "super-secret-token", "secret123", "https://"):
            self.assertNotIn(secret, safe)
        self.assertIn("[OTP REDACTED]", safe)
        self.assertIn("[TOKEN REDACTED]", safe)
        self.assertIn("[SENSITIVE LINK REDACTED]", safe)

    def test_ordinary_public_project_link_is_preserved(self):
        link = "https://freelancehunt.com/project/example/123456.html"
        safe, changed = redact_sensitive_content(f"Project: {link}")
        self.assertFalse(changed)
        self.assertIn(link, safe)


class TestCompleteTelegramCards(unittest.TestCase):
    def test_long_project_card_is_complete_html_safe_and_within_message_limit(self):
        description = ("Full requirement <tag> & acceptance criterion.\n" * 350).strip()
        analysis = _analysis(full_description=description)
        parts = format_job_card_parts(analysis)
        joined = "\n".join(parts)

        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= TELEGRAM_TEXT_LIMIT for part in parts))
        self.assertNotIn("<tag>", joined)
        self.assertEqual(joined.count("Full requirement"), 350)
        for expected in (
            "Повнота ТЗ",
            "Service lane",
            "Win signal",
            "Scope clarity",
            "Трудомісткість",
            "Рекомендована ціна",
            "Релевантний кейс",
            "Готовий відгук",
            "Наступна дія власниці",
        ):
            self.assertIn(expected, joined)

    def test_private_message_card_is_high_priority_and_needs_context(self):
        analysis = _analysis(
            event_type=EmailType.CLIENT_PRIVATE_MESSAGE.value,
            title="New private message from Alex",
            client_name="Alex",
            full_description="Can you confirm the delivery date?",
            proposal_draft="Yes. I will confirm the scoped delivery date after reviewing the thread.",
            language="en",
            needs_context=True,
        )
        parts = format_job_card_parts(analysis)
        self.assertEqual(len(parts), 1)
        card = "\n".join(parts)
        self.assertIn("HIGH PRIORITY", card)
        self.assertIn("NEEDS_CONTEXT", card)
        self.assertIn("Can you confirm", card)
        self.assertIn("reviewing the thread", card)

    def test_security_card_never_contains_sensitive_link(self):
        body, changed = redact_security_event(
            "Verification code: 887766 https://freelancehunt.com/reset?token=abc12345"
        )
        analysis = _analysis(
            event_type=EmailType.ACCOUNT_OR_SECURITY_EVENT.value,
            full_description=body,
            url="",
            proposal_draft="",
            sensitive_redacted=changed,
        )
        card = "\n".join(format_job_card_parts(analysis))
        self.assertNotIn("887766", card)
        self.assertNotIn("abc12345", card)
        self.assertNotIn("href=", card)
        self.assertIn("Gmail", card)


class TestStage2Processor(unittest.IsolatedAsyncioTestCase):
    async def test_project_status_bypasses_job_score_and_is_persisted(self):
        email = EmailMessage(
            id="status-1",
            sender="notify@freelancehunt.com",
            subject="Project status changed",
            body="Client selected you as the project executor.",
            text_body="Client selected you as the project executor.",
            links=["https://freelancehunt.com/project/synthetic/123456.html?utm=x"],
            received_at=NOW,
        )
        repository = InMemoryGmailRepository()
        processor = GmailJobProcessor(
            provider=MockGmailProvider([email]),
            bot=MagicMock(),
            chat_id=123,
            min_score=9.0,
            repository=repository,
        )
        low_score = _analysis(
            "status-1",
            is_relevant=False,
            score=0.0,
            fit_score=0.0,
            proposal_draft="",
        )
        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=low_score)),
            patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)),
        ):
            stats = await processor.run()

        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.below_threshold, 0)
        stored = await repository.get_job("status-1")
        self.assertEqual(stored.event_type, EmailType.PROJECT_STATUS_EVENT.value)
        self.assertEqual(
            stored.url,
            "https://freelancehunt.com/project/synthetic/123456.html",
        )
        self.assertEqual(stored.status, "sent")

    async def test_private_message_bypasses_score_and_persists_full_context(self):
        email = EmailMessage(
            id="private-1",
            sender="messages@freelancehunt.com",
            subject="New private message from Alex",
            body="Could you confirm scope before Friday?",
            text_body="Could you confirm scope before Friday?",
            links=["https://freelancehunt.com/mailbox/thread/42"],
            received_at=NOW,
        )
        repository = InMemoryGmailRepository()
        processor = GmailJobProcessor(
            provider=MockGmailProvider([email]),
            bot=MagicMock(),
            chat_id=123,
            min_score=9.0,
            repository=repository,
        )
        low_score = _analysis(
            "private-1",
            is_relevant=False,
            score=0.0,
            fit_score=0.0,
            proposal_draft="I can confirm after checking the previous thread.",
        )
        with (
            patch("gmail_agent.processor.analyze_email", AsyncMock(return_value=low_score)),
            patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)),
        ):
            stats = await processor.run()

        self.assertEqual(stats.sent, 1)
        self.assertEqual(stats.below_threshold, 0)
        stored = await repository.get_job("private-1")
        self.assertEqual(stored.event_type, EmailType.CLIENT_PRIVATE_MESSAGE.value)
        self.assertEqual(stored.full_description, email.body)
        self.assertEqual(stored.client_name, "Alex")
        self.assertTrue(stored.needs_context)
        self.assertEqual(stored.urgency, "high")

    async def test_security_event_is_redacted_without_ai_and_dedup_survives_restart(self):
        email = EmailMessage(
            id="security-1",
            sender="security@freelancehunt.com",
            subject="Security alert: new sign-in",
            body="Your one-time code: 123456. https://freelancehunt.com/reset?token=secret",
            text_body="Your one-time code: 123456.",
            links=["https://freelancehunt.com/reset?token=secret"],
            received_at=NOW,
        )
        shared_state: dict[str, object] = {}
        repository = InMemoryGmailRepository(shared_state)

        async def run_once(repo):
            processor = GmailJobProcessor(
                provider=MockGmailProvider([email]),
                bot=MagicMock(),
                chat_id=123,
                repository=repo,
            )
            with (
                patch("gmail_agent.processor.analyze_email", AsyncMock()) as analyze,
                patch("gmail_agent.processor.send_job_card", AsyncMock(return_value=True)) as send,
            ):
                stats = await processor.run()
            return stats, analyze, send

        first, analyze_first, send_first = await run_once(repository)
        restarted = InMemoryGmailRepository(shared_state)
        second, analyze_second, send_second = await run_once(restarted)

        self.assertEqual(first.sent, 1)
        self.assertEqual(second.sent, 0)
        self.assertEqual(second.duplicates_skipped, 1)
        analyze_first.assert_not_awaited()
        analyze_second.assert_not_awaited()
        send_first.assert_awaited_once()
        send_second.assert_not_awaited()
        stored = await restarted.get_job("security-1")
        self.assertNotIn("123456", stored.full_description)
        self.assertNotIn("https://", stored.full_description)
        self.assertTrue(stored.sensitive_redacted)


class TestFullContextReply(unittest.IsolatedAsyncioTestCase):
    async def test_existing_proposal_is_returned_without_model_call(self):
        client = MagicMock()
        client.chat.completions.create = AsyncMock()
        result = await generate_reply(
            "Title",
            "FULL UNIQUE SPECIFICATION",
            "Freelancehunt",
            "100 USD",
            "https://example.test/project",
            client=client,
            existing_proposal="Stored original proposal",
        )
        self.assertEqual(result, "Stored original proposal")
        client.chat.completions.create.assert_not_awaited()

    async def test_rewrite_prompt_contains_full_description_case_price_and_timeline(self):
        choice = MagicMock()
        choice.message.content = "Rewritten proposal"
        completion = MagicMock(choices=[choice])
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=completion)

        full_spec = "FULL UNIQUE SPECIFICATION " + ("detail " * 400)
        await generate_reply(
            "Title",
            full_spec,
            "Freelancehunt",
            "100 USD",
            "https://example.test/project",
            client=client,
            language="en",
            selected_evidence="Gmail Job Agent",
            recommended_price="250 USD milestone",
            recommended_timeline="5 days",
            existing_proposal="Original proposal",
            rewrite=True,
        )
        prompt = client.chat.completions.create.await_args.kwargs["messages"][1]["content"]
        for expected in (
            "FULL UNIQUE SPECIFICATION",
            "Gmail Job Agent",
            "250 USD milestone",
            "5 days",
        ):
            self.assertIn(expected, prompt)


class TestMailboxIdentityGate(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(email_address: str) -> MagicMock:
        service = MagicMock()
        service.users.return_value.getProfile.return_value.execute.return_value = {
            "emailAddress": email_address,
            "messagesTotal": 1,
            "threadsTotal": 1,
        }
        service.users.return_value.labels.return_value.get.return_value.execute.return_value = {
            "messagesTotal": 1
        }
        return service

    async def test_wrong_oauth_mailbox_fails_closed(self):
        provider = RealGmailProvider(
            "unused.json", "unused-token.json", expected_account="adult@example.com"
        )
        provider._service = self._service("wrong@example.com")
        with self.assertRaisesRegex(RuntimeError, "mailbox mismatch"):
            await provider.get_account_profile()

    async def test_expected_oauth_mailbox_is_verified_with_users_get_profile(self):
        provider = RealGmailProvider(
            "unused.json", "unused-token.json", expected_account="adult@example.com"
        )
        provider._service = self._service("adult@example.com")
        profile = await provider.get_account_profile()
        self.assertEqual(profile["email_address"], "adult@example.com")
        self.assertEqual(provider.identity_alias, "ad***@example.com")

    def test_local_oauth_mismatch_never_writes_token_and_forces_account_chooser(self):
        flow = MagicMock()
        credentials = MagicMock()
        credentials.to_json.return_value = '{"must_not":"be_written"}'
        flow.run_local_server.return_value = credentials
        service = self._service("wrong@example.com")

        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            with (
                patch(
                    "gmail_agent.oauth_local._client_config",
                    return_value={"installed": {}},
                ),
                patch(
                    "google_auth_oauthlib.flow.InstalledAppFlow.from_client_config",
                    return_value=flow,
                ),
                patch("googleapiclient.discovery.build", return_value=service),
            ):
                with self.assertRaisesRegex(RuntimeError, "mailbox mismatch"):
                    run_oauth(
                        "unused.json",
                        str(token_path),
                        "adult@example.com",
                        open_browser=False,
                    )

            self.assertFalse(token_path.exists())
        flow.run_local_server.assert_called_once_with(
            port=0,
            open_browser=False,
            prompt="select_account",
        )


class TestMigrationBrandAndScheduler(unittest.TestCase):
    def test_stage2_columns_use_only_additive_migrations(self):
        models = (PROJECT_ROOT / "db" / "models.py").read_text(encoding="utf-8")
        required = (
            "event_type",
            "full_description",
            "description_completeness",
            "language",
            "deadline",
            "bid_count",
            "client_context",
            "recommended_price",
            "proposal_draft",
            "received_at",
            "sensitive_redacted",
        )
        for column in required:
            self.assertIn(f"ADD COLUMN IF NOT EXISTS {column}", models)
        migrations = models[models.index("_MIGRATIONS = [") :]
        self.assertNotIn("DROP TABLE", migrations.upper())
        self.assertNotIn("DELETE FROM", migrations.upper())

    def test_active_pipeline_contains_no_old_brand(self):
        paths = [
            PROJECT_ROOT / "gmail_agent",
            PROJECT_ROOT / "bot",
            PROJECT_ROOT / "ai",
            PROJECT_ROOT / "scheduler.py",
        ]
        offenders = []
        for path in paths:
            files = [path] if path.is_file() else list(path.rglob("*.py"))
            for file in files:
                if "tests" in file.parts:
                    continue
                if "OptiDigital" in file.read_text(encoding="utf-8"):
                    offenders.append(str(file.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_scheduler_defaults_to_sixty_seconds_with_overlap_protection(self):
        scheduler = (PROJECT_ROOT / "gmail_agent" / "scheduler.py").read_text(
            encoding="utf-8"
        )
        config = (PROJECT_ROOT / "config.py").read_text(encoding="utf-8")
        self.assertIn("GMAIL_CHECK_INTERVAL_MINUTES: int = 1", config)
        self.assertIn("max_instances=1", scheduler)
        self.assertIn("coalesce=True", scheduler)


if __name__ == "__main__":
    unittest.main(verbosity=2)
