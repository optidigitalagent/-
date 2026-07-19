"""Small, shared safety boundary for Telegram HTML output."""

from html import escape
from ipaddress import ip_address
import re
from typing import Any
from urllib.parse import urlsplit


def escape_html(value: Any) -> str:
    """Return a value safe for a Telegram HTML text or attribute context."""
    if value is None:
        return ""
    return escape(str(value), quote=True)


def _valid_hostname(hostname: str) -> bool:
    try:
        ip_address(hostname)
        return True
    except ValueError:
        pass

    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").rstrip(".")
    except UnicodeError:
        return False
    if not ascii_hostname or len(ascii_hostname) > 253:
        return False

    labels = ascii_hostname.split(".")
    return all(
        len(label) <= 63
        and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in labels
    )


def safe_http_url(value: Any) -> str | None:
    """Return a valid HTTP(S) URL, or None for unsafe/malformed values."""
    if value is None:
        return None

    raw = str(value).strip()
    if not raw or "\\" in raw or any(char.isspace() or ord(char) < 32 for char in raw):
        return None

    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        parsed.port  # Access validates that an explicit port is numeric and in range.
    except (TypeError, ValueError):
        return None

    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.netloc
        or not hostname
        or not _valid_hostname(hostname)
    ):
        return None
    return raw
