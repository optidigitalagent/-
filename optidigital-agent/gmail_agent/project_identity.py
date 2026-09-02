"""Canonical public Freelancehunt project identity shared by every ingest path."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlsplit, urlunsplit


_ALLOWED_HOSTS = frozenset({"freelancehunt.com", "www.freelancehunt.com"})
_PROJECT_PATH = re.compile(
    r"/(?:[a-z]{2}/)?(?:project|job)/[^/]+/(?P<project_id>\d+)\.html/?",
    re.IGNORECASE,
)
_PROJECT_ID = re.compile(r"\d+")


def canonical_freelancehunt_project_url(value: str) -> str:
    """Return a safe tracking-free public project URL or an empty string."""

    try:
        parsed = urlsplit((value or "").strip())
        port = parsed.port
    except (TypeError, ValueError):
        return ""
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or hostname not in _ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
        or _PROJECT_PATH.fullmatch(parsed.path) is None
    ):
        return ""
    return urlunsplit(("https", "freelancehunt.com", parsed.path.rstrip("/"), "", ""))


def freelancehunt_project_id(value: str = "", *, fallback: str = "") -> str:
    """Extract the durable numeric project ID from a public URL or safe fallback."""

    canonical_url = canonical_freelancehunt_project_url(value)
    if canonical_url:
        match = _PROJECT_PATH.fullmatch(urlsplit(canonical_url).path)
        if match is not None:
            return match.group("project_id")
    candidate = str(fallback or "").strip()
    return candidate if _PROJECT_ID.fullmatch(candidate) else ""


def freelancehunt_project_stable_key(value: str = "", *, project_id: str = "") -> str:
    """Hash one canonical project ID into the existing 64-char repository key shape."""

    canonical_id = freelancehunt_project_id(value, fallback=project_id)
    if not canonical_id:
        return ""
    identity = f"freelancehunt:project:{canonical_id}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def source_family(value: str) -> str:
    """Map detailed ingest labels to persisted cross-source dedup families."""

    normalized = str(value or "").casefold()
    if "rss" in normalized or "feed" in normalized:
        return "rss"
    if "gmail" in normalized or "digest" in normalized or "single_job" in normalized:
        return "gmail"
    if "parser" in normalized or "legacy" in normalized:
        return "parser"
    return normalized or "unknown"
