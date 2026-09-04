"""Fail-closed parser for real Freelancehunt private-message notifications."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup

from .email_analyzer import detect_language
from .gmail_provider import EmailMessage
from .security import redact_sensitive_content


_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_THREAD_PATH_RE = re.compile(
    r"/(?:[a-z]{2}/)?mailbox/read/thread/(?P<id>\d+)(?:/)?$", re.IGNORECASE
)
_LEGACY_THREAD_PATH_RE = re.compile(
    r"/(?:thread|dialog|messages?)/(?P<id>\d+)(?:/)?$", re.IGNORECASE
)
_PROJECT_PATH_RE = re.compile(
    r"/(?:[a-z]{2}/)?project/(?:[^/?#]+/)?(?P<id>\d+)(?:\.html)?/?$",
    re.IGNORECASE,
)
_PROFILE_PATH_RE = re.compile(
    r"/(?:[a-z]{2}/)?(?:freelancer|profile)(?:/show)?/"
    r"(?P<slug>[^/?#]+?)(?:\.html)?/?$",
    re.IGNORECASE,
)
_SUBJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "uk",
        re.compile(
            r"^\s*Нове\s+особисте\s+повідомлення\s+від\s+(?P<sender>.+?)\s*:\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "ru",
        re.compile(
            r"^\s*Новое\s+личное\s+сообщение\s+от\s+(?P<sender>.+?)\s*:\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "en",
        re.compile(
            r"^\s*New\s+private\s+message\s+from\s+(?P<sender>.+?)\s*:\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
    ),
    (
        "pl",
        re.compile(
            r"^\s*(?:Nowa\s+)?Wiadomość\s+prywatna\s+od\s+(?P<sender>.+?)\s*:\s*(?P<title>.+?)\s*$",
            re.IGNORECASE,
        ),
    ),
)
_LOOSE_SENDER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("uk", re.compile(r"Нове\s+особисте\s+повідомлення\s+від\s+(.+)$", re.I)),
    ("ru", re.compile(r"Новое\s+личное\s+сообщение\s+от\s+(.+)$", re.I)),
    ("en", re.compile(r"New\s+private\s+message\s+from\s+(.+)$", re.I)),
    ("pl", re.compile(r"(?:Nowa\s+)?Wiadomość\s+prywatna\s+od\s+(.+)$", re.I)),
)
_REPLY_MARKERS = {
    "reply",
    "reply to message",
    "view and reply",
    "відповісти",
    "відповісти на повідомлення",
    "ответить",
    "ответить на сообщение",
    "odpowiedz",
    "odpowiedz na wiadomość",
}
_MESSAGE_LABELS = {"message", "message:", "повідомлення", "повідомлення:", "сообщение", "сообщение:", "wiadomość", "wiadomość:"}
_BOILERPLATE_EXACT = {
    "freelancehunt",
    "freelancehunt.com",
    "view profile",
    "переглянути профіль",
    "посмотреть профиль",
    "zobacz profil",
    "unsubscribe",
    "відписатися",
    "отписаться",
    "wypisz się",
}
_BOILERPLATE_PREFIXES = (
    "you received a new private message",
    "ви отримали нове особисте повідомлення",
    "вы получили новое личное сообщение",
    "otrzymałeś nową wiadomość prywatną",
    "this notification was sent",
    "це повідомлення надіслано",
    "это уведомление отправлено",
    "copyright ",
    "© ",
)
_MESSAGE_SELECTORS = (
    "[data-role='message']",
    "[data-testid='message-text']",
    ".private-message__text",
    ".private-message-text",
    ".message__text",
    ".message-text",
    ".mail-message-text",
    ".notification-message__text",
)


@dataclass(frozen=True, slots=True)
class FreelancehuntPrivateMessageNotification:
    sender_display_name: str
    sender_profile_slug: str
    conversation_subject: str
    actual_message_text: str
    thread_id: str
    safe_thread_url: str
    project_id: str
    project_url: str
    wrapper_language: str
    client_message_language: str
    is_platform_support_message: bool
    parse_confidence: str
    safe_parse_errors: tuple[str, ...]
    safe_excerpt: str


def normalize_conversation_title(value: str) -> str:
    """Exact-match normalization; intentionally no fuzzy or semantic matching."""

    normalized = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    normalized = normalized.translate(
        str.maketrans(
            {
                "–": "-",
                "—": "-",
                "−": "-",
                "‑": "-",
                "“": '"',
                "”": '"',
                "„": '"',
                "«": '"',
                "»": '"',
                "’": "'",
                "‘": "'",
            }
        )
    )
    normalized = re.sub(r"\s+", " ", normalized).strip().casefold()
    normalized = re.sub(r"\s*([-:\"'])\s*", r"\1", normalized)
    normalized = re.sub(r"[^\w\s\-:\"']+", "", normalized, flags=re.UNICODE)
    return re.sub(r"\s+", " ", normalized).strip()


def _clean_text(value: str, *, limit: int = 12000) -> str:
    decoded = unicodedata.normalize("NFKC", html.unescape(str(value or "")))
    decoded = decoded.replace("\u00a0", " ")
    decoded = re.sub(r"[ \t]+", " ", decoded)
    decoded = re.sub(r"\n\s*\n\s*\n+", "\n\n", decoded).strip()
    safe, _redacted = redact_sensitive_content(decoded[:limit])
    return safe.strip()


def _safe_url(value: str) -> str:
    candidate = html.unescape(str(value or "")).strip().rstrip(".,);]}")
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not (
        host == "freelancehunt.com" or host.endswith(".freelancehunt.com")
    ):
        return ""
    fragment = "last-message" if parsed.fragment.casefold() == "last-message" else ""
    return urlunparse(("https", host, parsed.path.rstrip("/"), "", "", fragment))


def _extract_links(email: EmailMessage, soup: BeautifulSoup | None) -> list[str]:
    raw: list[str] = list(email.links or [])
    raw.extend(_URL_RE.findall(f"{email.text_body or email.body or ''}\n{email.html_body or ''}"))
    if soup is not None:
        raw.extend(str(tag.get("href") or "") for tag in soup.find_all("a"))
    safe: list[str] = []
    for value in raw:
        url = _safe_url(value)
        if url and url not in safe:
            safe.append(url)
    return safe


def _parse_subject(subject: str) -> tuple[str, str, str, list[str]]:
    cleaned = _clean_text(subject, limit=1000)
    for language, pattern in _SUBJECT_PATTERNS:
        match = pattern.match(cleaned)
        if match:
            return (
                _clean_text(match.group("sender"), limit=500),
                _clean_text(match.group("title"), limit=1000),
                language,
                [],
            )
    for language, pattern in _LOOSE_SENDER_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return _clean_text(match.group(1), limit=500), "", language, ["conversation_subject_missing"]
    return "", "", detect_language(cleaned), ["notification_subject_unrecognized"]


def _is_boilerplate(line: str, *, sender: str, subject: str) -> bool:
    value = " ".join(line.casefold().split()).strip(" :")
    if not value:
        return True
    if sender and value == sender.casefold().strip(" :"):
        return True
    if subject and normalize_conversation_title(value) == normalize_conversation_title(subject):
        return True
    if value in _BOILERPLATE_EXACT or value in _REPLY_MARKERS or value in _MESSAGE_LABELS:
        return True
    return any(value.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES)


def _sanitize_message_candidate(value: str, *, sender: str, subject: str) -> str:
    kept: list[str] = []
    for raw_line in _clean_text(value).splitlines():
        line = raw_line.strip()
        if not line or _is_boilerplate(line, sender=sender, subject=subject):
            continue
        urls = _URL_RE.findall(line)
        if urls and all(_safe_url(url) for url in urls):
            # Profile, navigation, reply, project and tracking links are metadata,
            # never part of the copy-ready client message.
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _html_message(
    soup: BeautifulSoup, *, sender: str, subject: str
) -> tuple[str, list[str]]:
    candidates: list[str] = []
    for selector in _MESSAGE_SELECTORS:
        for node in soup.select(selector):
            for removable in node.select("a, button, nav, footer, script, style"):
                removable.decompose()
            candidate = _sanitize_message_candidate(
                node.get_text("\n", strip=True), sender=sender, subject=subject
            )
            if candidate and candidate not in candidates:
                candidates.append(candidate)
    if len(candidates) == 1:
        return candidates[0], []
    if len(candidates) > 1:
        return "", ["multiple_message_blocks"]
    return "", ["structured_message_block_missing"]


def _plain_message(
    value: str,
    *,
    sender: str,
    subject: str,
    has_safe_identity: bool,
) -> tuple[str, list[str]]:
    lines = [line.strip() for line in _clean_text(value).splitlines() if line.strip()]
    if not lines:
        return "", ["message_body_missing"]

    boundary = next(
        (
            index
            for index, line in enumerate(lines)
            if " ".join(line.casefold().split()).strip(" :") in _REPLY_MARKERS
            or bool(_THREAD_PATH_RE.search(urlparse(_safe_url(line)).path))
        ),
        len(lines),
    )
    prefix = lines[:boundary]
    start = 0
    marker_seen = False
    for index, line in enumerate(prefix):
        compact = " ".join(line.casefold().split()).strip(" :")
        urls = _URL_RE.findall(line)
        is_profile = any(_PROFILE_PATH_RE.search(urlparse(_safe_url(url)).path) for url in urls)
        if compact in _MESSAGE_LABELS or is_profile or (sender and compact == sender.casefold().strip(" :")):
            start = index + 1
            marker_seen = True
    candidate = _sanitize_message_candidate(
        "\n".join(prefix[start:]), sender=sender, subject=subject
    )
    if candidate and (marker_seen or boundary < len(lines)):
        return candidate, []

    # Deterministic compatibility path: the entire plain part is the client
    # message only when it has no notification-wrapper signals and the email
    # already carries one safe project/thread identity.
    wrapper_signal = any(
        any(pattern.search(line) for _language, pattern in _LOOSE_SENDER_PATTERNS)
        for line in lines
    )
    whole = _sanitize_message_candidate("\n".join(lines), sender=sender, subject=subject)
    if whole and has_safe_identity and not wrapper_signal:
        return whole, ["plain_body_used_as_message"]
    return "", ["actual_message_boundary_ambiguous"]


def _is_support_message(sender: str, slug: str, subject: str) -> bool:
    sender_key = normalize_conversation_title(sender)
    slug_key = slug.casefold().replace("-", "_")
    subject_key = normalize_conversation_title(subject)
    authoritative_staff_slug = slug_key.startswith("freelancehunt_")
    if authoritative_staff_slug:
        return True
    platform_identity = sender_key in {
        "freelancehunt",
        "freelancehunt support",
        "support freelancehunt",
    } or slug_key.startswith(("freelancehunt_", "support_", "help_"))
    support_topic = any(
        token in subject_key
        for token in (
            "onboarding",
            "account",
            "profile",
            "verification",
            "support",
            "welcome",
            "successful start",
            "успішний старт",
            "успешный старт",
            "udany start",
            "обліков",
            "акаунт",
            "профіл",
            "верифікац",
            "підтрим",
            "приветствуем",
            "поддержк",
            "konto",
            "profil",
            "weryfikac",
            "pomoc",
        )
    )
    return platform_identity and (support_topic or sender_key == "freelancehunt")


def _client_language(value: str) -> str:
    language = detect_language(value)
    if language != "en" or not re.search(r"[а-я]", value.casefold()):
        return language
    # The shared detector deliberately defaults to English. A message that is
    # clearly Cyrillic but has no language-exclusive letter must not inherit the
    # wrapper language; the conservative fallback for that script is Russian.
    return "ru"


def parse_freelancehunt_private_message_notification(
    email: EmailMessage,
) -> FreelancehuntPrivateMessageNotification:
    """Extract only the client-authored message and safe routing metadata."""

    sender, conversation_subject, wrapper_language, errors = _parse_subject(email.subject)
    soup = BeautifulSoup(email.html_body, "lxml") if email.html_body else None
    links = _extract_links(email, soup)
    thread_id = ""
    thread_url = ""
    project_id = ""
    project_url = ""
    profile_slug = ""
    for url in links:
        path = urlparse(url).path
        thread_match = _THREAD_PATH_RE.search(path) or _LEGACY_THREAD_PATH_RE.search(path)
        project_match = _PROJECT_PATH_RE.search(path)
        profile_match = _PROFILE_PATH_RE.search(path)
        if thread_match and not thread_id:
            thread_id, thread_url = thread_match.group("id"), url
        if project_match and not project_id:
            project_id, project_url = project_match.group("id"), url
        if profile_match and not profile_slug:
            profile_slug = profile_match.group("slug")

    message = ""
    html_errors: list[str] = []
    if soup is not None:
        message, html_errors = _html_message(soup, sender=sender, subject=conversation_subject)
    if not message and "multiple_message_blocks" not in html_errors:
        plain_source = email.text_body or email.body or (soup.get_text("\n") if soup else "")
        message, plain_errors = _plain_message(
            plain_source,
            sender=sender,
            subject=conversation_subject,
            has_safe_identity=bool(thread_id or project_id),
        )
        errors.extend(html_errors)
        errors.extend(plain_errors)
    elif html_errors:
        errors.extend(html_errors)
    if not thread_id:
        errors.append("thread_id_missing")
    if not message:
        errors.append("actual_message_not_isolated")

    safe_excerpt = _clean_text(
        message or email.text_body or email.body or (soup.get_text("\n") if soup else ""),
        limit=1200,
    )[:900]
    support = _is_support_message(sender, profile_slug, conversation_subject)
    confidence = (
        "HIGH"
        if message and thread_id and not errors
        else "MEDIUM"
        if message and (thread_id or project_id)
        else "FAILED"
    )
    return FreelancehuntPrivateMessageNotification(
        sender_display_name=sender,
        sender_profile_slug=profile_slug,
        conversation_subject=conversation_subject,
        actual_message_text=message,
        thread_id=thread_id,
        safe_thread_url=thread_url,
        project_id=project_id,
        project_url=project_url,
        wrapper_language=wrapper_language,
        client_message_language=_client_language(message) if message else "",
        is_platform_support_message=support,
        parse_confidence=confidence,
        safe_parse_errors=tuple(dict.fromkeys(errors)),
        safe_excerpt=safe_excerpt,
    )
