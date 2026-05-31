import asyncio
import logging
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.freelancehunt.com/v2"
PAGE_SIZE = 25

# Freelancehunt skill IDs for the API filter.
# Full list: GET /skills endpoint (Authorization: Bearer <token>)
# Common dev skills — extend after calling /skills:
#   3=HTML/CSS, 14=JavaScript, 39=Python, 1=PHP, 7=MySQL, 50=Telegram
SKILL_IDS: list[int] = [3, 14, 39, 1, 7, 50]

# Ukrainian keyword filter applied locally on title + description
SKILLS_FILTER: list[str] = [
    "сайт",
    "бот",
    "crm",
    "ai",
    "автоматизація",
    "telegram",
    "розробка",
    "додаток",
    "парсинг",
    "інтеграція",
]


def _build_params(page: int) -> list[tuple[str, Any]]:
    params: list[tuple[str, Any]] = [
        ("page[number]", page),
        ("page[size]", PAGE_SIZE),
    ]
    for skill_id in SKILL_IDS:
        params.append(("filter[skills][]", skill_id))
    return params


def _extract_project(item: dict[str, Any]) -> dict[str, Any]:
    attrs = item.get("attributes", {})
    budget = attrs.get("budget") or {}
    employer = attrs.get("employer") or {}

    # URL может быть в attributes или в links самого item
    url = attrs.get("url") or (item.get("links") or {}).get("self", "")

    return {
        "platform": "Freelancehunt",
        "title": attrs.get("name", ""),
        "description": attrs.get("description") or "",
        "budget_from": budget.get("amount_from"),
        "budget_to": budget.get("amount_to"),
        "currency": budget.get("currency", "UAH"),
        "url": url,
        "employer_name": employer.get("login") or employer.get("full_name") or "",
        "bid_count": attrs.get("bid_count", 0),
        "created_at": attrs.get("created_at", ""),
    }


def _matches_filter(project: dict[str, Any]) -> bool:
    text = f"{project['title']} {project['description']}".lower()
    return any(kw in text for kw in SKILLS_FILTER)


async def get_new_projects() -> list[dict[str, Any]]:
    """Fetch fresh projects from Freelancehunt (pages 1–2), filtered by skills."""
    headers = {
        "Authorization": f"Bearer {settings.FREELANCEHUNT_TOKEN}",
        "Content-Type": "application/json",
    }

    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        base_url=BASE_URL, headers=headers, timeout=30.0
    ) as client:
        for page in range(1, 3):  # pages 1 and 2 only — freshest projects
            await _fetch_page(client, page, results)

    logger.info("Freelancehunt: fetched %d matching projects", len(results))
    return results


async def _fetch_page(
    client: httpx.AsyncClient,
    page: int,
    results: list[dict[str, Any]],
    max_retries: int = 3,
) -> None:
    for attempt in range(max_retries):
        try:
            response = await client.get("/projects", params=_build_params(page))

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(
                    "Rate limited on page %d. Sleeping %ds...", page, retry_after
                )
                await asyncio.sleep(retry_after)
                continue  # retry same page

            response.raise_for_status()
            data = response.json()

            for item in data.get("data", []):
                project = _extract_project(item)
                if _matches_filter(project):
                    results.append(project)

            logger.debug("Page %d: got %d items", page, len(data.get("data", [])))
            return  # success

        except httpx.HTTPStatusError as exc:
            logger.error("HTTP %d on page %d: %s", exc.response.status_code, page, exc)
            return  # don't retry on 4xx/5xx (except 429 handled above)

        except httpx.RequestError as exc:
            logger.warning(
                "Request error page %d (attempt %d/%d): %s",
                page, attempt + 1, max_retries, exc,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(2**attempt)  # 1s, 2s
            else:
                logger.error("Giving up on page %d after %d attempts", page, max_retries)
