"""Read-only Freelancehunt project bid-eligibility verification.

The checker deliberately fails closed: a project is actionable only when the
live public page contains positive evidence that a bid can be submitted.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from html import unescape
from typing import Any, AsyncIterator, Awaitable, Callable
from urllib.parse import urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class LiveStatus(StrEnum):
    ACTIVE_BIDDABLE = "ACTIVE_BIDDABLE"
    BLOCKED_RULE_VIOLATION = "BLOCKED_RULE_VIOLATION"
    CLOSED = "CLOSED"
    EXECUTOR_SELECTED = "EXECUTOR_SELECTED"
    DELETED_OR_UNAVAILABLE = "DELETED_OR_UNAVAILABLE"
    LIVE_STATUS_UNKNOWN = "LIVE_STATUS_UNKNOWN"


@dataclass(frozen=True, slots=True)
class LiveStatusResult:
    status: LiveStatus
    checked_at: datetime
    evidence: str
    biddable: bool
    last_error: str = ""


@dataclass(frozen=True, slots=True)
class BiddableStatusGuard:
    """Outcome shared by every proposal display/generation/send action."""

    allowed: bool
    result: LiveStatusResult
    refreshed: bool


ACTION_FRESHNESS_SECONDS = 60
LIVE_STATUS_UNKNOWN_EXHAUSTED = "live_status_unknown_exhausted"


@dataclass(frozen=True, slots=True)
class _PageResponse:
    status_code: int
    html: str


_STATUS_MARKERS: tuple[tuple[LiveStatus, tuple[str, ...]], ...] = (
    (
        LiveStatus.BLOCKED_RULE_VIOLATION,
        (
            "проект заблокований фрилансерами за порушення правил сервісу",
            "проєкт заблокований фрилансерами за порушення правил сервісу",
            "проект заблокирован фрилансерами за нарушение правил сервиса",
            "project was blocked by freelancers for violating the service rules",
            "project has been blocked for violating the service rules",
            "projekt został zablokowany za naruszenie zasad serwisu",
            "projekt zablokowany za naruszenie zasad serwisu",
        ),
    ),
    (
        LiveStatus.EXECUTOR_SELECTED,
        (
            "виконавця обрано",
            "виконавець обраний",
            "исполнитель выбран",
            "исполнитель уже выбран",
            "executor selected",
            "contractor selected",
            "wybrano wykonawcę",
            "wykonawca został wybrany",
        ),
    ),
    (
        LiveStatus.CLOSED,
        (
            "проєкт закрито",
            "проект закрито",
            "проєкт завершено",
            "проект завершен",
            "проект закрыт",
            "прийом ставок завершено",
            "прием ставок завершен",
            "bidding is closed",
            "bidding closed",
            "project closed",
            "project completed",
            "project finished",
            "projekt zamknięty",
            "projekt zakończony",
            "składanie ofert zakończone",
        ),
    ),
    (
        LiveStatus.DELETED_OR_UNAVAILABLE,
        (
            "сторінку не знайдено",
            "сторінка не існує",
            "страница не найдена",
            "страница не существует",
            "project not found",
            "page not found",
            "project is unavailable",
            "nie znaleziono strony",
            "strona nie istnieje",
            "projekt jest niedostępny",
        ),
    ),
)

_BID_TEXT_MARKERS = (
    "зробити ставку",
    "подати ставку",
    "залишити ставку",
    "подати заявку",
    "залишити заявку",
    "сделать ставку",
    "подать ставку",
    "оставить ставку",
    "подать заявку",
    "оставить заявку",
    "submit a bid",
    "place a bid",
    "make a bid",
    "submit proposal",
    "make a proposal",
    "apply for this project",
    "złóż ofertę",
    "dodaj ofertę",
    "wyślij ofertę",
    "złóż propozycję",
)

_BID_URL_RE = re.compile(r"/(?:bid|bids|proposal|proposals|offer|offers)(?:/|$)", re.I)
_PROTECTION_MARKERS = (
    "cf-challenge",
    "challenges.cloudflare.com",
    "just a moment",
    "enable javascript and cookies to continue",
    "verify you are human",
    "captcha",
)
_PUBLIC_PROJECTS_RSS_URL = "https://freelancehunt.com/en/projects.rss"
_PROJECT_ID_RE = re.compile(r"/(?:project|job)/.+/(\d+)\.html$", re.I)


def clean_project_url(value: str) -> str:
    """Return a canonical public Freelancehunt project URL or an empty string."""

    try:
        parsed = urlsplit(value or "")
        port = parsed.port
    except (TypeError, ValueError):
        return ""
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold()
        not in {"freelancehunt.com", "www.freelancehunt.com"}
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return ""
    path = parsed.path or ""
    if not re.search(r"/(?:[a-z]{2}/)?(?:project|job)/.+/\d+\.html$", path, re.I):
        return ""
    return urlunsplit(("https", "freelancehunt.com", path, "", ""))


def retry_due(
    checked_at: datetime | None,
    retry_count: int,
    *,
    now: datetime | None = None,
    base_seconds: int = 60,
    max_seconds: int = 3600,
    max_retries: int = 3,
) -> bool:
    """Return whether an UNKNOWN project is eligible for another bounded retry."""

    if retry_count >= max_retries:
        return False
    if checked_at is None:
        return True
    current = now or datetime.now(timezone.utc)
    value = checked_at
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delay = min(max_seconds, max(1, base_seconds) * (2 ** max(0, retry_count - 1)))
    return current >= value + timedelta(seconds=delay)


def classify_live_html(html: str, *, checked_at: datetime | None = None) -> LiveStatusResult:
    """Classify sanitized page HTML using negative markers before bid evidence."""

    observed_at = checked_at or datetime.now(timezone.utc)
    soup = BeautifulSoup(html or "", "html.parser")
    for element in soup.find_all(("script", "style", "noscript", "template")):
        element.decompose()
    for element in reversed(soup.find_all(True)):
        style = str(element.get("style", "")).replace(" ", "").casefold()
        if (
            element.has_attr("hidden")
            or str(element.get("aria-hidden", "")).casefold() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            element.decompose()
    visible = " ".join(soup.stripped_strings)
    normalized = re.sub(r"\s+", " ", unescape(visible)).casefold()

    for status, markers in _STATUS_MARKERS:
        for marker in markers:
            if marker in normalized:
                return LiveStatusResult(
                    status=status,
                    checked_at=observed_at,
                    evidence=marker,
                    biddable=False,
                )

    for element in soup.find_all(("a", "button", "input", "form")):
        disabled = (
            element.has_attr("disabled")
            or str(element.get("aria-disabled", "")).casefold() == "true"
            or any(
                "disabled" in str(item).casefold()
                for item in element.get("class", [])
            )
            or any(parent.has_attr("disabled") for parent in element.parents)
        )
        if disabled:
            continue
        # A form's descendant text can come entirely from a disabled submit
        # button. Treat the form itself as evidence only through its action;
        # enabled controls are evaluated independently below.
        element_text = "" if element.name == "form" else element.get_text(" ", strip=True)
        label = " ".join(
            part
            for part in (
                element_text,
                str(element.get("value", "")),
                str(element.get("aria-label", "")),
                str(element.get("title", "")),
            )
            if part
        )
        target = str(element.get("href", "") or element.get("action", ""))
        normalized_label = re.sub(r"\s+", " ", label).casefold()
        matched_text = next(
            (marker for marker in _BID_TEXT_MARKERS if marker in normalized_label),
            "",
        )
        if matched_text or _BID_URL_RE.search(target):
            evidence = matched_text or "enabled bid form/action"
            return LiveStatusResult(
                status=LiveStatus.ACTIVE_BIDDABLE,
                checked_at=observed_at,
                evidence=evidence,
                biddable=True,
            )

    return LiveStatusResult(
        status=LiveStatus.LIVE_STATUS_UNKNOWN,
        checked_at=observed_at,
        evidence="No enabled bid form or bid CTA was positively verified.",
        biddable=False,
        last_error="bid CTA not verified",
    )


class FreelancehuntLiveStatusChecker:
    """Bounded HTTP-first, cookie-free browser-fallback status checker.

    One ``scan()`` scope shares an anonymous HTTP client and, when needed, one
    anonymous Chromium browser/context.  URLs are deduplicated per scan and a
    short TTL cache prevents repeated reads between adjacent read-only actions.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        http_timeout_seconds: float = 5.0,
        playwright_timeout_seconds: float = 8.0,
        max_concurrency: int = 4,
        scan_budget_seconds: float = 80.0,
        cache_ttl_seconds: float = 30.0,
        http_fetcher: Callable[[str], Awaitable[_PageResponse]] | None = None,
        playwright_fetcher: Callable[[str], Awaitable[_PageResponse]] | None = None,
        rss_fetcher: Callable[[], Awaitable[_PageResponse]] | None = None,
    ) -> None:
        # ``timeout_seconds`` remains accepted for old injected tests, but is
        # clamped to the production maxima required by the hotfix.
        if timeout_seconds is not None:
            http_timeout_seconds = min(float(timeout_seconds), 5.0)
            playwright_timeout_seconds = min(float(timeout_seconds), 8.0)
        self._http_timeout_seconds = min(max(float(http_timeout_seconds), 0.01), 5.0)
        self._playwright_timeout_seconds = min(
            max(float(playwright_timeout_seconds), 0.01), 8.0
        )
        self._max_concurrency = min(max(int(max_concurrency), 3), 5)
        self._scan_budget_seconds = min(max(float(scan_budget_seconds), 0.01), 90.0)
        self._cache_ttl_seconds = max(float(cache_ttl_seconds), 0.0)
        self._http_fetcher = http_fetcher or self._fetch_http
        self._playwright_fetcher = playwright_fetcher or self._fetch_playwright
        # Do not let injected page fetchers unexpectedly reach the network in
        # tests.  Production defaults use the official public open-project RSS.
        self._rss_fetcher = (
            rss_fetcher
            if rss_fetcher is not None
            else self._fetch_public_projects_rss
            if http_fetcher is None and playwright_fetcher is None
            else None
        )
        self._scan_depth = 0
        self._deadline = 0.0
        self._scan_tasks: dict[str, asyncio.Task[LiveStatusResult]] = {}
        self._ttl_cache: dict[str, tuple[float, LiveStatusResult]] = {}
        self._rss_task: asyncio.Task[_PageResponse] | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._browser_context: Any | None = None
        self._browser_lock = asyncio.Lock()

    @asynccontextmanager
    async def scan(self) -> AsyncIterator["FreelancehuntLiveStatusChecker"]:
        """Open a bounded reusable anonymous scan scope."""

        outermost = self._scan_depth == 0
        self._scan_depth += 1
        if outermost:
            self._deadline = time.monotonic() + self._scan_budget_seconds
            self._scan_tasks = {}
            self._rss_task = None
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
        try:
            yield self
        finally:
            self._scan_depth -= 1
            if outermost:
                for task in self._scan_tasks.values():
                    if not task.done():
                        task.cancel()
                if self._rss_task is not None and not self._rss_task.done():
                    self._rss_task.cancel()
                await self._close_resources()
                self._scan_tasks = {}
                self._rss_task = None
                self._semaphore = None

    async def __aenter__(self) -> "FreelancehuntLiveStatusChecker":
        self._owned_scope = self.scan()
        return await self._owned_scope.__aenter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._owned_scope.__aexit__(exc_type, exc, tb)

    async def check(self, url: str) -> LiveStatusResult:
        if self._scan_depth == 0:
            async with self.scan():
                return await self.check(url)

        clean_url = clean_project_url(url)
        cache_key = clean_url or f"invalid:{url}"
        cached = self._ttl_cache.get(cache_key)
        now_monotonic = time.monotonic()
        if cached is not None and now_monotonic - cached[0] <= self._cache_ttl_seconds:
            return cached[1]

        task = self._scan_tasks.get(cache_key)
        if task is None:
            task = asyncio.create_task(self._bounded_check(url))
            self._scan_tasks[cache_key] = task
        result = await task
        self._ttl_cache[cache_key] = (time.monotonic(), result)
        return result

    async def batch_check(self, urls: list[str]) -> dict[str, LiveStatusResult]:
        """Check unique URLs concurrently inside one deadline/resource scope."""

        if self._scan_depth == 0:
            async with self.scan():
                return await self.batch_check(urls)
        unique = list(dict.fromkeys(urls))
        tasks = {url: asyncio.create_task(self.check(url)) for url in unique}
        remaining = max(0.0, self._deadline - time.monotonic())
        try:
            async with asyncio.timeout(remaining):
                values = await asyncio.gather(*tasks.values())
        except TimeoutError:
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            values = [
                task.result() if task.done() and not task.cancelled() and task.exception() is None
                else self._unknown("overall scan budget exhausted")
                for task in tasks.values()
            ]
        return dict(zip(tasks, values, strict=True))

    async def _bounded_check(self, url: str) -> LiveStatusResult:
        semaphore = self._semaphore or asyncio.Semaphore(self._max_concurrency)
        async with semaphore:
            remaining = max(0.0, self._deadline - time.monotonic())
            if remaining <= 0:
                return self._unknown("overall scan budget exhausted")
            try:
                async with asyncio.timeout(remaining):
                    return await self._check_uncached(url)
            except TimeoutError:
                return self._unknown("overall scan budget exhausted")

    async def _check_uncached(self, url: str) -> LiveStatusResult:
        checked_at = datetime.now(timezone.utc)
        clean_url = clean_project_url(url)
        if not clean_url:
            return LiveStatusResult(
                status=LiveStatus.DELETED_OR_UNAVAILABLE,
                checked_at=checked_at,
                evidence="Invalid or non-public Freelancehunt project URL.",
                biddable=False,
                last_error="invalid project URL",
            )

        http_error = ""
        try:
            response = await asyncio.wait_for(
                self._http_fetcher(clean_url), timeout=self._http_timeout_seconds
            )
            if response.status_code in {404, 410}:
                return LiveStatusResult(
                    status=LiveStatus.DELETED_OR_UNAVAILABLE,
                    checked_at=checked_at,
                    evidence=f"HTTP {response.status_code}",
                    biddable=False,
                )
            if response.status_code == 200 and not self._is_protected(response.html):
                result = classify_live_html(response.html, checked_at=checked_at)
                if result.status != LiveStatus.LIVE_STATUS_UNKNOWN:
                    return result
                http_error = result.last_error
            else:
                http_error = f"HTTP {response.status_code} or protected HTML"
        except Exception as exc:
            http_error = f"HTTP {type(exc).__name__}"
            logger.info("Freelancehunt live-status HTTP check failed: %s", type(exc).__name__)

        # The official public RSS is a current list of open projects and remains
        # anonymously readable when Cloudflare protects HTML pages. Membership
        # is positive ACTIVE evidence; absence is deliberately not terminal.
        rss_result, rss_error = await self._check_public_projects_rss(
            clean_url, checked_at=checked_at
        )
        if rss_result is not None:
            return rss_result

        try:
            response = await asyncio.wait_for(
                self._playwright_fetcher(clean_url),
                timeout=self._playwright_timeout_seconds,
            )
            if response.status_code in {404, 410}:
                return LiveStatusResult(
                    status=LiveStatus.DELETED_OR_UNAVAILABLE,
                    checked_at=checked_at,
                    evidence=f"Browser HTTP {response.status_code}",
                    biddable=False,
                )
            if response.status_code == 200 and not self._is_protected(response.html):
                return classify_live_html(response.html, checked_at=checked_at)
            browser_error = f"Browser HTTP {response.status_code} or protected HTML"
        except Exception as exc:
            browser_error = f"Playwright {type(exc).__name__}"
            logger.info("Freelancehunt live-status browser fallback failed: %s", type(exc).__name__)

        last_error = f"{http_error}; {rss_error}; {browser_error}".strip("; ")
        return LiveStatusResult(
            status=LiveStatus.LIVE_STATUS_UNKNOWN,
            checked_at=checked_at,
            evidence="LIVE STATUS NOT VERIFIED",
            biddable=False,
            last_error=last_error[:500],
        )

    @staticmethod
    def _unknown(error: str) -> LiveStatusResult:
        return LiveStatusResult(
            status=LiveStatus.LIVE_STATUS_UNKNOWN,
            checked_at=datetime.now(timezone.utc),
            evidence="LIVE STATUS NOT VERIFIED",
            biddable=False,
            last_error=error[:500],
        )

    @staticmethod
    def _is_protected(html: str) -> bool:
        normalized = (html or "").casefold()
        return any(marker in normalized for marker in _PROTECTION_MARKERS)

    async def _fetch_http(self, url: str) -> _PageResponse:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.7",
        }
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers=headers,
                timeout=self._http_timeout_seconds,
                follow_redirects=True,
            )
        response = await self._http_client.get(url)
        return _PageResponse(response.status_code, response.text)

    async def _fetch_public_projects_rss(self) -> _PageResponse:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                headers={
                    "User-Agent": "Antonov-Digital-Live-Status/1.0",
                    "Accept": "application/rss+xml,application/xml,text/xml",
                    "Accept-Language": "en",
                },
                timeout=self._http_timeout_seconds,
                follow_redirects=True,
            )
        response = await self._http_client.get(_PUBLIC_PROJECTS_RSS_URL)
        return _PageResponse(response.status_code, response.text)

    async def _check_public_projects_rss(
        self, clean_url: str, *, checked_at: datetime
    ) -> tuple[LiveStatusResult | None, str]:
        if self._rss_fetcher is None:
            return None, ""
        match = _PROJECT_ID_RE.search(urlsplit(clean_url).path)
        if match is None:
            return None, "RSS project id unavailable"
        try:
            if self._rss_task is None:
                self._rss_task = asyncio.create_task(self._rss_fetcher())
            response = await asyncio.wait_for(
                asyncio.shield(self._rss_task), timeout=self._http_timeout_seconds
            )
            if response.status_code != 200 or self._is_protected(response.html):
                return None, f"RSS HTTP {response.status_code} or protected XML"
            if not re.search(r"<rss(?:\s|>)", response.html, re.I):
                return None, "RSS response was not an RSS document"
            project_ids = set(
                re.findall(
                    r"https://(?:www\.)?freelancehunt\.com/(?:[a-z]{2}/)?"
                    r"(?:project|job)/[^<\s]+?/(\d+)\.html",
                    response.html,
                    re.I,
                )
            )
            if match.group(1) in project_ids:
                return (
                    LiveStatusResult(
                        status=LiveStatus.ACTIVE_BIDDABLE,
                        checked_at=checked_at,
                        evidence="listed in official current open-project RSS",
                        biddable=True,
                    ),
                    "",
                )
            return None, "absent from official current open-project RSS"
        except Exception as exc:
            logger.info(
                "Freelancehunt public RSS check failed: %s", type(exc).__name__
            )
            return None, f"RSS {type(exc).__name__}"

    async def _fetch_playwright(self, url: str) -> _PageResponse:
        from playwright.async_api import async_playwright

        async with self._browser_lock:
            if self._browser_context is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                # No storage_state, cookies or authenticated context is used.
                self._browser_context = await self._browser.new_context(
                    locale="uk-UA",
                    extra_http_headers={"Accept-Language": "uk-UA,uk;q=0.9"},
                )
        page = await self._browser_context.new_page()
        try:
            response = await page.goto(
                url,
                timeout=int(self._playwright_timeout_seconds * 1000),
                wait_until="domcontentloaded",
            )
            # Give enabled public controls a brief bounded chance to render.
            try:
                await page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass
            return _PageResponse(
                response.status if response is not None else 0,
                await page.content(),
            )
        finally:
            await page.close()

    async def _close_resources(self) -> None:
        if self._browser_context is not None:
            await self._browser_context.close()
            self._browser_context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None


def result_fields(result: LiveStatusResult, retry_count: int = 0) -> dict[str, Any]:
    """Map a result to the backward-compatible persisted field names."""

    return {
        "live_status": result.status.value,
        "live_status_checked_at": result.checked_at,
        "live_status_evidence": result.evidence,
        "biddable": result.biddable,
        "live_status_retry_count": retry_count,
        "live_status_last_error": result.last_error,
    }


def _field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def active_status_is_fresh(
    record: Any,
    *,
    seconds: int = ACTION_FRESHNESS_SECONDS,
    now: datetime | None = None,
) -> bool:
    """Only a recent positive live result can expose a proposal."""

    checked_at = _field(record, "live_status_checked_at")
    if (
        _field(record, "live_status") != LiveStatus.ACTIVE_BIDDABLE.value
        or _field(record, "biddable") is not True
        or checked_at is None
    ):
        return False
    if isinstance(checked_at, str):
        try:
            checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - checked_at <= timedelta(seconds=seconds)


async def ensure_current_biddable_status(
    record: Any,
    checker: FreelancehuntLiveStatusChecker,
    persist: Callable[[LiveStatusResult], Awaitable[None]],
    *,
    freshness_seconds: int = ACTION_FRESHNESS_SECONDS,
    force: bool = False,
) -> BiddableStatusGuard:
    """Unified fail-closed guard called before every proposal action.

    The caller must load and detach ``record`` before invoking this function.
    ``persist`` is called only after the network/browser work has completed, so
    callers can open a new, short database transaction for the update.
    """

    platform = str(_field(record, "platform", "") or "").casefold()
    guarded = "freelancehunt" in platform
    if not guarded:
        result = LiveStatusResult(
            status=LiveStatus.ACTIVE_BIDDABLE,
            checked_at=datetime.now(timezone.utc),
            evidence="Live guard not required for this platform.",
            biddable=True,
        )
        return BiddableStatusGuard(True, result, False)

    if not _field(record, "url", ""):
        try:
            stored_status = LiveStatus(str(_field(record, "live_status", "")))
        except ValueError:
            stored_status = LiveStatus.LIVE_STATUS_UNKNOWN
        if stored_status == LiveStatus.ACTIVE_BIDDABLE:
            stored_status = LiveStatus.LIVE_STATUS_UNKNOWN
        result = LiveStatusResult(
            status=stored_status,
            checked_at=datetime.now(timezone.utc),
            evidence=str(
                _field(record, "live_status_evidence", "")
                or "Public project URL is unavailable; live status cannot be verified."
            ),
            biddable=False,
            last_error="missing public project URL",
        )
        return BiddableStatusGuard(False, result, False)

    if not force and active_status_is_fresh(record, seconds=freshness_seconds):
        result = LiveStatusResult(
            status=LiveStatus.ACTIVE_BIDDABLE,
            checked_at=_field(record, "live_status_checked_at"),
            evidence=str(_field(record, "live_status_evidence", "") or "fresh ACTIVE"),
            biddable=True,
            last_error=str(_field(record, "live_status_last_error", "") or ""),
        )
        return BiddableStatusGuard(True, result, False)

    result = await checker.check(str(_field(record, "url", "") or ""))
    await persist(result)
    return BiddableStatusGuard(
        result.status == LiveStatus.ACTIVE_BIDDABLE and result.biddable,
        result,
        True,
    )
