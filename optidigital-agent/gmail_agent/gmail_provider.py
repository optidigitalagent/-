"""Gmail provider — abstract interface, Mock, and Real OAuth2 implementations."""

import asyncio
import base64
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Any

logger = logging.getLogger(__name__)


def _gmail_reauth_message(reason: str) -> str:
    return (
        f"Gmail OAuth token cannot be refreshed ({reason}). "
        "Run local re-authorization: "
        "python -m gmail_agent.oauth_local --credentials credentials.json --token gmail_token.json. "
        "Then update GMAIL_TOKEN_JSON on Railway with the new gmail_token.json content."
    )


@dataclass
class EmailMessage:
    id: str
    subject: str
    sender: str
    body: str
    received_at: datetime
    raw_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailMatchDiagnostic:
    """Header-only job-alert match details safe for diagnostic output."""

    sender_display_name: str
    sender_email: str
    subject: str
    date: str
    platform: str
    sender_matched: bool
    subject_matched: bool
    is_job_alert: bool


class GmailProvider(ABC):
    @abstractmethod
    async def get_new_emails(self) -> list[EmailMessage]:
        """Return unprocessed job-alert emails."""

    @abstractmethod
    async def mark_as_processed(self, email_id: str) -> None:
        """Mark email as processed so it won't be returned again."""

    @abstractmethod
    async def get_recent_email_diagnostics(
        self, max_results: int = 10
    ) -> list[EmailMatchDiagnostic]:
        """Inspect recent email headers without bodies or processing side effects."""


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

    async def get_recent_email_diagnostics(
        self, max_results: int = 10
    ) -> list[EmailMatchDiagnostic]:
        return [
            build_email_diagnostic(
                sender=email.sender,
                subject=email.subject,
                date=email.received_at.isoformat() if email.received_at else "—",
            )
            for email in self._emails[:max_results]
        ]


# ── Real Gmail provider ───────────────────────────────────────────────────────

_JOB_ALERT_DOMAINS = {
    "freelancehunt.com": "Freelancehunt",
    "work.ua": "Work.ua",
    "robota.ua": "Robota.ua",
    "upwork.com": "Upwork",
}

_JOB_ALERT_SUBJECTS = [
    "новий проект",
    "новий проєкт",
    "new project",
    "нова вакансія",
    "new job",
    "job alert",
    "нові замовлення",
    "нові проекти",
    "нові проєкти",
    "підходящі вакансії",
    "matching jobs",
    "freelancehunt",
    "work.ua",
    "robota.ua",
    "upwork",
]


def _decode_email_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _match_sender_domain(domain: str) -> str:
    """Return the platform for an approved sender domain or subdomain."""
    normalized = domain.strip().lower().rstrip(".")
    for approved_domain, platform in _JOB_ALERT_DOMAINS.items():
        if normalized == approved_domain or normalized.endswith(f".{approved_domain}"):
            return platform
    return "Unknown"


def build_email_diagnostic(
    sender: str, subject: str, date: str = "—"
) -> EmailMatchDiagnostic:
    decoded_sender = _decode_email_header(sender)
    decoded_subject = _decode_email_header(subject)
    display_name, sender_email = parseaddr(decoded_sender)
    sender_email = sender_email.strip().lower()
    sender_domain = sender_email.rsplit("@", 1)[1] if "@" in sender_email else ""
    platform = _match_sender_domain(sender_domain)
    sender_matched = platform != "Unknown"
    subject_lower = decoded_subject.casefold()
    subject_matched = any(keyword.casefold() in subject_lower for keyword in _JOB_ALERT_SUBJECTS)

    if platform == "Unknown":
        for domain, detected_platform in _JOB_ALERT_DOMAINS.items():
            if domain in subject_lower:
                platform = detected_platform
                break

    return EmailMatchDiagnostic(
        sender_display_name=display_name.strip(),
        sender_email=sender_email,
        subject=decoded_subject,
        date=date,
        platform=platform,
        sender_matched=sender_matched,
        subject_matched=subject_matched,
        is_job_alert=sender_matched or subject_matched,
    )


class RealGmailProvider(GmailProvider):
    """
    Reads job alert emails from Gmail via OAuth2 API.

    Railway-safe (env vars take priority over files):
        GMAIL_TOKEN_JSON       — full JSON content of OAuth2 token
        GMAIL_CREDENTIALS_JSON — full JSON content of OAuth2 credentials (for reference)

    File fallback (local development):
        GMAIL_CREDENTIALS_FILE — path to credentials JSON file
        GMAIL_TOKEN_FILE       — path to token JSON file

    OAuth browser flow (run_local_server) is never triggered automatically.
    Generate a token locally first, then set GMAIL_TOKEN_JSON on Railway.
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
            from googleapiclient.discovery import build
        except ImportError:
            raise RuntimeError(
                "Google API libraries not installed.\n"
                "Run: pip install google-auth-oauthlib google-api-python-client"
            )

        import os
        token_json_env = os.getenv("GMAIL_TOKEN_JSON")

        creds = None
        _from_env = False

        if token_json_env:
            try:
                creds = Credentials.from_authorized_user_info(
                    json.loads(token_json_env), self.SCOPES
                )
                _from_env = True
            except Exception as exc:
                raise RuntimeError(f"Invalid GMAIL_TOKEN_JSON: {exc}") from exc
        elif os.path.exists(self._token_file):
            creds = Credentials.from_authorized_user_file(self._token_file, self.SCOPES)

        if creds and not creds.valid:
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as exc:
                    detail = str(exc)
                    if "invalid_grant" in detail:
                        raise RuntimeError(_gmail_reauth_message("invalid_grant")) from exc
                    raise RuntimeError(f"Gmail token refresh failed: {detail}") from exc
                if not _from_env:
                    try:
                        with open(self._token_file, "w") as f:
                            f.write(creds.to_json())
                    except OSError:
                        logger.warning("Could not save refreshed token to %s", self._token_file)
            else:
                creds = None

        if not creds or not creds.valid:
            raise RuntimeError(
                "Real Gmail requires valid GMAIL_TOKEN_JSON on server. "
                "Run OAuth locally first."
            )

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
        return build_email_diagnostic(msg.sender, msg.subject).is_job_alert

    @staticmethod
    def _metadata_diagnostic(raw_msg: dict) -> EmailMatchDiagnostic:
        payload = raw_msg.get("payload", {})
        headers = {
            header["name"].lower(): header["value"]
            for header in payload.get("headers", [])
        }
        return build_email_diagnostic(
            sender=headers.get("from", ""),
            subject=headers.get("subject", ""),
            date=headers.get("date", "—"),
        )

    def _fetch_recent_diagnostics(self, max_results: int) -> list[EmailMatchDiagnostic]:
        svc = self.service
        result = svc.users().messages().list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=max_results,
        ).execute()
        diagnostics: list[EmailMatchDiagnostic] = []
        for meta in result.get("messages", []):
            raw = svc.users().messages().get(
                userId="me",
                id=meta["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            diagnostics.append(self._metadata_diagnostic(raw))
        return diagnostics

    async def get_recent_email_diagnostics(
        self, max_results: int = 10
    ) -> list[EmailMatchDiagnostic]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_recent_diagnostics, max_results)

    def _fetch_account_profile(self) -> dict[str, Any]:
        """Return account identity and counts without reading any messages."""
        svc = self.service
        profile = svc.users().getProfile(userId="me").execute()
        inbox = svc.users().labels().get(userId="me", id="INBOX").execute()
        return {
            "email_address": profile.get("emailAddress", "unknown"),
            "messages_total": profile.get("messagesTotal", 0),
            "threads_total": profile.get("threadsTotal", 0),
            "inbox_messages_count": inbox.get("messagesTotal", 0),
            "oauth_status": "OK",
        }

    async def get_account_profile(self) -> dict[str, Any]:
        """Safely identify the OAuth account without exposing token material."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_account_profile)

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
            sender_matches = 0
            subject_matches = 0

            for meta in messages_meta:
                metadata = svc.users().messages().get(
                    userId="me",
                    id=meta["id"],
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                diagnostic = self._metadata_diagnostic(metadata)
                sender_matches += int(diagnostic.sender_matched)
                subject_matches += int(diagnostic.subject_matched)
                if not diagnostic.is_job_alert:
                    continue

                raw = svc.users().messages().get(
                    userId="me", id=meta["id"], format="full"
                ).execute()
                email = self._parse_message(raw)
                if email:
                    emails.append(email)

            logger.info(
                "RealGmailProvider: Inbox inspected: %d; Matched sender domain: %d; "
                "Matched subject keyword: %d; Returned job alerts: %d",
                len(messages_meta), sender_matches, subject_matches, len(emails),
            )
            return emails

        loop = asyncio.get_running_loop()
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
