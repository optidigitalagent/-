"""Revenue-oriented AI analysis for normalized email events."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .email_classifier import EmailType
from .quality_gate import (
    ANALYSIS_VERSION,
    SCORE_FAILED,
    normalize_score_metadata,
    score_display,
)

if TYPE_CHECKING:
    from gmail_agent.digest_parser import DigestJobCandidate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the internal opportunity analyst for Antonov Digital. Analyze one
normalized Freelancehunt/Gmail event and return JSON only.

Truthful delivery model and evidence:
- Antonov Digital is a two-founder team with developer Vadim responsible for
  the main technical implementation.
- Candidate service lanes (NOT proof of past work or current capacity) are
  evaluated without an initial preference: AI agents and
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
- Select exactly one evidence_case_id from: BELLA_DENT,
  DENTAL_SUPPLIER_AI_AGENT, GMAIL_JOB_AGENT, STATUS_DENT, AMIDENTAL,
  ART_STUDIO_184, AUDIOBOOK_CLEANER, MENTIUM, NFC_REVIEW_CARDS,
  NO_DIRECT_CASE, DEMO_REQUIRED. selected_evidence is advisory only; the
  application replaces it with the approved registry wording.
- Never invent results, metrics, reviews, employees, years, client facts or
  oral Polish fluency. Label an unbuilt example as a demo.

Commercial rules:
- There is no minimum price. Do not reject a project merely for a low budget.
- commercial_decision is TAKE only when a complete, truthful proposal can be
  produced now; ASK only when exactly one missing source fact blocks it; SKIP
  only for a source-grounded mismatch or non-executable requirement. Provider
  or schema failures are never commercial SKIP decisions.
- Pick CASH, REPUTATION or STRATEGIC and explain why.
- Return two distinct finite numbers: fit_score is delivery-capability match;
  score is overall commercial opportunity considering fit, scope, budget,
  competition, risk, response speed and CASH/REPUTATION/STRATEGIC value.
  Prefer a controlled project or milestone price, realistic delivery time and
  explicit risks. Scores and win_probability_signal are relative signals, not
  promises. Never fill a missing value with a manufactured score.
- TAKE: state deliverables, quantities, boundaries and acceptance checks. Derive
  the quote from scope, estimated effort and risks; justify it briefly in reason.
  No invented team hourly rate, price floor or copied example amount. Missing
  client budget does not prevent our own scoped quote. Use source currency when
  specified; otherwise select UAH/USD/EUR/PLN and explain that choice in reason.
  recommended_price syntax: amount or amount-range, currency, optionally
  'as one milestone' / 'as two milestones' / 'as three milestones'.
  realistic_timeline syntax: duration or duration-range plus hours/days/weeks/months.
  Values must fit effort and conservative capacity; rationale belongs in reason,
  not these canonical fields. State materials needed to START in delivery_risk.
- ASK: ask_basis identifies the missing_fact, its owner CLIENT or TEAM, fact_kind,
  exact source_quote or explicit absence_reason, required_for_estimate and
  estimate_impact. decision_reason summarizes that grounded dependency.
  next_action is an imperative concrete ACTION addressed to that owner, not a name.
  clarification_question contains ONE concrete question in the client language.
  recommended_price, realistic_timeline and proposal_draft must be empty strings.
  Client budget is source metadata, never our offer. Do not ask for known facts.
  Missing execution assets are not automatically missing requirements. A prior
  manual scope assessment is evidence, not certainty; explain any disagreement.
  CLIENT_REQUIREMENT is an unknown requirement the client can supply; TEAM_FACT
  belongs to the team. EXECUTOR_PREFERENCE (e.g. preferred executor portfolio)
  is not a mandatory client gap. Consult approved evidence first, never ask the
  client for our examples. NO_DIRECT_CASE does not mean inability or force ASK.
  EXECUTION_INPUT assets needed only to start do not block estimation. Ask only
  if a specific missing requirement changes scope, effort, price or feasibility.
  A genuinely mandatory client reference may justify ASK; optional style browsing
  does not. Never ask for already stated quantities or requirements. Do not offer
  a free sample. 'Will send privately' states a channel, not 'after selection'.
- SKIP: source-grounded non-executability reason, no price/timeline/proposal or
  question. Small budget and NO_DIRECT_CASE alone are not SKIP reasons.
- Score and Fit are independent assessed numbers (or null if genuinely unknown).
  Never use zero as an ASK or historical-source placeholder. Genuine assessed
  zeros remain zeros. Never change a score merely to pass a readiness check.
- Evidence must quote/paraphrase specific source requirements, not assert that
  'we possess' skills or experience. Approved past-work claims appear only in
  application-owned evidence. The model body may describe a truthful FUTURE
  execution approach, never unapproved past capability or experience.
- Match proposal/reply language to the client: uk, ru, en or pl. Polish is
  written with AI assistance.
- Private messages are HIGH PRIORITY and must not be filtered by job score.
- Do not send bids or platform messages; produce a copy-paste draft for the
  adult account owner.
- Do not include any URL, domain, email, phone, handle, social network,
  messenger or off-platform call to action in model-authored fields.

The strict schema supplies one root 'analysis' object with the TAKE/ASK/SKIP
contract. Return every schema field; use empty string/null for unavailable metadata.
title/platform/url/project_id/thread_id identify only the supplied source.
budget/deadline/bid_count/client_name/client_profile_url/client_context retain
only known source facts. Source URL fields may contain the supplied public URL;
never add links to the proposal or other model-authored commercial text.
reason and why_relevant describe required operations and a future execution
approach, NOT newly authored claims of our expertise or experience. Past-work
statements come exclusively from application-owned approved registry wording.
skills lists source skills, not an invented team CV.
scope_clarity describes known boundaries and genuine gaps; estimated_effort is
an honest hours/range estimate. delivery_risk and client_payment_risk must name
risks/unknowns and proposed safeguards, not invent client history.
TAKE proposal_draft is a personalized future delivery approach in client language.
No past case/experience, price, currency, milestone or timeline in the model body:
the application appends exact approved evidence, commercial and start clauses.
ASK/SKIP proposal_draft is empty. needs_context is true only for ASK.
No directly matching case is acceptable; do not claim a past visual-content case
merely because image/video workflows are a supported service lane.

For CLIENT_PRIVATE_MESSAGE, use the full safe message, set urgency=high, create
a reply draft, and set needs_context=true when prior conversation is missing.
For status/workspace events, focus on the required owner decision. Security
content is pre-redacted; never reconstruct codes, tokens or sensitive links.
"""

MAX_MODEL_OUTPUT_TOKENS = 1600
COMMERCIAL_DECISIONS = frozenset({"TAKE", "ASK", "SKIP"})


class AskBasis(BaseModel):
    """One estimate-blocking dependency, not a general requirements ontology."""
    model_config = ConfigDict(extra="forbid", strict=True)
    missing_fact: str = Field(pattern=r"\S", description="The missing fact in the same language and concrete terms as clarification_question.")
    owner: Literal["CLIENT", "TEAM"]
    fact_kind: Literal["CLIENT_REQUIREMENT", "TEAM_FACT", "EXECUTOR_PREFERENCE", "EXECUTION_INPUT"]
    source_quote: str
    absence_reason: str
    required_for_estimate: bool
    estimate_impact: str = Field(pattern=r"\S")


class OpportunityAnalysisOutput(BaseModel):
    """Flat persisted/legacy shape; wire uses decision-specific variants below."""

    model_config = ConfigDict(extra="forbid", strict=True)

    is_relevant: bool = False
    commercial_decision: Literal["TAKE", "ASK", "SKIP"] = "TAKE"
    decision_reason: str = ""
    clarification_question: str = ""
    ask_basis: AskBasis | None = None
    title: str = ""
    platform: str = ""
    score: float | None = None
    fit_score: float | None = None
    reason: str = Field(default="", description="Source-grounded assessment; for TAKE justify chosen quote, currency, effort and conservative timeline without inventing team rates.")
    budget: str = Field(default="", description="Client source budget only; empty if absent. Never our offer price.")
    url: str = ""
    urgency: Literal["high", "medium", "low"] = "medium"
    why_relevant: str = ""
    red_flags: list[str] = []
    language: Literal["uk", "ru", "en", "pl"] = "en"
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
    executable: Literal["yes", "maybe", "no"] = "maybe"
    win_probability_signal: str = ""
    scope_clarity: str = ""
    estimated_effort: str = ""
    delivery_risk: str = ""
    client_payment_risk: str = ""
    project_mode: Literal["CASH", "REPUTATION", "STRATEGIC"] = "CASH"
    project_mode_reason: str = ""
    recommended_price: str = ""
    realistic_timeline: str = ""
    selected_evidence: str = ""
    evidence_case_id: Literal[
        "BELLA_DENT",
        "DENTAL_SUPPLIER_AI_AGENT",
        "GMAIL_JOB_AGENT",
        "STATUS_DENT",
        "AMIDENTAL",
        "ART_STUDIO_184",
        "AUDIOBOOK_CLEANER",
        "MENTIUM",
        "NFC_REVIEW_CARDS",
        "NO_DIRECT_CASE",
        "DEMO_REQUIRED",
    ] = "NO_DIRECT_CASE"
    evidence: str = ""
    proposal_draft: str = ""
    needs_context: bool = False
    next_action: str = Field(default="", description="One concrete imperative action addressed to the ask_basis owner; never a recipient-only label.")


class TakeOutput(OpportunityAnalysisOutput):
    commercial_decision: Literal["TAKE"]
    executable: Literal["yes"]
    clarification_question: Literal[""]
    needs_context: Literal[False]
    score: float = Field(ge=0, le=10)
    fit_score: float = Field(ge=0, le=10)
    recommended_price: str = Field(pattern=r"\S")
    realistic_timeline: str = Field(pattern=r"\S")
    proposal_draft: str = Field(pattern=r"\S")
    ask_basis: None = None


class AskOutput(OpportunityAnalysisOutput):
    commercial_decision: Literal["ASK"]
    executable: Literal["maybe"]
    recommended_price: Literal[""]
    realistic_timeline: Literal[""]
    proposal_draft: Literal[""]
    needs_context: Literal[True]
    ask_basis: AskBasis
    next_action: str = Field(pattern=r"\S")
    clarification_question: str = Field(pattern=r"\S")


class SkipOutput(OpportunityAnalysisOutput):
    commercial_decision: Literal["SKIP"]
    executable: Literal["no"]
    recommended_price: Literal[""]
    realistic_timeline: Literal[""]
    proposal_draft: Literal[""]
    clarification_question: Literal[""]
    needs_context: Literal[False]
    ask_basis: None = None


class OpportunityWireOutput(BaseModel):
    """Supported nested anyOf, not root anyOf or unsupported if/then/oneOf."""
    model_config = ConfigDict(extra="forbid", strict=True)
    analysis: TakeOutput | AskOutput | SkipOutput


def _strict_output_schema() -> dict[str, Any]:
    """Return an all-fields-required schema accepted by Structured Outputs."""

    schema = OpportunityWireOutput.model_json_schema()

    def harden(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["required"] = list(properties)
                node["additionalProperties"] = False
            node.pop("default", None)
            if "const" in node:
                node["enum"] = [node.pop("const")]
            for value in node.values():
                harden(value)
        elif isinstance(node, list):
            for value in node:
                harden(value)

    harden(schema)
    return schema


STRICT_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "antonov_opportunity_analysis",
        "strict": True,
        "schema": _strict_output_schema(),
    },
}


@dataclass
class JobAnalysis:
    # Original Stage 1 fields remain required for constructor compatibility.
    email_id: str
    is_relevant: bool
    title: str
    platform: str
    score: float | None
    reason: str
    budget: str
    url: str
    urgency: str
    why_relevant: str
    red_flags: list[str] = field(default_factory=list)
    analysis_succeeded: bool = True
    commercial_decision: str = ""
    decision_reason: str = ""
    clarification_question: str = ""
    budget_provenance: str = "MODEL"
    provider_outcome: str = ""
    provider_model: str = ""
    provider_finish_reason: str = ""
    provider_prompt_tokens: int = 0
    provider_completion_tokens: int = 0
    provider_total_tokens: int = 0
    provider_error_code: str = ""

    # Stage 2 durable event and commercial decision package.
    event_type: str = EmailType.PROJECT_SINGLE.value
    source_email_id: str = ""
    full_description: str = ""
    description_completeness: str = "PARTIAL"
    materials_status: str = "UNKNOWN"
    scope_sufficiency: str = "UNKNOWN"
    scope_enrichment_source: str = ""
    scope_enrichment_sha256: str = ""
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
    analysis_quality_status: str = ""
    quality_checked_at: datetime | None = None
    quality_errors: str = "[]"
    quality_repair_count: int = 0
    proposal_quality_score: float | None = None
    evidence_case_id: str = ""
    analysis_version: str = ""
    proposal_version: str = ""
    proposal_content_sha256: str = ""
    money_terms_json: str = ""
    timeline_terms_json: str = ""
    original_analysis_snapshot: str = ""
    quality_clarification_question: str = ""
    model_output_json: str = ""
    score_valid: bool | None = None
    score_raw: str = ""
    score_state: str = ""
    fit_score_valid: bool | None = None
    fit_score_raw: str = ""
    fit_score_state: str = ""
    # Ephemeral card-only signal. Durable retry ownership remains in job.status.
    sales_tracking_unavailable: bool = False

    @property
    def score_display(self) -> str:
        return score_display(
            self.score,
            raw=self.score_raw or None,
            explicit_state=self.score_state,
            explicit_valid=self.score_valid,
            analysis_succeeded=self.analysis_succeeded,
        )

    @property
    def fit_score_display(self) -> str:
        return score_display(
            self.fit_score,
            raw=self.fit_score_raw or None,
            explicit_state=self.fit_score_state,
            explicit_valid=self.fit_score_valid,
            analysis_succeeded=self.analysis_succeeded,
        )


def _score_semantics(value: Any, *, provider_succeeded: bool) -> tuple[float | None, bool, str, str]:
    metadata = normalize_score_metadata(
        value,
        raw=("" if value is None else value),
        analysis_succeeded=provider_succeeded,
    )
    semantic_value = (
        metadata.value
        if metadata.valid or metadata.state == SCORE_FAILED
        else None
    )
    return semantic_value, metadata.valid, metadata.raw, metadata.state


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
        f"Source language hint: {detect_language(subject + ' ' + body)}\n"
        f"Full available safe body:\n{trimmed}"
    )


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _safe_int(value: Any) -> int:
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _normalized_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Validate types while retaining compatibility with pre-schema fixtures."""

    if "analysis" in data:
        return OpportunityWireOutput.model_validate(data).analysis.model_dump()
    candidate = dict(data)
    if "commercial_decision" not in candidate:
        executable = str(candidate.get("executable") or "").casefold()
        candidate["commercial_decision"] = (
            "SKIP"
            if candidate.get("is_relevant") is False or executable == "no"
            else "ASK"
            if executable == "maybe"
            else "TAKE"
        )
    candidate.setdefault("decision_reason", str(candidate.get("reason") or ""))
    candidate.setdefault("clarification_question", "")
    return OpportunityAnalysisOutput.model_validate(candidate).model_dump()


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
    validation_errors: list[str] | tuple[str, ...] | None = None,
    repair_context: dict[str, Any] | None = None,
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
    provider_outcome = "SUCCESS"
    provider_model = ""
    provider_finish_reason = ""
    provider_prompt_tokens = 0
    provider_completion_tokens = 0
    provider_total_tokens = 0
    provider_error_code = ""
    try:
        user_prompt = _format_email(
            subject, sender, body, event_type, source_url, client_context
        )
        if validation_errors:
            user_prompt += (
                "\n\nQUALITY REPAIR — correct every deterministic validation error "
                "without inventing facts. Return the complete JSON object.\n"
                + "Validation errors: "
                + json.dumps(list(validation_errors), ensure_ascii=False)
            )
        if repair_context:
            user_prompt += (
                "\nImmutable source metadata and live-status must not be changed."
                "\nPrior model fields are untrusted, not mandatory defaults. "
                "Return the corrected decision branch; ASK/SKIP must clear offer "
                "fields. Keep genuine numeric zeros; never repair source freshness."
                "\nRepair context JSON:\n"
                + json.dumps(repair_context, ensure_ascii=False, default=str, sort_keys=True)
            )
        response = await client.chat.completions.create(
            model=model,
            response_format=STRICT_RESPONSE_FORMAT,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            temperature=0.1,
            max_tokens=MAX_MODEL_OUTPUT_TOKENS,
        )
        choice = response.choices[0]
        finish_reason_value = getattr(choice, "finish_reason", "")
        provider_finish_reason = (
            finish_reason_value if isinstance(finish_reason_value, str) else ""
        )
        provider_model_value = getattr(response, "model", "")
        provider_model = provider_model_value if isinstance(provider_model_value, str) else ""
        usage = getattr(response, "usage", None)
        provider_prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0))
        provider_completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0))
        provider_total_tokens = _safe_int(getattr(usage, "total_tokens", 0))
        refusal_value = getattr(choice.message, "refusal", None)
        refusal = refusal_value if isinstance(refusal_value, str) else ""
        if refusal.strip():
            provider_outcome = "REFUSAL"
            provider_error_code = "model_refusal"
            raise ValueError("model refused the structured request")
        if provider_finish_reason in {"length", "content_filter"}:
            provider_outcome = "INCOMPLETE"
            provider_error_code = f"finish_reason_{provider_finish_reason}"
            raise ValueError("model response was incomplete")
        content = getattr(choice.message, "content", None)
        if not isinstance(content, str) or not content.strip():
            provider_outcome = "INCOMPLETE"
            provider_error_code = "empty_model_content"
            raise ValueError("model returned empty content")
        data = _normalized_payload(_extract_json(content))
    except ValidationError:
        provider_outcome = "SCHEMA_ERROR"
        provider_error_code = "local_schema_validation_failed"
        logger.warning(
            "analyze_email schema validation failed email_id=%s", email_id
        )
        data = {}
        analysis_succeeded = False
    except Exception as exc:
        if provider_outcome == "SUCCESS":
            provider_outcome = "API_ERROR"
            provider_error_code = type(exc).__name__
        logger.warning(
            "analyze_email failed email_id=%s outcome=%s error_type=%s",
            email_id,
            provider_outcome,
            type(exc).__name__,
        )
        data = {}
        analysis_succeeded = False

    # Missing, null, malformed and non-finite values stay invalid instead of
    # being silently coerced to a legitimate zero.  Failed provider calls are
    # the sole diagnostic exception and remain marked analysis_succeeded=false.
    score, score_valid, score_raw, score_state = _score_semantics(
        data.get("score"), provider_succeeded=analysis_succeeded
    )
    fit_score, fit_score_valid, fit_score_raw, fit_score_state = _score_semantics(
        data.get("fit_score"), provider_succeeded=analysis_succeeded
    )
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
        commercial_decision=str(data.get("commercial_decision") or "TECHNICAL_FAILURE"),
        decision_reason=str(data.get("decision_reason") or data.get("reason") or ""),
        clarification_question=str(data.get("clarification_question") or ""),
        provider_outcome=provider_outcome,
        provider_model=provider_model or model,
        provider_finish_reason=provider_finish_reason,
        provider_prompt_tokens=provider_prompt_tokens,
        provider_completion_tokens=provider_completion_tokens,
        provider_total_tokens=provider_total_tokens,
        provider_error_code=provider_error_code,
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
        fit_score=fit_score,
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
        evidence_case_id=str(data.get("evidence_case_id", "")).strip().upper(),
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
        analysis_version=ANALYSIS_VERSION,
        model_output_json=json.dumps(data, ensure_ascii=False, sort_keys=True),
        score_valid=score_valid,
        score_raw=score_raw,
        score_state=score_state,
        fit_score_valid=fit_score_valid,
        fit_score_raw=fit_score_raw,
        fit_score_state=fit_score_state,
    )


async def analyze_candidate(
    candidate: "DigestJobCandidate",
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> JobAnalysis:
    """Analyze one deterministic digest child, never the whole digest HTML."""

    from .digest_parser import normalize_candidate_scope

    candidate = normalize_candidate_scope(candidate)
    deterministic = deterministic_candidate_decision(candidate)
    if deterministic is not None:
        return deterministic

    body_lines = [f"Description: {candidate.description}"]
    if candidate.budget:
        body_lines.append(f"Budget: {candidate.budget}")
    else:
        body_lines.append("Source budget: NOT_SPECIFIED (our scoped quote is permitted).")
    body_lines.append(
        f"Source assessment: completeness={candidate.description_completeness}; "
        f"materials={candidate.materials_status}; scope={candidate.scope_sufficiency}. "
        "Assess the actual brief; explain any disagreement with this prior classification."
    )
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
    analysis.materials_status = candidate.materials_status
    analysis.scope_sufficiency = candidate.scope_sufficiency
    analysis.scope_enrichment_source = candidate.scope_enrichment_source
    analysis.scope_enrichment_sha256 = candidate.scope_enrichment_sha256
    analysis.category = analysis.category or candidate.category
    analysis.deadline = analysis.deadline or candidate.deadline
    analysis.bid_count = (
        analysis.bid_count if analysis.bid_count is not None else candidate.bid_count
    )
    analysis.client_name = analysis.client_name or candidate.client_name
    analysis.client_profile_url = (
        analysis.client_profile_url or candidate.client_profile_url
    )
    analysis.project_id = candidate.project_id or analysis.project_id
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
    analysis.budget = candidate.budget or "не вказано"
    analysis.budget_provenance = "SOURCE_CANDIDATE" if candidate.budget else "UNAVAILABLE"
    return analysis


def deterministic_candidate_decision(
    candidate: "DigestJobCandidate",
) -> JobAnalysis | None:
    """Apply only source-explicit hard constraints; never infer team facts."""

    if (
        candidate.materials_status == "UNAVAILABLE_SCOPE_RELEVANT"
        or candidate.scope_sufficiency == "INSUFFICIENT_FOR_FIXED_TERMS"
    ):
        language = detect_language(f"{candidate.title}\n{candidate.description}")
        reasons = {
            "uk": (
                "Недоступні матеріали можуть містити обов'язкові вимоги, що "
                "впливають на обсяг, вартість або строк."
            ),
            "ru": (
                "Недоступные материалы могут содержать обязательные требования, "
                "влияющие на объём, стоимость или срок."
            ),
            "en": (
                "Unavailable materials may contain mandatory requirements that "
                "change scope, price, or timeline."
            ),
            "pl": (
                "Niedostępne materiały mogą zawierać obowiązkowe wymagania "
                "wpływające na zakres, cenę lub termin."
            ),
        }
        questions = {
            "uk": "Чи містять матеріали додаткові обов'язкові вимоги до обсягу, вартості або строку?",
            "ru": "Содержат ли материалы дополнительные обязательные требования к объёму, стоимости или сроку?",
            "en": "Do the materials contain additional mandatory requirements affecting scope, price, or timeline?",
            "pl": "Czy materiały zawierają dodatkowe obowiązkowe wymagania wpływające na zakres, cenę lub termin?",
        }
        reason = reasons[language]
        return JobAnalysis(
            email_id=candidate.stable_key,
            source_email_id=candidate.source_email_id,
            is_relevant=True,
            title=candidate.title,
            platform=candidate.platform,
            score=None,
            fit_score=None,
            reason=reason,
            decision_reason=reason,
            clarification_question=questions[language],
            commercial_decision="ASK",
            budget=candidate.budget or "не вказано",
            budget_provenance=(
                "SOURCE_CANDIDATE" if candidate.budget else "UNAVAILABLE"
            ),
            budget_currency=candidate.budget_currency,
            url=candidate.url,
            urgency="medium",
            why_relevant="",
            analysis_succeeded=True,
            event_type=candidate.event_type,
            full_description=candidate.description,
            description_completeness=candidate.description_completeness,
            materials_status=candidate.materials_status,
            scope_sufficiency=candidate.scope_sufficiency,
            scope_enrichment_source=candidate.scope_enrichment_source,
            scope_enrichment_sha256=candidate.scope_enrichment_sha256,
            language=language,
            category=candidate.category,
            deadline=candidate.deadline,
            bid_count=candidate.bid_count,
            client_name=candidate.client_name,
            client_profile_url=candidate.client_profile_url,
            project_id=candidate.project_id,
            executable="maybe",
            next_action={
                'uk': 'Уточнити у клієнта обов’язкові вимоги в недоступних матеріалах.',
                'ru': 'Уточнить у клиента обязательные требования в недоступных материалах.',
                'en': 'Ask the client to clarify mandatory requirements in the unavailable materials.',
                'pl': 'Zapytaj klienta o obowiązkowe wymagania w niedostępnych materiałach.',
            }[language],
            tags=candidate.tags,
            discovery_source=candidate.discovery_source,
            discovery_sources=candidate.discovery_source,
            source_publication_at=candidate.source_publication_at,
            source_feed_timestamp=candidate.source_feed_timestamp,
            feed_fetched_at=candidate.feed_fetched_at,
            first_seen_at=candidate.first_seen_at,
            received_at=candidate.received_at,
            evidence="",
            evidence_case_id="NO_DIRECT_CASE",
            analysis_version=ANALYSIS_VERSION,
            provider_outcome="NOT_CALLED_DETERMINISTIC_SCOPE_GUARD",
            provider_model="",
            model_output_json=json.dumps({"ask_basis": {
                "missing_fact": reason,
                "owner": "CLIENT", "fact_kind": "CLIENT_REQUIREMENT",
                "source_quote": "", "absence_reason": reason,
                "required_for_estimate": True, "estimate_impact": reason,
            }}, ensure_ascii=False),
        )

    source = f"{candidate.title}\n{candidate.description}".casefold()
    logo_task = any(token in source for token in ("логотип", "logo"))
    explicit_no_ai = any(
        token in source for token in ("не ии", "не ai", "not ai", "rather than ai")
    )
    specialist_required = bool(
        re.search(r"специалист\w*\s+по\s+логотип", source)
        or re.search(r"спеціаліст\w*\s+з\s+логотип", source)
        or "logo specialist" in source
    )
    if not (logo_task and explicit_no_ai and specialist_required):
        return None

    reason = (
        "Источник требует именно специалиста по логотипам и прямо исключает ИИ; "
        "соответствие этому обязательному способу выполнения не подтверждено."
    )
    return JobAnalysis(
        email_id=candidate.stable_key,
        source_email_id=candidate.source_email_id,
        is_relevant=False,
        title=candidate.title,
        platform=candidate.platform,
        score=0.0,
        fit_score=0.0,
        score_valid=True,
        score_raw="0.0",
        score_state="VALID",
        fit_score_valid=True,
        fit_score_raw="0.0",
        fit_score_state="VALID",
        reason=reason,
        decision_reason=reason,
        commercial_decision="SKIP",
        budget=candidate.budget or "не вказано",
        budget_provenance=("SOURCE_CANDIDATE" if candidate.budget else "UNAVAILABLE"),
        budget_currency=candidate.budget_currency,
        url=candidate.url,
        urgency="low",
        why_relevant="",
        analysis_succeeded=True,
        event_type=candidate.event_type,
        full_description=candidate.description,
        description_completeness=candidate.description_completeness,
        language=detect_language(f"{candidate.title}\n{candidate.description}"),
        category=candidate.category,
        deadline=candidate.deadline,
        bid_count=candidate.bid_count,
        client_name=candidate.client_name,
        client_profile_url=candidate.client_profile_url,
        project_id=candidate.project_id,
        service_lane="logo design",
        executable="no",
        next_action="Ставку не подавать.",
        tags=candidate.tags,
        discovery_source=candidate.discovery_source,
        discovery_sources=candidate.discovery_source,
        source_publication_at=candidate.source_publication_at,
        source_feed_timestamp=candidate.source_feed_timestamp,
        feed_fetched_at=candidate.feed_fetched_at,
        first_seen_at=candidate.first_seen_at,
        received_at=candidate.received_at,
        evidence=(
            "В опубликованном ТЗ обязательны специалист по логотипам и выполнение не ИИ."
        ),
        analysis_version=ANALYSIS_VERSION,
        provider_outcome="NOT_CALLED_DETERMINISTIC_POLICY",
        provider_model="",
        model_output_json="{}",
    )


async def repair_analysis(
    original: JobAnalysis,
    validation_errors: list[str] | tuple[str, ...],
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> JobAnalysis:
    """Run exactly one caller-bounded repair while preserving source metadata."""

    from .quality_gate import approved_evidence_text, model_repair_errors, repair_diagnostics, evidence_selection_errors

    validation_errors = model_repair_errors(validation_errors)
    if not validation_errors:
        raise ValueError("No model-repairable errors; source/actionability cannot be repaired by a model")

    # Exactly one rejected model object. Never embed a dataclass containing it.
    try:
        rejected = json.loads(original.model_output_json or "{}")
        rejected = rejected.get("analysis", rejected)
        if not isinstance(rejected, dict):
            rejected = {}
    except (ValueError, TypeError, AttributeError):
        rejected = {}
    rejected = {name: value for name, value in rejected.items()
                if name in OpportunityAnalysisOutput.model_fields}
    if not rejected:
        rejected = {name: getattr(original, name, None)
                    for name in OpportunityAnalysisOutput.model_fields if hasattr(original, name)}
    source_facts = {name: getattr(original, name) for name in (
        "full_description", "title", "url", "platform", "project_id", "thread_id",
        "budget", "budget_currency", "budget_provenance", "language",
        "description_completeness", "materials_status", "scope_sufficiency",
        "scope_enrichment_source", "scope_enrichment_sha256", "live_status",
        "live_status_checked_at", "biddable",
    )}
    # Source/live fields are supplied for grounding, but are immutable below.
    repaired = await analyze_email(
        email_id=original.email_id,
        subject=original.title,
        sender=original.platform,
        body=original.full_description,
        client=client,
        model=model,
        event_type=original.event_type,
        source_url=original.url,
        client_context=original.client_context,
        validation_errors=validation_errors,
        repair_context={
            "rejected_response": rejected,
            "source_facts": source_facts,
            "diagnostics": repair_diagnostics(original, validation_errors),
        },
    )
    for field_name in (
        "title",
        "event_type",
        "language",
        "budget",
        "budget_provenance",
        "source_email_id",
        "full_description",
        "description_completeness",
        "materials_status",
        "scope_sufficiency",
        "scope_enrichment_source",
        "scope_enrichment_sha256",
        "category",
        "skills",
        "deadline",
        "bid_count",
        "client_name",
        "client_profile_url",
        "client_context",
        "project_id",
        "thread_id",
        "received_at",
        "sensitive_redacted",
        "source_mailbox_alias",
        "live_status",
        "live_status_checked_at",
        "live_status_evidence",
        "biddable",
        "live_status_retry_count",
        "live_status_last_error",
        "tags",
        "budget_currency",
        "discovery_source",
        "discovery_sources",
        "source_publication_at",
        "source_feed_timestamp",
        "feed_fetched_at",
        "first_seen_at",
    ):
        setattr(repaired, field_name, getattr(original, field_name))
    repaired.platform = original.platform
    repaired.url = original.url
    repaired.project_id = original.project_id
    # A previous model enum is not a source fact. The full gate still checks
    # relevance/grounding of this NEW choice; text can only come from registry.
    repaired.selected_evidence = ('' if evidence_selection_errors(repaired) else
        approved_evidence_text(repaired.evidence_case_id, repaired.language))
    return repaired


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
