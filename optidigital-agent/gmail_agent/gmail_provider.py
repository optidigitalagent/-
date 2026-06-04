"""Gmail provider — abstract interface, Mock, and Real OAuth2 implementations."""

import asyncio
import base64
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_bytes
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    body: str
    received_at: datetime
    raw_headers: dict[str, str] = field(default_factory=dict)


class GmailProvider(ABC):
    @abstractmethod
    async def get_new_emails(self) -> list[EmailMessage]:
        """Return unprocessed job-alert emails."""

    @abstractmethod
    async def mark_as_processed(self, email_id: str) -> None:
        """Mark email as processed so it won't be returned again."""


# ── Mock provider ─────────────────────────────────────────────────────────────

class MockGmailProvider(GmailProvider):
    """
    Returns a fixed set of mock emails — useful for tests and dry-runs.

    Deduplication is intentionally NOT handled here: it is the responsibility
    of EmailDedup in the processor, mirroring RealGmailProvider behaviour.
    """

    def __init__(self, emails: list[EmailMessage] | None = None):
        self._emails: list[EmailMessage] = emails or []

    async def get_new_emails(self) -> list[EmailMessage]:
        return list(self._emails)

    async def mark_as_processed(self, email_id: str) -> None:
        pass


# ── Real Gmail provider ───────────────────────────────────────────────────────

_JOB_ALERT_SENDERS = [
    "noreply@freelancehunt.com",
    "no-reply@freelancehunt.com",
    "info@freelancehunt.com",
    "notifications@work.ua",
    "noreply@work.ua",
    "noreply@robota.ua",
    "notification@robota.ua",
    "donotreply@upwork.com",
    "no-reply@upwork.com",
]

_JOB_ALERT_SUBJECTS = [
    "новий проект",
    "new project",
    "нова вакансія",
    "new job",
    "job alert",
    "нові замовлення",
    "нові проекти",
    "підходящі вакансії",
    "matching jobs",
    "freelancehunt",
    "work.ua",
    "robota.ua",
    "upwork",
]


class RealGmailProvider(GmailProvider):
    """
    Reads job alert emails from Gmail via OAuth2 API.

    Requires:
        GMAIL_CREDENTIALS_FILE — path to Google OAuth2 credentials JSON
        GMAIL_TOKEN_FILE — path to token storage file (created on first auth)

    Setup:
        1. Go to Google Cloud Console → Create project
        2. Enable Gmail API
        3. Create OAuth2 credentials (Desktop app)
        4. Download as credentials.json
        5. On first run: browser opens for auth, token saved to GMAIL_TOKEN_FILE
    """

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self, credentials_file: str, token_file: str, max_results: int = 50):
        self._credentials_file = credentials_file
        self._token_file = token_file
        self._max_results = max_results
        self._service: Any = None

    def _build_service(self) -> Any:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            raise RuntimeError(
                "Google API libraries not installed.\n"
                "Run: pip install google-auth-oauthlib google-api-python-client"
            )

        creds = None
        import os
        if os.path.exists(self._token_file):
            creds = Credentials.from_authorized_user_file(self._token_file, self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._credentials_file, self.SCOPES
                )
                creds = flow.run_local_server(port=0)
            with open(self._token_file, "w") as f:
                f.write(creds.to_json())

        return build("gmail", "v1", credentials=creds)

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _extract_body(self, msg_payload: dict) -> str:
        """Extract plain text body from Gmail message payload."""
        mime_type = msg_payload.get("mimeType", "")
        body_data = msg_payload.get("body", {}).get("data", "")

        if mime_type == "text/plain" and body_data:
            return base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")

        # Recurse into parts
        parts = msg_payload.get("parts", [])
        for part in parts:
            text = self._extract_body(part)
            if text:
                return text
        return ""

    def _parse_message(self, raw_msg: dict) -> EmailMessage | None:
        try:
            msg_id = raw_msg["id"]
            payload = raw_msg.get("payload", {})
            headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

            subject = headers.get("subject", "")
            sender = headers.get("from", "")
            date_str = headers.get("date", "")

            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_str)
            except Exception:
                received_at = datetime.utcnow()

            body = self._extract_body(payload)

            return EmailMessage(
                id=msg_id,
                subject=subject,
                sender=sender,
                body=body,
                received_at=received_at,
                raw_headers=headers,
            )
        except Exception:
            logger.exception("Failed to parse Gmail message %s", raw_msg.get("id"))
            return None

    def _is_job_alert(self, msg: EmailMessage) -> bool:
        sender_lower = msg.sender.lower()
        subject_lower = msg.subject.lower()

        sender_match = any(s in sender_lower for s in _JOB_ALERT_SENDERS)
        subject_match = any(kw in subject_lower for kw in _JOB_ALERT_SUBJECTS)

        return sender_match or subject_match

    async def get_new_emails(self) -> list[EmailMessage]:
        def _sync_fetch() -> list[EmailMessage]:
            svc = self.service
            result = svc.users().messages().list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=self._max_results,
            ).execute()

            messages_meta = result.get("messages", [])
            emails: list[EmailMessage] = []

            for meta in messages_meta:
                raw = svc.users().messages().get(
                    userId="me",
                    id=meta["id"],
                    format="full",
                ).execute()
                email = self._parse_message(raw)
                if email and self._is_job_alert(email):
                    emails.append(email)

            logger.info("RealGmailProvider: fetched %d job alert emails", len(emails))
            return emails

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_fetch)

    async def mark_as_processed(self, email_id: str) -> None:
        # We don't modify Gmail labels — dedup.py handles processed IDs locally
        pass


def build_provider(
    use_mock: bool = True,
    mock_emails: list[EmailMessage] | None = None,
    credentials_file: str = "credentials.json",
    token_file: str = "gmail_token.json",
) -> GmailProvider:
    if use_mock:
        return MockGmailProvider(emails=mock_emails or [])
    return RealGmailProvider(credentials_file=credentials_file, token_file=token_file)
