import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
import random
import re
from datetime import datetime
from typing import Any

import httpx

from parser.base import BasePlatformParser

logger = logging.getLogger(__name__)

BASE_URL_UA = "https://free-lance.ua"
HTML_URL_UA = f"{BASE_URL_UA}/projects/"

API_CANDIDATES: list[str] = [
    f"{BASE_URL_UA}/api/projects",
    f"{BASE_URL_UA}/api/v1/projects",
]

_EXTRACT_JS = """
() => {
    const selectors = [
        'div.project-item',
        'li.b-post',
        '[class*="project-item"]',
        '[class*="project-card"]',
        'tr[class*="project"]',
        '[class*="project"]',
        'article',
    ];
    let cards = [];
    for (const sel of selectors) {
        const found = Array.from(document.querySelectorAll(sel)).filter(el =>
            el.querySelector('a') !== null && el.textContent.trim().length > 15
        );
        if (found.length > 2) { cards = found; break; }
    }

    return cards.map(el => {
        const titleEl =
            el.querySelector('a[href*="/project"]') ||
            el.querySelector('h2 a') ||
            el.querySelector('h3 a') ||
            el.querySelector('[class*="title"] a') ||
            el.querySelector('a');

        // employer/customer profile link — only user pages
        const employerLinkEl =
            el.querySelector('a[href*="/users/"]') ||
            el.querySelector('a[href*="/user/"]');

        const descEl =
            el.querySelector('[class*="description"]') ||
            el.querySelector('[class*="desc"]') ||
            el.querySelector('p');
        const priceEl =
            el.querySelector('[class*="price"]') ||
            el.querySelector('[class*="budget"]') ||
            el.querySelector('[class*="cost"]');
        const timeEl = el.querySelector('time') || el.querySelector('[datetime]');
        const bidsEl =
            el.querySelector('[class*="bid"]') ||
            el.querySelector('[class*="offer"]') ||
            el.querySelector('[class*="proposal"]');

        return {
            title:        titleEl        ? titleEl.textContent.trim()              : '',
            url:          titleEl        ? (titleEl.href || '')                    : '',
            employer_url: employerLinkEl ? (employerLinkEl.href || '')             : '',
            description:  descEl        ? descEl.textContent.trim().slice(0, 300) : '',
            budget:       priceEl       ? priceEl.textContent.trim()              : '',
            bid_count:    bidsEl        ? bidsEl.textContent.trim()               : '0',
            created_at:   timeEl        ? (timeEl.getAttribute('datetime') || '') : '',
        };
    }).filter(p => p.title.length > 0 && p.url.length > 0);
}
"""


class FreelanceUaParser(BasePlatformParser):
    PLATFORM = "FreelanceUA"

    # ── API probe ─────────────────────────────────────────────────────────────

    def _parse_api_response(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            items = data.get("data", data.get("projects", data.get("items", [])))
        elif isinstance(data, list):
            items = data
        else:
            return []

        results: list[dict[str, Any]] = []
        for item in items:
            try:
                if not isinstance(item, dict):
                    continue
                title = item.get("title", item.get("name", ""))
                if not title:
                    continue

                description = item.get("description", item.get("body", ""))[:2000]
                url = item.get("url", item.get("link", ""))
                if url and not url.startswith("http"):
                    url = f"{BASE_URL_UA}{url}"

                budget_raw = item.get("budget", item.get("price", {}))
                if isinstance(budget_raw, dict):
                    budget_from = float(budget_raw.get("from") or 0) or None
                    budget_to   = float(budget_raw.get("to")   or 0) or None
                elif isinstance(budget_raw, (int, float)):
                    budget_from, budget_to = None, float(budget_raw)
                else:
                    budget_from = budget_to = None

                category_raw = item.get("category", item.get("tags", ""))
                if isinstance(category_raw, list):
                    category = ", ".join(str(c) for c in category_raw[:5])
                elif isinstance(category_raw, dict):
                    category = category_raw.get("name", "")
                else:
                    category = str(category_raw) if category_raw else ""

                results.append({
                    "platform":          self.PLATFORM,
                    "title":             title,
                    "description":       description,
                    "budget_from":       budget_from,
                    "budget_to":         budget_to,
                    "currency":          "UAH",
                    "url":               url,
                    "employer_name":     "",
                    "employer_url":      "",
                    "category":          category,
                    "deadline":          item.get("deadline", item.get("expired_at", "")),
                    "bid_count":         int(item.get("bids", item.get("proposals", 0)) or 0),
                    "created_at":        item.get("created_at", datetime.utcnow().isoformat()),
                    "employer_phone":    None,
                    "employer_telegram": None,
                    "employer_email":    None,
                })
            except Exception:
                self.logger.debug("Failed to parse FreelanceUA API item", exc_info=True)

        return results

    async def _try_api(self) -> list[dict[str, Any]]:
        headers = {
            "User-Agent": self._random_ua(),
            "Accept": "application/json",
            "Accept-Language": "uk-UA,uk;q=0.9",
        }
        try:
            async with httpx.AsyncClient(headers=headers, timeout=15.0, follow_redirects=True) as client:
                for api_url in API_CANDIDATES:
                    try:
                        resp = await client.get(api_url)
                        self.logger.info(
                            "FreelanceUA API probe %s: status=%d", api_url, resp.status_code
                        )
                        if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                            data = resp.json()
                            items = self._parse_api_response(data)
                            if items:
                                self.logger.info(
                                    "FreelanceUA: API %s returned %d items", api_url, len(items)
                                )
                                return items
                    except Exception as exc:
                        self.logger.debug("FreelanceUA API %s error: %s", api_url, exc)
        except Exception as exc:
            self.logger.warning("FreelanceUA API probe failed: %s", exc)
        return []

    # ── Playwright fallback ───────────────────────────────────────────────────

    def _parse_js_items(self, raw: list[dict]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in raw:
            try:
                budget_from, budget_to = self._parse_budget(item.get("budget", ""))
                bid_count = int(re.sub(r"\D", "", item.get("bid_count", "0") or "0") or 0)

                url = item.get("url", "")
                employer_url = item.get("employer_url", "")

                # Validate project URL: must contain /project/ or /projects/
                if url and not re.search(r"/projects?/", url):
                    self.logger.debug(
                        "project_url_missing: url=%r rejected (no /project(s)/ path), title=%r",
                        url, item.get("title", ""),
                    )
                    # Salvage as employer_url only if it looks like a user profile
                    if not employer_url and re.search(r"/users?/", url):
                        employer_url = url
                    url = ""

                if not url:
                    self.logger.debug(
                        "project_url_missing: title=%r", item.get("title", "")
                    )

                # Validate employer URL: must contain /user/ or /users/
                if employer_url and not re.search(r"/users?/", employer_url):
                    employer_url = ""

                results.append({
                    "platform":          self.PLATFORM,
                    "title":             item["title"],
                    "description":       item.get("description", ""),
                    "budget_from":       budget_from,
                    "budget_to":         budget_to,
                    "currency":          "UAH",
                    "url":               url,
                    "employer_name":     "",
                    "employer_url":      employer_url,
                    "category":          "",
                    "deadline":          "",
                    "bid_count":         bid_count,
                    "created_at":        item.get("created_at", "") or datetime.utcnow().isoformat(),
                    "employer_phone":    None,
                    "employer_telegram": None,
                    "employer_email":    None,
                })
            except Exception:
                self.logger.debug("Failed to parse FreelanceUA JS item", exc_info=True)
        return results

    async def _playwright_extract(self, page: Any) -> list[dict[str, Any]]:
        raw = await page.evaluate(_EXTRACT_JS)
        self.logger.info("FreelanceUA Playwright: evaluate() found %d elements", len(raw))
        if not raw:
            page_title = await page.title()
            page_url = page.url
            html = await page.content()
            self.logger.warning("=== FreelanceUA: 0 projects found ===")
            self.logger.warning("Page title: %s", page_title)
            self.logger.warning("Page URL: %s", page_url)
            self.logger.warning("HTML (first 2000 chars):\n%s", html[:2000])

            debug_selectors = [
                "div.project-item", "li.b-post", '[class*="project-item"]',
                '[class*="project-card"]', 'tr[class*="project"]',
                '[class*="project"]', "article",
            ]
            sel_counts: list[str] = []
            for sel in debug_selectors:
                try:
                    cnt = await page.evaluate(
                        "(sel) => document.querySelectorAll(sel).length", sel
                    )
                    self.logger.warning("Selector %r → %d elements", sel, cnt)
                    sel_counts.append(f"{sel}: {cnt}")
                except Exception:
                    pass

            screenshot_path = await self._take_screenshot(page, "zero_results")
            debug_msg = (
                f"🔴 0 проєктів на free-lance.ua\n"
                f"URL: {page_url}\n"
                f"Title: {page_title}\n"
                f"Selectors:\n" + "\n".join(sel_counts) + "\n\n"
                f"HTML (перші 500 симв.):\n{html[:500]}"
            )
            await self._send_alert(debug_msg)
            await self._send_screenshot_to_telegram(screenshot_path)
            return []
        return self._parse_js_items(raw)

    # ── entry point ───────────────────────────────────────────────────────────

    async def get_new_projects(self) -> list[dict[str, Any]]:
        self.logger.info("FreelanceUA: starting fetch")

        projects = await self._try_api()

        if not projects:
            self.logger.info("FreelanceUA: API empty — trying %s", HTML_URL_UA)
            await asyncio.sleep(random.uniform(1.5, 3.0))
            projects = await self._browse(HTML_URL_UA, self._playwright_extract) or []

        projects = await self._enrich_descriptions(projects)
        matching = [p for p in projects if self._matches_filter(p)]
        self.logger.info(
            "FreelanceUA: total=%d matching=%d", len(projects), len(matching)
        )
        return matching

    async def get_new_projects_debug(self) -> dict[str, Any]:
        self.logger.info("FreelanceUA: starting debug fetch")

        projects = await self._try_api()

        if not projects:
            self.logger.info("FreelanceUA: API empty — trying %s", HTML_URL_UA)
            await asyncio.sleep(random.uniform(1.5, 3.0))
            projects = await self._browse(HTML_URL_UA, self._playwright_extract) or []

        projects = await self._enrich_descriptions(projects)
        matched, rejected = self._debug_split(projects)
        self.logger.info(
            "FreelanceUA debug: total=%d matched=%d rejected=%d",
            len(projects), len(matched), len(rejected),
        )
        return {
            "platform": self.PLATFORM,
            "total": len(projects),
            "matched": matched,
            "rejected": rejected,
        }


async def get_new_projects() -> list[dict[str, Any]]:
    return await FreelanceUaParser().get_new_projects()


async def get_debug_info() -> dict[str, Any]:
    return await FreelanceUaParser().get_new_projects_debug()
