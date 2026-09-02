"""Deterministic extraction of individual jobs from Freelancehunt digests."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag


_PLATFORM = "Freelancehunt"
_DIRECT_JOB_PATH = re.compile(
    r"/(?:ua/job|project|ua/project)/[^/]+/\d+\.html",
    re.IGNORECASE,
)
_ALLOWED_HOSTS = frozenset({"freelancehunt.com", "www.freelancehunt.com"})


@dataclass(frozen=True, slots=True)
class DigestJobCandidate:
    source_email_id: str
    platform: str
    title: str
    description: str
    budget: str
    url: str
    category: str
    received_at: datetime | None
    stable_key: str


def _clean_text(value: str) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def _normalized_identity_text(value: str) -> str:
    return _clean_text(value).casefold()


def _normalize_direct_job_url(href: str) -> str | None:
    """Return a safe canonical vacancy URL, or ``None`` for non-job links.

    The path is classified before tracking query/fragment data is removed.  A
    strict path and host allowlist excludes category, root, unsubscribe,
    profile, tracking and asset links without having to enumerate them.
    """

    try:
        parsed = urlsplit((href or "").strip())
        port = parsed.port
    except (TypeError, ValueError):
        return None

    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or hostname not in _ALLOWED_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
    ):
        return None

    # Classification intentionally precedes query/fragment stripping.
    if _DIRECT_JOB_PATH.fullmatch(parsed.path) is None:
        return None

    canonical_host = "freelancehunt.com"
    if port is not None and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        canonical_host = f"{canonical_host}:{port}"
    normalized = SplitResult(
        scheme=parsed.scheme.lower(),
        netloc=canonical_host,
        path=parsed.path,
        query="",
        fragment="",
    )
    return urlunsplit(normalized)


def _stable_key(
    platform: str,
    normalized_url: str,
    title: str,
    description: str,
) -> str:
    if normalized_url:
        identity = f"{platform}{normalized_url}"
    else:
        identity = (
            f"{platform}{_normalized_identity_text(title)}"
            f"{_normalized_identity_text(description)}"
        )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _has_class_fragment(tag: Tag, fragment: str) -> bool:
    classes = tag.get("class", ())
    if isinstance(classes, str):
        classes = classes.split()
    return any(fragment in str(class_name).casefold() for class_name in classes)


def _first_class_text(container: Tag, fragment: str) -> str:
    element = container.find(
        lambda tag: isinstance(tag, Tag) and _has_class_fragment(tag, fragment)
    )
    return _clean_text(element.get_text(" ", strip=True)) if element else ""


def _card_parts(anchor: Tag) -> tuple[str, str, str, str] | None:
    table = anchor.find_parent("table")
    if table is None:
        return None

    rows = table.find_all("tr")
    if len(rows) < 2:
        return None
    heading_row, description_row = rows[0], rows[1]

    # The audited digest structure puts the authoritative title link in row 1.
    title_anchor = None
    for candidate_anchor in heading_row.find_all("a", href=True):
        if _normalize_direct_job_url(str(candidate_anchor.get("href", ""))):
            title_anchor = candidate_anchor
            break
    if title_anchor is None:
        return None

    title = _clean_text(title_anchor.get_text(" ", strip=True))
    description = _clean_text(description_row.get_text(" ", strip=True))
    if not title or not description:
        return None

    budget = _first_class_text(heading_row, "budget")
    category = _first_class_text(table, "category")
    normalized_url = _normalize_direct_job_url(str(title_anchor.get("href", "")))
    if normalized_url is None:
        return None
    return title, description, budget, category


def parse_freelancehunt_digest(
    email: Any,
    max_candidates: int = 20,
) -> list[DigestJobCandidate]:
    """Extract unique Freelancehunt vacancy cards in document order."""

    if max_candidates <= 0:
        return []

    html = str(getattr(email, "html_body", "") or "")
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    candidates: list[DigestJobCandidate] = []
    seen_keys: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        normalized_url = _normalize_direct_job_url(str(anchor.get("href", "")))
        if normalized_url is None:
            continue

        parts = _card_parts(anchor)
        if parts is None:
            continue
        title, description, budget, category = parts
        stable_key = _stable_key(
            _PLATFORM,
            normalized_url,
            title,
            description,
        )
        if stable_key in seen_keys:
            continue

        seen_keys.add(stable_key)
        candidates.append(
            DigestJobCandidate(
                source_email_id=str(getattr(email, "id", "")),
                platform=_PLATFORM,
                title=title,
                description=description,
                budget=budget,
                url=normalized_url,
                category=category,
                received_at=getattr(email, "received_at", None),
                stable_key=stable_key,
            )
        )
        if len(candidates) >= max_candidates:
            break

    return candidates
