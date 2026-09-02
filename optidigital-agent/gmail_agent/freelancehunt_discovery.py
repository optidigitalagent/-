"""Fast official-RSS discovery for public Freelancehunt projects."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Awaitable, Callable

import httpx
from bs4 import BeautifulSoup

from .digest_parser import DigestJobCandidate
from .live_status import FreelancehuntLiveStatusChecker
from .processor import GmailJobProcessor, ProcessorStats
from .project_identity import (
    canonical_freelancehunt_project_url,
    freelancehunt_project_id,
    freelancehunt_project_stable_key,
)
from .storage import GmailRepository, PostgresGmailRepository, ScanRun


logger = logging.getLogger(__name__)

OFFICIAL_PROJECTS_RSS_URL = "https://freelancehunt.com/projects.rss"
DISCOVERY_TRIGGER = "freelancehunt_rss"
MAX_FEED_BYTES = 2_000_000

_BUDGET_PATTERN = re.compile(
    r"(?i)(?:\d[\d\s.,]*(?:\s*[-–]\s*\d[\d\s.,]*)?\s*"
    r"(?:UAH|USD|EUR|PLN|грн|₴|\$|€|zł))"
)
_CURRENCY_PATTERN = re.compile(r"(?i)UAH|USD|EUR|PLN|грн|₴|\$|€|zł")


class FeedParseError(ValueError):
    """The official feed did not satisfy the bounded RSS contract."""


@dataclass(frozen=True, slots=True)
class FeedBatch:
    candidates: list[DigestJobCandidate]
    fetched_at: datetime
    source_feed_timestamp: datetime | None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _child_text(parent: ET.Element, name: str) -> str:
    for child in list(parent):
        if _local_name(child.tag).casefold() == name.casefold():
            return "".join(child.itertext()).strip()
    return ""


def _parse_rfc822(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _plain_description(value: str) -> str:
    text = BeautifulSoup(unescape(value or ""), "html.parser").get_text(" ", strip=True)
    return " ".join(text.replace("\xa0", " ").split())[:16_000]


def _budget_fields(value: str) -> tuple[str, str]:
    match = _BUDGET_PATTERN.search(value or "")
    if match is None:
        return "", ""
    budget = " ".join(match.group(0).split())
    currency_match = _CURRENCY_PATTERN.search(budget)
    currency = currency_match.group(0).upper() if currency_match else ""
    currency = {"ГРН": "UAH", "₴": "UAH", "$": "USD", "€": "EUR", "ZŁ": "PLN"}.get(
        currency, currency
    )
    return budget, currency


def parse_freelancehunt_rss(
    xml_text: str,
    *,
    fetched_at: datetime | None = None,
    max_items: int = 50,
) -> FeedBatch:
    """Parse a bounded RSS document without fetching links or executing content."""

    fetched = fetched_at or datetime.now(timezone.utc)
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    fetched = fetched.astimezone(timezone.utc)
    payload = (xml_text or "").encode("utf-8", errors="ignore")
    if not payload or len(payload) > MAX_FEED_BYTES:
        raise FeedParseError("RSS payload is empty or exceeds the safe size limit")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise FeedParseError("RSS XML is malformed") from exc
    if _local_name(root.tag).casefold() != "rss":
        raise FeedParseError("document root is not RSS")
    channel = next(
        (child for child in list(root) if _local_name(child.tag).casefold() == "channel"),
        None,
    )
    if channel is None:
        raise FeedParseError("RSS channel is missing")

    feed_timestamp = _parse_rfc822(
        _child_text(channel, "lastBuildDate") or _child_text(channel, "pubDate")
    )
    candidates: list[DigestJobCandidate] = []
    seen_ids: set[str] = set()
    for item in list(channel):
        if _local_name(item.tag).casefold() != "item":
            continue
        canonical_url = canonical_freelancehunt_project_url(
            _child_text(item, "link") or _child_text(item, "guid")
        )
        project_id = freelancehunt_project_id(canonical_url)
        stable_key = freelancehunt_project_stable_key(
            canonical_url, project_id=project_id
        )
        title = " ".join(_child_text(item, "title").split())[:1000]
        if not canonical_url or not project_id or not stable_key or not title:
            continue
        if project_id in seen_ids:
            continue
        seen_ids.add(project_id)

        description = _plain_description(_child_text(item, "description"))
        categories = [
            " ".join("".join(child.itertext()).split())
            for child in list(item)
            if _local_name(child.tag).casefold() == "category"
        ]
        categories = list(dict.fromkeys(value for value in categories if value))
        category = ", ".join(categories)[:500]
        budget, currency = _budget_fields(f"{title}\n{description}")
        publication_at = _parse_rfc822(_child_text(item, "pubDate"))
        completeness = "FULL" if len(description) >= 240 else "PARTIAL"
        candidates.append(
            DigestJobCandidate(
                source_email_id=f"rss:{project_id}",
                platform="Freelancehunt",
                title=title,
                description=description,
                budget=budget,
                url=canonical_url,
                category=category,
                received_at=publication_at,
                stable_key=stable_key,
                project_id=project_id,
                tags=category,
                budget_currency=currency,
                source_publication_at=publication_at,
                source_feed_timestamp=feed_timestamp,
                feed_fetched_at=fetched,
                first_seen_at=fetched,
                discovery_source="rss",
                event_type="PROJECT_FEED",
                description_completeness=completeness,
            )
        )
        if len(candidates) >= max(0, max_items):
            break
    return FeedBatch(candidates, fetched, feed_timestamp)


class FreelancehuntFeedClient:
    """Anonymous official-feed reader with an injectable test fetcher."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        max_items: int = 50,
        fetcher: Callable[[], Awaitable[str]] | None = None,
    ) -> None:
        self._timeout_seconds = min(max(float(timeout_seconds), 0.1), 10.0)
        self._max_items = min(max(int(max_items), 1), 50)
        self._fetcher = fetcher

    async def fetch(self) -> FeedBatch:
        fetched_at = datetime.now(timezone.utc)
        if self._fetcher is not None:
            xml_text = await self._fetcher()
        else:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=True,
                headers={
                    "User-Agent": "Antonov-Digital-Instant-Discovery/1.0",
                    "Accept": "application/rss+xml,application/xml,text/xml",
                    "Accept-Language": "en",
                },
            ) as client:
                response = await client.get(OFFICIAL_PROJECTS_RSS_URL)
                response.raise_for_status()
                xml_text = response.text
        return parse_freelancehunt_rss(
            xml_text, fetched_at=fetched_at, max_items=self._max_items
        )


class _NoopProvider:
    async def mark_as_processed(self, _email_id: str) -> None:
        return None


class FreelancehuntDiscoveryPipeline:
    """Feed adapter over the existing guarded PostgreSQL/AI/Telegram pipeline."""

    def __init__(
        self,
        *,
        repository: GmailRepository,
        bot: Any,
        chat_id: int,
        feed_client: FreelancehuntFeedClient | None = None,
        openai_client: Any | None = None,
        live_status_checker: FreelancehuntLiveStatusChecker | None = None,
        max_new_projects_per_scan: int = 10,
    ) -> None:
        self._repository = repository
        self._feed_client = feed_client or FreelancehuntFeedClient()
        self._max_new_projects_per_scan = min(
            max(int(max_new_projects_per_scan), 1), 50
        )
        self._processor = GmailJobProcessor(
            provider=_NoopProvider(),
            bot=bot,
            chat_id=chat_id,
            # The feed path evaluates all truthful executable lanes. Fit remains
            # visible in the card but is not a hidden keyword/score drop gate.
            min_score=0.0,
            repository=repository,
            max_cards_per_scan=self._max_new_projects_per_scan,
            digest_enabled=True,
            openai_client=openai_client,
            live_status_checker=(
                live_status_checker or FreelancehuntLiveStatusChecker()
            ),
        )

    async def _bounded_workset(
        self, candidates: list[DigestJobCandidate]
    ) -> list[DigestJobCandidate]:
        selected: list[DigestJobCandidate] = []
        new_count = 0
        for candidate in candidates:
            processed = await self._repository.is_processed(candidate.stable_key)
            existing = await self._repository.get_job(candidate.stable_key)
            if processed or existing is not None:
                selected.append(candidate)
                continue
            if new_count < self._max_new_projects_per_scan:
                selected.append(candidate)
                new_count += 1
        return selected

    async def run(self) -> ProcessorStats:
        started_at = datetime.now(timezone.utc)
        try:
            await self._repository.reconcile_freelancehunt_identities()
            batch = await self._feed_client.fetch()
        except Exception as exc:
            stats = ProcessorStats(errors=1, parser_failures=1)
            stats.error_details.append(
                f"identity reconciliation or official RSS failed: {type(exc).__name__}"
            )
            await self._repository.append_scan_run(
                ScanRun(
                    trigger=DISCOVERY_TRIGGER,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    errors=1,
                    event_counts='{"PROJECT_FEED": 0}',
                )
            )
            logger.exception("Freelancehunt official RSS discovery failed")
            return stats
        selected = await self._bounded_workset(batch.candidates)
        return await self._processor.run_candidates(
            selected,
            trigger=DISCOVERY_TRIGGER,
            source_alias="official-public-rss",
            source_candidates_found=len(batch.candidates),
        )


async def check_freelancehunt_projects(bot: Any) -> None:
    """Production APScheduler entry point; never performs a platform action."""

    from config import settings
    from db import AsyncSessionLocal

    if not settings.FREELANCEHUNT_DISCOVERY_ENABLED:
        logger.debug("Freelancehunt instant discovery disabled")
        return
    repository = PostgresGmailRepository(AsyncSessionLocal)
    pipeline = FreelancehuntDiscoveryPipeline(
        repository=repository,
        bot=bot,
        chat_id=settings.TELEGRAM_CHAT_ID,
        max_new_projects_per_scan=settings.FREELANCEHUNT_DISCOVERY_MAX_NEW_PER_SCAN,
    )
    stats = await pipeline.run()
    logger.info(
        "Freelancehunt RSS scan completed candidates=%d ai=%d active=%d "
        "non_actionable=%d unknown=%d duplicates=%d sent=%d errors=%d",
        stats.candidates_found,
        stats.ai_analyzed,
        stats.live_status_active,
        stats.live_status_non_actionable,
        stats.live_status_unknown,
        stats.duplicates_skipped,
        stats.sent,
        stats.errors,
    )


def register_freelancehunt_discovery_job(
    scheduler: Any,
    bot: Any,
    *,
    interval_seconds: int = 60,
) -> None:
    """Register the dedicated overlap-protected 60-second feed poll."""

    scheduler.add_job(
        check_freelancehunt_projects,
        trigger="interval",
        seconds=max(60, int(interval_seconds)),
        id="check_freelancehunt_projects",
        args=[bot],
        max_instances=1,
        coalesce=True,
    )
    logger.info(
        "Freelancehunt instant discovery registered: interval=%d seconds",
        max(60, int(interval_seconds)),
    )
