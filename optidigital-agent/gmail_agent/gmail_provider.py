"""Gmail provider — abstract interface, Mock, and Real OAuth2 implementations."""

import asyncio
import base64
import binascii
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlparse

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
    text_body: str = ""
    html_body: str = ""
    links: list[str] = field(default_factory=list)


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

    async def search_freelancehunt_emails(
        self, days: int = 7
    ) -> list[EmailMessage]:
        """Read Freelancehunt digest emails from the requested lookback window."""
        raise NotImplementedError


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

    async def search_freelancehunt_emails(
        self, days: int = 7
    ) -> list[EmailMessage]:
        _validate_lookback_days(days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        matches: list[EmailMessage] = []
        for email in self._emails:
            diagnostic = build_email_diagnostic(email.sender, email.subject)
            if not _is_freelancehunt_digest(diagnostic):
                continue
            received_at = email.received_at
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            if received_at >= cutoff:
                matches.append(email)
        return matches


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

_FREELANCEHUNT_DIGEST_SUBJECTS = (
    "підбірка вакансій",
    "підбірка проєктів",
    "підбірка проектів",
    "подборка вакансий",
    "подборка проектов",
)

_UNSAFE_HTML_TAGS = ("script", "style", "noscript", "template", "object", "embed")
_FOOTER_MARKERS = ("footer", "unsubscribe", "email-footer", "preferences")
_PLAIN_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)


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


def _validate_lookback_days(days: int) -> None:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be a positive integer")


def _is_freelancehunt_digest(diagnostic: EmailMatchDiagnostic) -> bool:
    subject = diagnostic.subject.casefold()
    return (
        diagnostic.sender_matched
        and diagnostic.platform == "Freelancehunt"
        and any(marker in subject for marker in _FREELANCEHUNT_DIGEST_SUBJECTS)
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

    @staticmethod
    def _decode_part_data(part: dict) -> str:
        encoded = part.get("body", {}).get("data", "")
        if not encoded:
            return ""
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded)
        except (TypeError, ValueError, binascii.Error):
            return ""

        headers = {
            header.get("name", "").casefold(): header.get("value", "")
            for header in part.get("headers", [])
        }
        content_type = headers.get("content-type", "")
        charset_match = re.search(
            r"charset\s*=\s*[\"']?([^\s;\"']+)", content_type, re.IGNORECASE
        )
        charset = charset_match.group(1) if charset_match else "utf-8"
        try:
            return decoded.decode(charset, errors="replace")
        except LookupError:
            return decoded.decode("utf-8", errors="replace")

    @staticmethod
    def _is_attachment(part: dict) -> bool:
        if part.get("filename") or part.get("body", {}).get("attachmentId"):
            return True
        for header in part.get("headers", []):
            if header.get("name", "").casefold() != "content-disposition":
                continue
            if "attachment" in header.get("value", "").casefold():
                return True
        return False

    def _collect_mime_parts(
        self,
        part: dict,
        plain_parts: list[str],
        html_parts: list[str],
    ) -> None:
        """Recursively collect inline text parts without loading attachments."""
        if self._is_attachment(part):
            return

        mime_type = part.get("mimeType", "").casefold()
        if mime_type == "text/plain":
            decoded = self._decode_part_data(part)
            if decoded:
                plain_parts.append(decoded)
        elif mime_type == "text/html":
            decoded = self._decode_part_data(part)
            if decoded:
                html_parts.append(decoded)

        for child in part.get("parts", []):
            self._collect_mime_parts(child, plain_parts, html_parts)

    @staticmethod
    def _has_hidden_style(tag: Any) -> bool:
        if getattr(tag, "attrs", None) is None:
            return False
        if tag.has_attr("hidden") or tag.get("aria-hidden", "").casefold() == "true":
            return True
        style = re.sub(r"\s+", "", tag.get("style", "").casefold())
        if any(
            marker in style
            for marker in ("display:none", "visibility:hidden", "opacity:0")
        ):
            return True
        classes = {str(value).casefold() for value in tag.get("class", [])}
        return bool(classes & {"hidden", "d-none", "display-none", "invisible"})

    @staticmethod
    def _is_tracking_image(tag: Any) -> bool:
        def _dimension(name: str) -> int | None:
            match = re.search(r"\d+", str(tag.get(name, "")))
            return int(match.group(0)) if match else None

        width = _dimension("width")
        height = _dimension("height")
        src = tag.get("src", "").casefold()
        alt = tag.get("alt", "").casefold()
        return (
            (width is not None and width <= 1)
            or (height is not None and height <= 1)
            or src.startswith("data:image/")
            or any(marker in src for marker in ("/track", "/pixel", "/open"))
            or "tracking pixel" in alt
        )

    @staticmethod
    def _is_safe_link(href: str) -> bool:
        try:
            parsed = urlparse(href)
        except (TypeError, ValueError):
            return False
        return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)

    def _clean_html(self, html: str) -> tuple[str, str, list[str]]:
        """Return sanitized HTML, visible text, and safe links."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(_UNSAFE_HTML_TAGS):
            tag.decompose()

        for tag in reversed(list(soup.find_all(True))):
            if self._has_hidden_style(tag):
                tag.decompose()

        for image in list(soup.find_all("img")):
            if self._is_tracking_image(image):
                image.decompose()

        for tag in reversed(list(soup.find_all(True))):
            identifiers = " ".join(
                [str(tag.get("id", "")), *[str(x) for x in tag.get("class", [])]]
            ).casefold()
            if any(marker in identifiers for marker in _FOOTER_MARKERS):
                tag.decompose()

        for footer in list(soup.find_all("footer")):
            footer.decompose()

        for anchor in list(soup.find_all("a", href=True)):
            href = anchor.get("href", "")
            combined = f"{href} {anchor.get_text(' ', strip=True)}".casefold()
            if "unsubscribe" in combined or "job-subscriptions" in combined:
                anchor.decompose()

        links: list[str] = []
        seen_links: set[str] = set()
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "").strip()
            if self._is_safe_link(href) and href not in seen_links:
                seen_links.add(href)
                links.append(href)

        visible_text = soup.get_text("\n", strip=True)
        visible_text = re.sub(r"\n{3,}", "\n\n", visible_text)
        return str(soup), visible_text, links

    def _extract_mime_content(
        self, msg_payload: dict
    ) -> tuple[str, str, str, list[str]]:
        plain_parts: list[str] = []
        html_parts: list[str] = []
        self._collect_mime_parts(msg_payload, plain_parts, html_parts)

        text_body = "\n\n".join(plain_parts)
        cleaned_html_parts: list[str] = []
        visible_html_parts: list[str] = []
        links: list[str] = []
        seen_links: set[str] = set()
        for html_part in html_parts:
            cleaned_html, visible_text, html_links = self._clean_html(html_part)
            cleaned_html_parts.append(cleaned_html)
            if visible_text:
                visible_html_parts.append(visible_text)
            for href in html_links:
                if href not in seen_links:
                    seen_links.add(href)
                    links.append(href)

        for match in _PLAIN_URL_RE.findall(text_body):
            href = match.rstrip(".,;:!?)]}")
            if self._is_safe_link(href) and href not in seen_links:
                seen_links.add(href)
                links.append(href)

        html_body = "\n".join(cleaned_html_parts)
        visible_html = "\n\n".join(visible_html_parts)
        body = text_body if text_body else visible_html
        return text_body, html_body, body, links

    def _extract_body(self, msg_payload: dict) -> str:
        """Backward-compatible primary body extraction."""
        return self._extract_mime_content(msg_payload)[2]

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

            text_body, html_body, body, links = self._extract_mime_content(payload)

            return EmailMessage(
                id=msg_id,
                subject=subject,
                sender=sender,
                body=body,
                received_at=received_at,
                raw_headers=headers,
                text_body=text_body,
                html_body=html_body,
                links=links,
            )
        except Exception as exc:
            logger.error("Failed to parse Gmail message (%s)", type(exc).__name__)
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

    def _fetch_freelancehunt_emails(self, days: int) -> list[EmailMessage]:
        """Fetch all matching digest emails in a lookback window, read-only."""
        _validate_lookback_days(days)
        svc = self.service
        query = f"from:(freelancehunt.com) newer_than:{days}d"
        page_token: str | None = None
        message_ids: list[str] = []
        seen_ids: set[str] = set()

        while True:
            list_kwargs: dict[str, Any] = {
                "userId": "me",
                "q": query,
                "maxResults": 100,
                "includeSpamTrash": False,
            }
            if page_token:
                list_kwargs["pageToken"] = page_token
            page = svc.users().messages().list(**list_kwargs).execute()
            for item in page.get("messages", []):
                message_id = item.get("id")
                if message_id and message_id not in seen_ids:
                    seen_ids.add(message_id)
                    message_ids.append(message_id)
            page_token = page.get("nextPageToken")
            if not page_token:
                break

        emails: list[EmailMessage] = []
        for message_id in message_ids:
            metadata = svc.users().messages().get(
                userId="me",
                id=message_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            diagnostic = self._metadata_diagnostic(metadata)
            if not _is_freelancehunt_digest(diagnostic):
                continue

            raw = svc.users().messages().get(
                userId="me", id=message_id, format="full"
            ).execute()
            email = self._parse_message(raw)
            if email is not None:
                emails.append(email)
        return emails

    async def search_freelancehunt_emails(
        self, days: int = 7
    ) -> list[EmailMessage]:
        """Read all Freelancehunt digest emails from the last ``days`` days."""
        _validate_lookback_days(days)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._fetch_freelancehunt_emails, days
        )

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
