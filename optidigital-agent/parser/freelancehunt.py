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

BASE_URL = "https://freelancehunt.com"
JSON_URL = f"{BASE_URL}/projects.json"
HTML_URL = f"{BASE_URL}/projects"

_EXTRACT_JS = """
() => {
    const selectors = [
        'article.project',
        '.project-card',
        'tr.project',
        '[class*="project-item"]',
        '[class*="project-card"]',
        'div[data-id]',
        '[class*="project"]',
    ];
    let cards = [];
    for (const sel of selectors) {
        const found = Array.from(document.querySelectorAll(sel)).filter(el =>
            el.querySelector('a') !== null && el.textContent.trim().length > 10
        );
        if (found.length > 0) { cards = found; break; }
    }

    return cards.map(el => {
        const titleEl =
            el.querySelector('a[href*="/project/"]') ||
            el.querySelector('h2 a') ||
            el.querySelector('h3 a') ||
            el.querySelector('a');
        const descEl =
            el.querySelector('[class*="description"]') ||
            el.querySelector('[class*="desc"]') ||
            el.querySelector('p');
        const budgetEl =
            el.querySelector('[class*="budget"]') ||
            el.querySelector('[class*="price"]') ||
            el.querySelector('[class*="cost"]');
        const bidsEl =
            el.querySelector('[class*="bid"]') ||
            el.querySelector('[class*="proposal"]') ||
            el.querySelector('[class*="offer"]');
        const timeEl = el.querySelector('time') || el.querySelector('[datetime]');
        const skillEls = Array.from(
            el.querySelectorAll('[class*="skill"], [class*="tag"], [class*="label"]')
        );

        return {
            title:       titleEl  ? titleEl.textContent.trim()                     : '',
            url:         titleEl  ? (titleEl.href || '')                           : '',
            description: descEl   ? descEl.textContent.trim().slice(0, 300)        : '',
            budget:      budgetEl ? budgetEl.textContent.trim()                    : '',
            bid_count:   bidsEl   ? bidsEl.textContent.trim()                     : '0',
            created_at:  timeEl   ? (timeEl.getAttribute('datetime') || '')        : '',
            skills:      skillEls.map(s => s.textContent.trim()).filter(Boolean).join(', '),
        };
    }).filter(p => p.title.length > 0 && p.url.length > 0);
}
"""


class FreelancehuntParser(BasePlatformParser):
    PLATFORM = "Freelancehunt"

    # ── JSON API ──────────────────────────────────────────────────────────────

    def _parse_json_response(self, data: dict | list) -> list[dict[str, Any]]:
        items: list = data.get("data", data) if isinstance(data, dict) else data
        results: list[dict[str, Any]] = []

        for item in items:
            try:
                attrs = item.get("attributes", item)
                title = attrs.get("name", attrs.get("title", ""))
                if not title:
                    continue

                description = attrs.get("description", "")[:2000]

                budget = attrs.get("budget", {})
                if isinstance(budget, dict):
                    budget_from = float(budget.get("from") or budget.get("min") or 0) or None
                    budget_to   = float(budget.get("to")   or budget.get("max") or 0) or None
                    currency    = budget.get("currency", "UAH")
                else:
                    budget_from = budget_to = None
                    currency = "UAH"

                links = item.get("links", {})
                url = links.get("self", attrs.get("url", ""))
                if url and not url.startswith("http"):
                    url = f"{BASE_URL}{url}"

                employer = attrs.get("employer", {})
                employer_name = ""
                employer_url = ""
                employer_login = ""
                if isinstance(employer, dict):
                    employer_login = employer.get("login", "")
                    employer_name = employer.get("first_name", "") or employer_login
                    emp_links = employer.get("links", {})
                    if isinstance(emp_links, dict):
                        employer_url = emp_links.get("self", "")
                    if not employer_url and employer_login:
                        employer_url = f"{BASE_URL}/freelancer/{employer_login}"

                bid_count = int(
                    attrs.get("bid_count") or attrs.get("offers_count") or 0
                )
                created_at = attrs.get("created_at", datetime.utcnow().isoformat())

                # Category from skills list
                skills = attrs.get("skills", [])
                if isinstance(skills, list) and skills:
                    category = ", ".join(
                        s.get("name", str(s)) if isinstance(s, dict) else str(s)
                        for s in skills[:5]
                    )
                else:
                    category = attrs.get("category", {})
                    if isinstance(category, dict):
                        category = category.get("name", "")
                    elif not isinstance(category, str):
                        category = ""

                deadline = attrs.get("expired_at") or attrs.get("deadline") or ""

                results.append({
                    "platform":          self.PLATFORM,
                    "title":             title,
                    "description":       description,
                    "budget_from":       budget_from,
                    "budget_to":         budget_to,
                    "currency":          currency,
                    "url":               url,
                    "employer_name":     employer_name,
                    "employer_url":      employer_url,
                    "category":          category,
                    "deadline":          deadline,
                    "bid_count":         bid_count,
                    "created_at":        created_at,
                    "employer_phone":    None,
                    "employer_telegram": None,
                    "employer_email":    None,
                })
            except Exception:
                self.logger.debug("Failed to parse JSON item", exc_info=True)

        return results

    async def _try_json_api(self) -> list[dict[str, Any]]:
        try:
            headers = {
                "User-Agent": self._random_ua(),
                "Accept": "application/json",
                "Accept-Language": "uk-UA,uk;q=0.9",
            }
            async with httpx.AsyncClient(headers=headers, timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(JSON_URL)
                self.logger.info("FreelanceHunt JSON API: status=%d", resp.status_code)
                if resp.status_code == 200:
                    data = resp.json()
                    projects = self._parse_json_response(data)
                    self.logger.info(
                        "FreelanceHunt JSON API: parsed %d projects", len(projects)
                    )
                    return projects
        except Exception as exc:
            self.logger.warning("FreelanceHunt JSON API failed: %s", exc)
        return []

    # ── Playwright fallback ───────────────────────────────────────────────────

    def _parse_js_items(self, raw: list[dict]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in raw:
            try:
                budget_from, budget_to = self._parse_budget(item.get("budget", ""))
                bid_count = int(re.sub(r"\D", "", item.get("bid_count", "0") or "0") or 0)
                results.append({
                    "platform":          self.PLATFORM,
                    "title":             item["title"],
                    "description":       item.get("description", ""),
                    "budget_from":       budget_from,
                    "budget_to":         budget_to,
                    "currency":          "UAH",
                    "url":               item.get("url", ""),
                    "employer_name":     "",
                    "employer_url":      "",
                    "category":          "",
                    "deadline":          "",
                    "bid_count":         bid_count,
                    "created_at":        item.get("created_at", "") or datetime.utcnow().isoformat(),
                    "employer_phone":    None,
                    "employer_telegram": None,
                    "employer_email":    None,
                })
            except Exception:
                self.logger.debug("Failed to parse JS item", exc_info=True)
        return results

    async def _playwright_extract(self, page: Any) -> list[dict[str, Any]]:
        rows = await page.query_selector_all("tr")
        print(f"[DEBUG] Total <tr> rows: {len(rows)}")
        for i, row in enumerate(rows[:5]):
            print(f"Row {i}: {await row.inner_text()}")

        results: list[dict[str, Any]] = []
        for row in rows:
            link = await row.query_selector("a[href*='/project/']")
            if not link:
                continue

            href = await link.get_attribute("href") or ""
            title = (await link.inner_text()).strip()
            if not title or not href:
                continue

            url = href if href.startswith("http") else f"{BASE_URL}{href}"

            # Budget: collect all td text after the title cell
            cells = await row.query_selector_all("td")
            budget_text = ""
            for cell in cells:
                cell_link = await cell.query_selector("a[href*='/project/']")
                if cell_link:
                    continue
                text = (await cell.inner_text()).strip()
                if text:
                    budget_text = text
                    break

            budget_from, budget_to = self._parse_budget(budget_text)
            results.append({
                "platform":          self.PLATFORM,
                "title":             title,
                "description":       "",
                "budget_from":       budget_from,
                "budget_to":         budget_to,
                "currency":          "UAH",
                "url":               url,
                "employer_name":     "",
                "employer_url":      "",
                "category":          "",
                "deadline":          "",
                "bid_count":         0,
                "created_at":        datetime.utcnow().isoformat(),
                "employer_phone":    None,
                "employer_telegram": None,
                "employer_email":    None,
            })

        self.logger.info("FreelanceHunt Playwright: found %d projects from <tr> rows", len(results))

        if not results:
            await self._take_screenshot(page, "zero_results")
            await self._send_alert(
                "Playwright знайшов 0 проєктів на freelancehunt.com — скриншот збережено"
            )
        return results

    # ── entry point ───────────────────────────────────────────────────────────

    async def get_new_projects(self) -> list[dict[str, Any]]:
        self.logger.info("FreelanceHunt: starting fetch")

        projects = await self._try_json_api()

        if not projects:
            self.logger.info("FreelanceHunt: JSON API empty — falling back to Playwright")
            await asyncio.sleep(random.uniform(1.5, 3.0))
            projects = await self._browse(HTML_URL, self._playwright_extract) or []

        matching = [p for p in projects if self._matches_filter(p)]
        self.logger.info(
            "FreelanceHunt: total=%d matching=%d", len(projects), len(matching)
        )
        return matching


async def get_new_projects() -> list[dict[str, Any]]:
    return await FreelancehuntParser().get_new_projects()
