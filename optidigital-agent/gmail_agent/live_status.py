"""Read-only Freelancehunt project bid-eligibility verification.

The checker deliberately fails closed: a project is actionable only when the
live public page contains positive evidence that a bid can be submitted.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from html import unescape
from typing import Any, Awaitable, Callable
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
    """HTTP-first, cookie-free Playwright-fallback live-status checker."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        http_fetcher: Callable[[str], Awaitable[_PageResponse]] | None = None,
        playwright_fetcher: Callable[[str], Awaitable[_PageResponse]] | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._http_fetcher = http_fetcher or self._fetch_http
        self._playwright_fetcher = playwright_fetcher or self._fetch_playwright

    async def check(self, url: str) -> LiveStatusResult:
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
            response = await self._http_fetcher(clean_url)
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

        try:
            response = await self._playwright_fetcher(clean_url)
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

        last_error = f"{http_error}; {browser_error}".strip("; ")
        return LiveStatusResult(
            status=LiveStatus.LIVE_STATUS_UNKNOWN,
            checked_at=checked_at,
            evidence="LIVE STATUS NOT VERIFIED",
            biddable=False,
            last_error=last_error[:500],
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
        async with httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
        return _PageResponse(response.status_code, response.text)

    async def _fetch_playwright(self, url: str) -> _PageResponse:
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                # No storage_state, cookies or authenticated context is used.
                context = await browser.new_context(
                    locale="uk-UA",
                    extra_http_headers={"Accept-Language": "uk-UA,uk;q=0.9"},
                )
                try:
                    page = await context.new_page()
                    response = await page.goto(
                        url,
                        timeout=int(self._timeout_seconds * 1000),
                        wait_until="domcontentloaded",
                    )
                    return _PageResponse(
                        response.status if response is not None else 0,
                        await page.content(),
                    )
                finally:
                    await context.close()
            finally:
                await browser.close()


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
