import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import json
import logging
import random
import re
import urllib.parse
from datetime import datetime
from typing import Any

import httpx

from parser.base import BasePlatformParser

logger = logging.getLogger(__name__)

BASE_URL = "https://kabanchik.ua"

SEARCH_QUERIES = ["сайт", "бот", "crm", "автоматизація", "розробка"]

API_CANDIDATES: list[str] = [
    f"{BASE_URL}/api/tasks",
    f"{BASE_URL}/api/v1/tasks",
    f"{BASE_URL}/api/v2/tasks",
]

_EXTRACT_JS = """
() => {
    const selectors = [
        '[class*="search-result"]',
        '[class*="task-item"]',
        '[class*="task-card"]',
        '[class*="task"]',
        '[class*="project"]',
        'article',
        '[class*="job-item"]',
        '[class*="job"]',
        '.card',
        '[class*="card"]',
        'li[class*="item"]',
    ];
    let cards = [];
    for (const sel of selectors) {
        const found = Array.from(document.querySelectorAll(sel)).filter(el =>
            el.querySelector('a') !== null && el.textContent.trim().length > 20
        );
        if (found.length > 2) { cards = found; break; }
    }

    return cards.map(el => {
        const titleEl =
            el.querySelector('h2 a') ||
            el.querySelector('h3 a') ||
            el.querySelector('[class*="title"] a') ||
            el.querySelector('[class*="name"] a') ||
            el.querySelector('a[href*="/ua/task"]') ||
            el.querySelector('a[href*="/task"]') ||
            el.querySelector('a');
        const descEl =
            el.querySelector('[class*="description"]') ||
            el.querySelector('[class*="desc"]') ||
            el.querySelector('p');
        const priceEl =
            el.querySelector('[class*="price"]') ||
            el.querySelector('[class*="budget"]') ||
            el.querySelector('[class*="salary"]') ||
            el.querySelector('[class*="cost"]');
        const timeEl = el.querySelector('time') || el.querySelector('[datetime]');
        const authorEl =
            el.querySelector('[class*="author"]') ||
            el.querySelector('[class*="user"]') ||
            el.querySelector('[class*="client"]');

        return {
            title:         titleEl  ? titleEl.textContent.trim()              : '',
            url:           titleEl  ? (titleEl.href || '')                    : '',
            description:   descEl   ? descEl.textContent.trim().slice(0, 300) : '',
            budget:        priceEl  ? priceEl.textContent.trim()              : '',
            created_at:    timeEl   ? (timeEl.getAttribute('datetime') || '') : '',
            employer_name: authorEl ? authorEl.textContent.trim()             : '',
        };
    }).filter(p => p.title.length > 0 && p.url.length > 0);
}
"""


class KabanchikParser(BasePlatformParser):
    PLATFORM = "Kabanchik"

    # ── internal API probe ────────────────────────────────────────────────────

    def _parse_api_response(self, data: Any) -> list[dict[str, Any]]:
        if isinstance(data, dict):
            items = data.get("data", data.get("tasks", data.get("items", [])))
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

                description = item.get("description", item.get("body", ""))[:300]
                url = item.get("url", item.get("link", ""))
                if url and not url.startswith("http"):
                    url = f"{BASE_URL}{url}"

                budget_raw = item.get("budget", item.get("price", item.get("salary", {})))
                if isinstance(budget_raw, dict):
                    budget_from = float(budget_raw.get("from") or budget_raw.get("min") or 0) or None
                    budget_to   = float(budget_raw.get("to")   or budget_raw.get("max") or 0) or None
                elif isinstance(budget_raw, (int, float)):
                    budget_from, budget_to = None, float(budget_raw)
                else:
                    budget_from = budget_to = None

                results.append({
                    "platform":      self.PLATFORM,
                    "title":         title,
                    "description":   description,
                    "budget_from":   budget_from,
                    "budget_to":     budget_to,
                    "currency":      "UAH",
                    "url":           url,
                    "employer_name": "",
                    "bid_count":     int(item.get("bids", item.get("proposals", 0)) or 0),
                    "created_at":    item.get("created_at", datetime.utcnow().isoformat()),
                })
            except Exception:
                self.logger.debug("Failed to parse Kabanchik API item", exc_info=True)

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
                        self.logger.info("Kabanchik API probe %s: status=%d", api_url, resp.status_code)
                        if resp.status_code == 200 and "json" in resp.headers.get("content-type", ""):
                            data = resp.json()
                            items = self._parse_api_response(data)
                            if items:
                                self.logger.info("Kabanchik: API %s returned %d items", api_url, len(items))
                                return items
                    except Exception as exc:
                        self.logger.debug("Kabanchik API %s error: %s", api_url, exc)
        except Exception as exc:
            self.logger.warning("Kabanchik API probe failed: %s", exc)
        return []

    # ── Playwright fallback ───────────────────────────────────────────────────

    def _parse_js_items(self, raw: list[dict]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in raw:
            try:
                budget_from, budget_to = self._parse_budget(item.get("budget", ""))
                results.append({
                    "platform":      self.PLATFORM,
                    "title":         item["title"],
                    "description":   item.get("description", ""),
                    "budget_from":   budget_from,
                    "budget_to":     budget_to,
                    "currency":      "UAH",
                    "url":           item.get("url", ""),
                    "employer_name": item.get("employer_name", ""),
                    "bid_count":     0,
                    "created_at":    item.get("created_at", "") or datetime.utcnow().isoformat(),
                })
            except Exception:
                self.logger.debug("Failed to parse Kabanchik JS item", exc_info=True)
        return results

    async def _playwright_extract(self, page: Any, query: str = "") -> list[dict[str, Any]]:
        prefix = f"[kabanchik/{query}]" if query else "[kabanchik]"

        title = await page.title()
        print(f"{prefix} Title: {title}")

        if "не найдена" in title.lower():
            self.logger.info("%s сторінка не знайдена, пропускаємо", prefix)
            return []

        # Debug: знайти перший елемент з класом task/project/order/job/item/card/result
        all_els = await page.query_selector_all("[class]")
        found_debug = False
        for el in all_els:
            cls = await el.get_attribute("class") or ""
            if any(x in cls.lower() for x in ["task", "project", "order", "job", "item", "card", "result"]):
                print(f"{prefix} Found: {cls}")
                try:
                    print(await el.inner_text())
                except Exception:
                    pass
                print("---")
                found_debug = True
                break
        if not found_debug:
            print(f"{prefix} No task/project/order/job/item/card/result elements found")

        # Спробувати внутрішній API через page.evaluate() (використовує cookies сесії)
        api_js = (
            "async () => {"
            "  const r = await fetch('/api/search?q=QUERY&type=task',"
            "    {headers: {'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest'}});"
            "  return {status: r.status, text: await r.text()};"
            "}"
        ).replace("QUERY", urllib.parse.quote(query or "сайт"))

        try:
            api_result = await page.evaluate(api_js)
            status = api_result.get("status")
            text = api_result.get("text", "")
            print(f"{prefix} API response: status={status}, text={text[:300]}")

            if status == 200:
                try:
                    data = json.loads(text)
                    items = self._parse_api_response(data)
                    if items:
                        self.logger.info("%s API returned %d items", prefix, len(items))
                        return items
                except Exception:
                    pass
        except Exception as exc:
            print(f"{prefix} page.evaluate error: {exc}")

        # Fallback: JS-селектор по DOM
        raw = await page.evaluate(_EXTRACT_JS)
        print(f"{prefix} JS extract found {len(raw)} elements")
        if not raw:
            await self._take_screenshot(page, f"zero_{query}")
            await self._send_alert(f"Playwright знайшов 0 завдань (query={query!r}) — скриншот збережено")
            return []
        return self._parse_js_items(raw)

    # ── entry point ───────────────────────────────────────────────────────────

    async def get_new_projects(self) -> list[dict[str, Any]]:
        print("Kabanchik: temporarily disabled, requires auth")
        return []

        self.logger.info("Kabanchik: starting fetch")

        projects = await self._try_api()

        if not projects:
            self.logger.info("Kabanchik: API not found — running %d search queries in parallel", len(SEARCH_QUERIES))

            async def _fetch_query(q: str) -> list[dict[str, Any]]:
                url = f"{BASE_URL}/ua/search?q={urllib.parse.quote(q)}"
                self.logger.info("Kabanchik: fetching %s", url)
                await asyncio.sleep(random.uniform(0.5, 2.0))
                result = await self._browse(url, lambda page, _q=q: self._playwright_extract(page, _q))
                return result or []

            gathered = await asyncio.gather(
                *[_fetch_query(q) for q in SEARCH_QUERIES],
                return_exceptions=True,
            )

            seen: set[str] = set()
            for res in gathered:
                if isinstance(res, Exception):
                    self.logger.warning("Kabanchik: query error: %s", res)
                    continue
                for p in res:
                    u = p.get("url", "")
                    if u and u not in seen:
                        seen.add(u)
                        projects.append(p)

        matching = [p for p in projects if self._matches_filter(p)]
        self.logger.info("Kabanchik: total=%d matching=%d", len(projects), len(matching))
        return matching


async def get_new_projects() -> list[dict[str, Any]]:
    return await KabanchikParser().get_new_projects()
