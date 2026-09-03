"""Revenue-oriented AI analysis for normalized email events."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from .email_classifier import EmailType

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from gmail_agent.digest_parser import DigestJobCandidate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the internal opportunity analyst for Antonov Digital. Analyze one
normalized Freelancehunt/Gmail event and return JSON only.

Truthful delivery model and evidence:
- Antonov Digital is a two-founder team with developer Vadim responsible for
  the main technical implementation.
- Supported lanes are evaluated without an initial preference: AI agents and
  integrations, automation, Telegram bots, CRM/internal systems, websites,
  web apps/MVPs, ecommerce, data/monitoring, SEO/GEO/local search, AI content,
  image/video workflows, audio/ASR, research, lead generation, SMM/content
  operations and project-management work that the team can realistically do.
- Approved factual cases: Bella Dent (website, lead automation, Telegram bots,
  PostgreSQL, Cloudinary); Dental Supplier AI Agent (AI agent, Telegram,
  supplier comparison/reporting); Gmail Job Agent (Gmail ingestion, AI
  qualification, Telegram, Railway, PostgreSQL); Status Dent and Amidental
  (websites; Status Dent also SEO/local search); Art Studio 184 (website and
  operational automations); Audiobook Cleaner (ASR/cleanup/QA); Mentium
  (education AI product/MVP discovery); NFC Review Cards (NFC workflow).
- Never invent results, metrics, reviews, employees, years, client facts or
  oral Polish fluency. Label an unbuilt example as a demo.

Commercial rules:
- There is no minimum price. Do not reject a project merely for a low budget.
- Pick CASH, REPUTATION or STRATEGIC and explain why.
- Prefer a controlled project or milestone price, realistic delivery time and
  explicit risks. fit_score and win_probability_signal are relative signals,
  not promises.
- Match proposal/reply language to the client: uk, ru, en or pl. Polish is
  written with AI assistance.
- Private messages are HIGH PRIORITY and must not be filtered by job score.
- Do not send bids or platform messages; produce a copy-paste draft for the
  adult account owner.

Return this JSON shape (empty string/null when unavailable):
{
  "is_relevant": true,
  "title": "event or project title",
  "platform": "Freelancehunt",
  "score": 0.0,
  "fit_score": 0.0,
  "reason": "short commercial assessment",
  "budget": "amount and currency or not specified",
  "url": "clean public project/thread URL or empty",
  "urgency": "high|medium|low",
  "why_relevant": "specific capability match",
  "red_flags": [],
  "language": "uk|ru|en|pl",
  "category": "",
  "skills": "comma-separated source skills",
  "deadline": "",
  "bid_count": null,
  "client_name": "",
  "client_profile_url": "",
  "client_context": "safe available client context",
  "project_id": "",
  "thread_id": "",
  "service_lane": "",
  "executable": "yes|maybe|no",
  "win_probability_signal": "low|medium|high plus short rationale",
  "scope_clarity": "low|medium|high plus short rationale",
  "estimated_effort": "honest hours/range",
  "delivery_risk": "",
  "client_payment_risk": "",
  "project_mode": "CASH|REPUTATION|STRATEGIC",
  "project_mode_reason": "",
  "recommended_price": "project or milestone price with currency",
  "realistic_timeline": "",
  "selected_evidence": "one approved relevant case or clearly labelled demo",
  "evidence": "facts in the source that support the assessment",
  "proposal_draft": "one strong copy-paste proposal/reply in client language",
  "needs_context": false,
  "next_action": "exactly one action for the adult owner"
}

For CLIENT_PRIVATE_MESSAGE, use the full safe message, set urgency=high, create
a reply draft, and set needs_context=true when prior conversation is missing.
For status/workspace events, focus on the required owner decision. Security
content is pre-redacted; never reconstruct codes, tokens or sensitive links.
"""


@dataclass
class JobAnalysis:
    # Original Stage 1 fields remain required for constructor compatibility.
    email_id: str
    is_relevant: bool
    title: str
    platform: str
    score: float
    reason: str
    budget: str
    url: str
    urgency: str
    why_relevant: str
    red_flags: list[str] = field(default_factory=list)
    analysis_succeeded: bool = True

    # Stage 2 durable event and commercial decision package.
    event_type: str = EmailType.PROJECT_SINGLE.value
    source_email_id: str = ""
    full_description: str = ""
    description_completeness: str = "PARTIAL"
    language: str = "uk"
    category: str = ""
    skills: str = ""
    deadline: str = ""
    bid_count: int | None = None
    client_name: str = ""
    client_profile_url: str = ""
    client_context: str = ""
    project_id: str = ""
    thread_id: str = ""
    service_lane: str = ""
    executable: str = "maybe"
    fit_score: float | None = None
    win_probability_signal: str = ""
    scope_clarity: str = ""
    estimated_effort: str = ""
    delivery_risk: str = ""
    client_payment_risk: str = ""
    project_mode: str = ""
    project_mode_reason: str = ""
    recommended_price: str = ""
    realistic_timeline: str = ""
    selected_evidence: str = ""
    evidence: str = ""
    proposal_draft: str = ""
    needs_context: bool = False
    next_action: str = ""
    received_at: datetime | None = None
    sensitive_redacted: bool = False
    source_mailbox_alias: str = ""
    live_status: str = ""
    live_status_checked_at: datetime | None = None
    live_status_evidence: str = ""
    biddable: bool | None = None
    live_status_retry_count: int = 0
    live_status_last_error: str = ""
    qualified: bool = False
    tags: str = ""
    budget_currency: str = ""
    discovery_source: str = ""
    discovery_sources: str = ""
    source_publication_at: datetime | None = None
    source_feed_timestamp: datetime | None = None
    feed_fetched_at: datetime | None = None
    first_seen_at: datetime | None = None
    telegram_sent_at: datetime | None = None
    publication_to_telegram_latency_seconds: float | None = None

    @property
    def score_display(self) -> str:
        return f"{self.score:.1f}/10"


def detect_language(text: str) -> str:
    """Conservative deterministic fallback for uk/ru/en/pl."""

    normalized = (text or "").casefold()
    if re.search(r"[іїєґ]", normalized) or any(
        word in normalized for word in ("проєкт", "потрібно", "замовник", "термін")
    ):
        return "uk"
    if re.search(r"[ыэъё]", normalized) or any(
        word in normalized for word in ("проект", "нужно", "заказчик", "срок")
    ):
        return "ru"
    if re.search(r"[ąćęłńóśźż]", normalized) or any(
        word in normalized for word in ("projekt", "potrzebuję", "termin", "zlecenie")
    ):
        return "pl"
    return "en"


def _format_email(
    subject: str,
    sender: str,
    body: str,
    event_type: str,
    source_url: str,
    client_context: str,
) -> str:
    # Keep enough source context for real specifications while bounding API cost.
    trimmed = body[:16000]
    return (
        f"Event type: {event_type}\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Source URL: {source_url or '(not available)'}\n"
        f"Known client context: {client_context or '(not available)'}\n"
        f"Full available safe body:\n{trimmed}"
    )


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(10.0, float(value)))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _executable(value: Any) -> str:
    normalized = str(value or "maybe").strip().casefold()
    if normalized in {"yes", "true", "1"}:
        return "yes"
    if normalized in {"no", "false", "0"}:
        return "no"
    return "maybe"


async def analyze_email(
    email_id: str,
    subject: str,
    sender: str,
    body: str,
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
    *,
    event_type: str = EmailType.PROJECT_SINGLE.value,
    source_url: str = "",
    client_context: str = "",
) -> JobAnalysis:
    if client is None:
        from openai import AsyncOpenAI
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import settings

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    analysis_succeeded = True
    try:
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": _format_email(
                        subject, sender, body, event_type, source_url, client_context
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1600,
        )
        data = _extract_json(response.choices[0].message.content)
    except Exception:
        logger.exception("analyze_email failed for email_id=%s", email_id)
        data = {}
        analysis_succeeded = False

    score = _float(data.get("fit_score", data.get("score", 0.0)))
    language = str(data.get("language") or detect_language(f"{subject}\n{body}"))
    if language not in {"uk", "ru", "en", "pl"}:
        language = detect_language(f"{subject}\n{body}")

    executable = _executable(data.get("executable"))
    is_relevant = bool(data.get("is_relevant", False)) and executable != "no"
    return JobAnalysis(
        email_id=email_id,
        is_relevant=is_relevant,
        title=str(data.get("title") or subject),
        platform=str(data.get("platform") or _detect_platform(sender)),
        score=score,
        reason=str(data.get("reason", "")),
        budget=str(data.get("budget") or "не вказано"),
        url=str(data.get("url") or source_url),
        urgency=str(data.get("urgency") or "medium"),
        why_relevant=str(data.get("why_relevant", "")),
        red_flags=[str(item) for item in (data.get("red_flags") or [])],
        analysis_succeeded=analysis_succeeded,
        event_type=event_type,
        source_email_id=email_id,
        full_description=body,
        description_completeness="FULL" if body.strip() else "PARTIAL",
        language=language,
        category=str(data.get("category", "")),
        skills=str(data.get("skills", "")),
        deadline=str(data.get("deadline", "")),
        bid_count=_optional_int(data.get("bid_count")),
        client_name=str(data.get("client_name", "")),
        client_profile_url=str(data.get("client_profile_url", "")),
        client_context=str(data.get("client_context") or client_context),
        project_id=str(data.get("project_id", "")),
        thread_id=str(data.get("thread_id", "")),
        service_lane=str(data.get("service_lane", "")),
        executable=executable,
        fit_score=score,
        win_probability_signal=str(data.get("win_probability_signal", "")),
        scope_clarity=str(data.get("scope_clarity", "")),
        estimated_effort=str(data.get("estimated_effort", "")),
        delivery_risk=str(data.get("delivery_risk", "")),
        client_payment_risk=str(data.get("client_payment_risk", "")),
        project_mode=str(data.get("project_mode", "")),
        project_mode_reason=str(data.get("project_mode_reason", "")),
        recommended_price=(
            "" if executable == "no" else str(data.get("recommended_price", ""))
        ),
        realistic_timeline=(
            "" if executable == "no" else str(data.get("realistic_timeline", ""))
        ),
        selected_evidence=str(data.get("selected_evidence", "")),
        evidence=str(data.get("evidence", "")),
        proposal_draft=(
            "" if executable == "no" else str(data.get("proposal_draft", ""))
        ),
        needs_context=bool(data.get("needs_context", False)),
        next_action=(
            "Не подавати ставку: виконання не підтверджене."
            if executable == "no"
            else str(data.get("next_action", ""))
        ),
    )


async def analyze_candidate(
    candidate: "DigestJobCandidate",
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> JobAnalysis:
    """Analyze one deterministic digest child, never the whole digest HTML."""

    body_lines = [f"Description: {candidate.description}"]
    if candidate.budget:
        body_lines.append(f"Budget: {candidate.budget}")
    if candidate.category:
        body_lines.append(f"Category: {candidate.category}")
    if candidate.url:
        body_lines.append(f"URL: {candidate.url}")

    analysis = await analyze_email(
        email_id=candidate.stable_key,
        subject=candidate.title,
        sender=candidate.platform,
        body="\n".join(body_lines),
        client=client,
        model=model,
        event_type=candidate.event_type,
        source_url=candidate.url,
    )
    analysis.platform = candidate.platform
    analysis.url = candidate.url
    analysis.source_email_id = candidate.source_email_id
    analysis.full_description = candidate.description
    analysis.description_completeness = candidate.description_completeness
    analysis.category = analysis.category or candidate.category
    analysis.deadline = analysis.deadline or candidate.deadline
    analysis.bid_count = (
        analysis.bid_count if analysis.bid_count is not None else candidate.bid_count
    )
    analysis.client_name = analysis.client_name or candidate.client_name
    analysis.client_profile_url = (
        analysis.client_profile_url or candidate.client_profile_url
    )
    analysis.project_id = analysis.project_id or candidate.project_id
    analysis.received_at = candidate.received_at
    analysis.tags = candidate.tags
    analysis.budget_currency = candidate.budget_currency
    analysis.discovery_source = candidate.discovery_source
    analysis.discovery_sources = candidate.discovery_source
    analysis.source_publication_at = candidate.source_publication_at
    analysis.source_feed_timestamp = candidate.source_feed_timestamp
    analysis.feed_fetched_at = candidate.feed_fetched_at
    analysis.first_seen_at = candidate.first_seen_at
    if not analysis.title:
        analysis.title = candidate.title
    if (not analysis.budget or analysis.budget == "не вказано") and candidate.budget:
        analysis.budget = candidate.budget
    return analysis


def _detect_platform(sender: str) -> str:
    normalized = sender.casefold()
    if "freelancehunt" in normalized:
        return "Freelancehunt"
    if "work.ua" in normalized:
        return "Work.ua"
    if "robota.ua" in normalized:
        return "Robota.ua"
    if "upwork" in normalized:
        return "Upwork"
    return "Unknown"
