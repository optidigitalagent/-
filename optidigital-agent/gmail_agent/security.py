"""Redaction helpers for content that may leave Gmail for Telegram."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlsplit


_SENSITIVE_URL_KEYS = {
    "code",
    "key",
    "otp",
    "reset",
    "reset_token",
    "secret",
    "signature",
    "token",
    "verification",
    "verify",
}
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_OTP_RE = re.compile(
    r"(?i)(\b(?:otp|one[- ]time\s+(?:code|password)|verification\s+code|"
    r"security\s+code|код\s+(?:підтвердження|подтверждения|безпеки|безопасности)|"
    r"одноразов(?:ий|ый)\s+код|kod\s+(?:weryfikacyjny|jednorazowy))\b"
    r"[^\r\n\dA-Z]{0,24})([A-Z0-9][A-Z0-9 -]{3,14}[A-Z0-9])"
)
_TOKEN_RE = re.compile(
    r"(?i)(\b(?:reset[_ -]?token|access[_ -]?token|refresh[_ -]?token|"
    r"verification[_ -]?token|secret)\b\s*[:=]\s*)([^\s<>]{8,})"
)
_CREDENTIAL_RE = re.compile(
    r"(?im)(\b(?:password|passwd|pwd|api[_ -]?key|api[_ -]?secret|"
    r"client[_ -]?secret|recovery[_ -]?code|парол(?:ь|я)|код\s+восстановления|"
    r"секрет(?:ный)?\s+ключ|hasło|kod\s+odzyskiwania|tajny\s+klucz)\b"
    r"\s*[:=]\s*)([^\s,;<>]{3,})"
)


def _is_sensitive_url(url: str) -> bool:
    try:
        parsed = urlsplit(url.rstrip(".,;:!?)]}"))
    except ValueError:
        return True
    path = parsed.path.casefold()
    if any(marker in path for marker in ("/reset", "/verify", "/password", "/login/token")):
        return True
    return any(key.casefold() in _SENSITIVE_URL_KEYS for key, _ in parse_qsl(parsed.query))


def redact_sensitive_content(text: str, *, security_event: bool = False) -> tuple[str, bool]:
    """Redact OTPs, token material and sensitive URLs.

    Security/account cards redact every link so the owner is directed to open
    Gmail or Freelancehunt directly. Other cards keep ordinary public links but
    still remove reset/verification URLs containing credentials.
    """

    value = text or ""
    changed = False

    def replace_url(match: re.Match[str]) -> str:
        nonlocal changed
        url = match.group(0)
        if security_event or _is_sensitive_url(url):
            changed = True
            return "[SENSITIVE LINK REDACTED]"
        return url

    value = _URL_RE.sub(replace_url, value)
    updated = _OTP_RE.sub(r"\1[OTP REDACTED]", value)
    changed = changed or updated != value
    value = updated
    updated = _TOKEN_RE.sub(r"\1[TOKEN REDACTED]", value)
    changed = changed or updated != value
    value = updated
    updated = _CREDENTIAL_RE.sub(r"\1[CREDENTIAL REDACTED]", value)
    changed = changed or updated != value
    return updated, changed


def redact_security_event(text: str) -> tuple[str, bool]:
    return redact_sensitive_content(text, security_event=True)
