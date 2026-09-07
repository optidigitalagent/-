"""Deterministic extraction of individual jobs from Freelancehunt digests."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup, Tag

from .project_identity import (
    canonical_freelancehunt_project_url,
    freelancehunt_project_id,
    freelancehunt_project_stable_key,
)


_PLATFORM = "Freelancehunt"
MATERIALS_STATUSES = frozenset(
    {
        "UNKNOWN",
        "NOT_REFERENCED",
        "AVAILABLE",
        "UNAVAILABLE_SCOPE_RELEVANT",
        "UNAVAILABLE_EXECUTION_INPUTS_ONLY",
    }
)
SCOPE_SUFFICIENCY_STATES = frozenset(
    {"UNKNOWN", "INSUFFICIENT_FOR_FIXED_TERMS", "SUFFICIENT_FOR_FIXED_TERMS"}
)
SCOPE_ENRICHMENT_SOURCES = frozenset(
    {"PUBLIC_PAGE_VERIFIED", "GMAIL_FULL_BODY", "SYNTHETIC_TEST"}
)


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
    deadline: str = ""
    bid_count: int | None = None
    client_name: str = ""
    client_profile_url: str = ""
    project_id: str = ""
    tags: str = ""
    budget_currency: str = ""
    source_publication_at: datetime | None = None
    source_feed_timestamp: datetime | None = None
    feed_fetched_at: datetime | None = None
    first_seen_at: datetime | None = None
    discovery_source: str = "gmail_digest"
    event_type: str = "PROJECT_DIGEST"
    description_completeness: str = "PARTIAL"
    materials_status: str = "UNKNOWN"
    scope_sufficiency: str = "UNKNOWN"
    scope_enrichment_source: str = ""
    scope_enrichment_sha256: str = ""


def _scope_enrichment_digest(candidate: DigestJobCandidate) -> str:
    payload = {
        "stable_key": candidate.stable_key,
        "url": candidate.url,
        "description": candidate.description,
        "description_completeness": candidate.description_completeness,
        "materials_status": candidate.materials_status,
        "scope_sufficiency": candidate.scope_sufficiency,
        "scope_enrichment_source": candidate.scope_enrichment_source,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def enrich_candidate_scope(
    candidate: DigestJobCandidate,
    *,
    description: str,
    source_kind: str,
    main_text_completeness: str,
    materials_status: str,
    scope_sufficiency: str,
) -> DigestJobCandidate:
    """Create an auditable source enrichment instead of trusting a FULL label."""

    source = str(source_kind or "").strip().upper()
    completeness = str(main_text_completeness or "").strip().upper()
    materials = str(materials_status or "").strip().upper()
    sufficiency = str(scope_sufficiency or "").strip().upper()
    if source not in SCOPE_ENRICHMENT_SOURCES:
        raise ValueError("unsupported scope enrichment source")
    if completeness not in {"FULL", "PARTIAL"} or not str(description or "").strip():
        raise ValueError("scope enrichment requires non-empty bounded source text")
    if materials not in MATERIALS_STATUSES:
        raise ValueError("unsupported materials status")
    if sufficiency not in SCOPE_SUFFICIENCY_STATES:
        raise ValueError("unsupported scope sufficiency")
    if (
        materials == "UNAVAILABLE_SCOPE_RELEVANT"
        and sufficiency != "INSUFFICIENT_FOR_FIXED_TERMS"
    ):
        raise ValueError("scope-relevant missing materials cannot authorize fixed terms")
    if (
        materials == "UNAVAILABLE_EXECUTION_INPUTS_ONLY"
        and sufficiency != "SUFFICIENT_FOR_FIXED_TERMS"
    ):
        raise ValueError("execution-input condition requires sufficient main scope")
    enriched = replace(
        candidate,
        description=" ".join(str(description).split())[:16_000],
        description_completeness=completeness,
        materials_status=materials,
        scope_sufficiency=sufficiency,
        scope_enrichment_source=source,
        scope_enrichment_sha256="",
    )
    return replace(enriched, scope_enrichment_sha256=_scope_enrichment_digest(enriched))


def normalize_candidate_scope(candidate: DigestJobCandidate) -> DigestJobCandidate:
    """Fail RSS candidates back to PARTIAL unless enrichment proof is intact."""

    discovery_sources = {
        value.strip().casefold()
        for value in str(candidate.discovery_source or "").split("+")
        if value.strip()
    }
    if "rss" not in discovery_sources:
        return candidate
    expected = _scope_enrichment_digest(replace(candidate, scope_enrichment_sha256=""))
    verified = bool(candidate.scope_enrichment_sha256) and hmac.compare_digest(
        candidate.scope_enrichment_sha256,
        expected,
    )
    if verified and candidate.scope_enrichment_source in SCOPE_ENRICHMENT_SOURCES:
        return candidate
    return replace(
        candidate,
        description_completeness="PARTIAL",
        materials_status="UNKNOWN",
        scope_sufficiency="UNKNOWN",
        scope_enrichment_source="",
        scope_enrichment_sha256="",
    )


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

    normalized = canonical_freelancehunt_project_url(href)
    return normalized or None


def _stable_key(
    platform: str,
    normalized_url: str,
    title: str,
    description: str,
) -> str:
    if normalized_url:
        canonical_key = freelancehunt_project_stable_key(normalized_url)
        if canonical_key:
            return canonical_key
    # Non-project fallback remains deterministic for legacy synthetic callers.
    import hashlib

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


def _card_parts(anchor: Tag) -> tuple[str, str, str, str, str, int | None, str] | None:
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
    deadline = _first_class_text(table, "deadline") or _first_class_text(table, "term")
    bid_text = _first_class_text(table, "bid") or _first_class_text(table, "proposal")
    bid_match = re.search(r"\d+", bid_text)
    bid_count = int(bid_match.group(0)) if bid_match else None
    client_name = _first_class_text(table, "client") or _first_class_text(table, "employer")
    normalized_url = _normalize_direct_job_url(str(title_anchor.get("href", "")))
    if normalized_url is None:
        return None
    return title, description, budget, category, deadline, bid_count, client_name


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
        title, description, budget, category, deadline, bid_count, client_name = parts
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
                deadline=deadline,
                bid_count=bid_count,
                client_name=client_name,
                project_id=freelancehunt_project_id(normalized_url),
                first_seen_at=getattr(email, "received_at", None),
            )
        )
        if len(candidates) >= max_candidates:
            break

    return candidates
