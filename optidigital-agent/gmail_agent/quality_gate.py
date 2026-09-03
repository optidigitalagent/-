"""Deterministic proposal-readiness validation for commercial project cards.

The model supplies an analysis; this module decides whether that analysis may
be exposed as a copy-ready proposal.  It deliberately has no network or model
dependency so a second model opinion can never waive the contract.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from .email_analyzer import JobAnalysis


ANALYSIS_VERSION = "proposal-quality-gate-v1"
PROPOSAL_VERSION_PREFIX = "pqg-v1"


class QualityStatus(StrEnum):
    VALID = "QUALITY_VALID"
    REPAIRED = "QUALITY_REPAIRED"
    MANUAL_REVIEW = "QUALITY_MANUAL_REVIEW"
    NON_EXECUTABLE = "QUALITY_NON_EXECUTABLE"
    FAILED = "QUALITY_FAILED"


PROPOSAL_READY_QUALITY_STATUSES = frozenset(
    {QualityStatus.VALID.value, QualityStatus.REPAIRED.value}
)


# Exact approved factual claims from the canonical Project Brain portfolio
# registry.  These are application-owned strings, never model-owned claims.
EVIDENCE_REGISTRY: Mapping[str, str] = {
    "BELLA_DENT": (
        "Bella Dent — website, lead automation, Telegram bots, PostgreSQL and "
        "Cloudinary; supported by live-system and implementation history."
    ),
    "DENTAL_SUPPLIER_AI_AGENT": (
        "Dental Supplier AI Agent — AI agent, Telegram, supplier comparison "
        "and reporting; supported by private code and architecture."
    ),
    "GMAIL_JOB_AGENT": (
        "Gmail Job Agent — Gmail ingestion, AI qualification, Telegram, "
        "Railway and PostgreSQL; supported by working code and production history."
    ),
    "STATUS_DENT": (
        "Status Dent — website, SEO and local search; supported by a live site "
        "and Google Search Console work."
    ),
    "AMIDENTAL": (
        "Amidental — website, forms and deployment; supported by a live site "
        "and design work."
    ),
    "ART_STUDIO_184": (
        "Art Studio 184 — website, automation, pricing and HR tools; supported "
        "by project history and assets."
    ),
    "AUDIOBOOK_CLEANER": (
        "Audiobook Cleaner — audio AI, ASR cleanup and QA pipeline; supported "
        "by CLI, tests and human feedback."
    ),
    "MENTIUM": (
        "Mentium — education AI product and MVP discovery; supported by "
        "platform and discovery history."
    ),
    "NFC_REVIEW_CARDS": (
        "NFC Review Cards — NFC product workflow and reviews; supported by "
        "physical-product and sales activity."
    ),
    "NO_DIRECT_CASE": (
        "No directly matching production case is claimed; the approach is "
        "based only on the stated capabilities and source requirements."
    ),
    "DEMO_REQUIRED": (
        "A project-specific demo or prototype is required before any production "
        "result or deployment claim can be made."
    ),
}


_PLACEHOLDER_RE = re.compile(
    r"(?i)(?:\[(?:name|price|link|client|company|budget|timeline)[^\]]*\]|"
    r"\{\{?[^{}]+\}?\}|\bTBD\b|\bTBC\b|\bN/?A\b|<insert\b|lorem ipsum)"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_TELEGRAM_RE = re.compile(
    r"(?i)(?:\bt\.me/|(?<![\w.])@[a-z][a-z0-9_]{4,}|"
    r"\b(?:message|contact|write|напиш\w*|пиш\w*)\b.{0,24}\btelegram\b)"
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){9,15}(?!\d)")
_OFF_PLATFORM_RE = re.compile(
    r"(?i)\b(?:whatsapp|viber|signal|skype|email me|write me at|"
    r"напиш(?:іть|ите)\s+(?:мені|мне)\s+(?:у|в)|пишіть\s+на)\b"
)
_UNSUPPORTED_CLAIM_RE = re.compile(
    r"(?i)(?:\b\d+(?:[.,]\d+)?\s*%|"
    r"\b\d+\+?\s*(?:years?|рок(?:и|ів|а)|лет|lat)\s+(?:of\s+)?(?:experience|досвід|опыт|doświadczen)|"
    r"\b\d+\+?\s*(?:clients?|клієнт|клиент|klient)|"
    r"\b(?:hundreds?|thousands?|сотн|тисяч|тысяч)\w*\s+(?:clients?|клієнт|клиент)|"
    r"\b(?:certified|сертифікован|сертифицирован|certyfikowan)\w*|"
    r"\b(?:five[- ]star|5[- ]star|rating|рейтинг|відгук(?:ів)?|отзыв(?:ов)?|recenzj(?:a|i))\b)"
)
_PRICE_RE = re.compile(
    r"(?i)(?:\d[\d\s.,]*(?:\s*[-–—]\s*\d[\d\s.,]*)?\s*"
    r"(?:UAH|USD|EUR|PLN|грн|₴|\$|€|zł))"
)
_TIMELINE_RE = re.compile(
    r"(?i)\b\d+(?:\s*[-–—]\s*\d+)?\s*"
    r"(?:hours?|days?|weeks?|months?|годин\w*|дн(?:і|ів|я)|тижн\w*|місяц\w*|"
    r"час(?:а|ов)?|дн(?:я|ей|и)|недел\w*|месяц\w*|godzin\w*|dni|dzień|tygodn\w*|miesi(?:ą|a)c\w*)\b"
)
_CONDITION_RE = re.compile(
    r"(?i)\b(?:if|after (?:you|the client) confirm|subject to|assuming|"
    r"якщо|після (?:вашого )?підтвердження|за умови|припускаю|"
    r"если|после подтверждения|при условии|предполагаю|"
    r"jeśli|po potwierdzeniu|pod warunkiem|zakładam)\b"
)
_PARTIAL_RE = re.compile(
    r"(?i)\b(?:assum(?:e|ing|ption)|subject to confirmation|clarif|"
    r"припущ|уточн|потрібно підтвердити|неповн|"
    r"предполож|уточн|нужно подтвердить|неполн|"
    r"założ|doprecyz|potwierdzeni|niepełn)\w*"
)
_CURRENCY_RE = re.compile(r"(?i)\b(?:UAH|USD|EUR|PLN|грн|zł)\b|[₴$€]")
_DIRECT_CASE_RE = re.compile(
    r"(?i)\b(?:our|наш(?:а|і|и)?|nasz(?:a|e)?)\s+.{0,48}"
    r"\b(?:case|project|кейс|проєкт|проект|projekt)\b"
)


@dataclass(frozen=True, slots=True)
class QualityValidation:
    status: str
    errors: tuple[str, ...]
    checked_at: datetime
    proposal_quality_score: float
    clarification_question: str = ""

    @property
    def proposal_ready(self) -> bool:
        return self.status in PROPOSAL_READY_QUALITY_STATUSES

    def errors_json(self) -> str:
        return json.dumps(list(self.errors), ensure_ascii=False)


def finite_score(value: Any) -> float | None:
    """Return a valid score without turning missing/malformed data into zero."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 10.0:
        return None
    return parsed


def approved_evidence_text(case_id: str) -> str:
    return EVIDENCE_REGISTRY.get(str(case_id or "").strip().upper(), "")


def _question_count(text: str) -> int:
    return (text or "").count("?")


def _one_action(text: str) -> bool:
    value = " ".join((text or "").split())
    if not value or _PLACEHOLDER_RE.search(value):
        return False
    if re.search(r"(?:^|\s)(?:1[.)]|2[.)]|[-•]\s)", value):
        return False
    sentences = [part for part in re.split(r"[.!?]+(?:\s+|$)", value) if part.strip()]
    return len(sentences) == 1


def _language_matches(language: str, proposal: str) -> bool:
    value = (proposal or "").casefold()
    if not value:
        return False
    if language == "uk":
        return bool(re.search(r"[іїєґ]", value)) or any(
            word in value for word in ("потріб", "можемо", "проєкт", "підтверд", "термін")
        )
    if language == "ru":
        return bool(re.search(r"[ыэъё]", value)) or any(
            word in value for word in ("нужно", "можем", "проект", "срок", "подтверд")
        )
    if language == "pl":
        return bool(re.search(r"[ąćęłńóśźż]", value)) or any(
            word in value for word in ("projekt", "możemy", "termin", "potwierd")
        )
    if language == "en":
        return bool(re.search(r"\b(?:the|we|your|project|can|will|deliver)\b", value))
    return False


def _project_specific(analysis: "JobAnalysis") -> bool:
    proposal_text = " ".join((analysis.proposal_draft or "").casefold().split())
    title_text = " ".join((analysis.title or "").casefold().split())
    if len(title_text) >= 6 and title_text in proposal_text:
        return True
    proposal_words = set(re.findall(r"[^\W\d_]{5,}", proposal_text))
    source_words = set(
        re.findall(
            r"[^\W\d_]{5,}",
            f"{analysis.title or ''} {analysis.full_description or ''}".casefold(),
        )
    )
    generic = {
        "project", "проєкт", "проект", "projekt", "client", "клієнт", "клиент",
        "робота", "работа", "praca", "можемо", "можем", "deliver", "виконати",
    }
    return bool((proposal_words & source_words) - generic)


def _source_grounded(text: str, analysis: "JobAnalysis") -> bool:
    claim_text = " ".join((text or "").casefold().split())
    title_text = " ".join((analysis.title or "").casefold().split())
    if len(title_text) >= 6 and title_text in claim_text:
        return True
    claim_words = set(re.findall(r"[^\W\d_]{5,}", claim_text))
    source_words = set(
        re.findall(
            r"[^\W\d_]{5,}",
            f"{analysis.title or ''} {analysis.full_description or ''}".casefold(),
        )
    )
    generic = {
        "source", "project", "requirements", "requires", "client", "explicitly",
        "джерело", "проєкт", "проект", "вимоги", "клієнт", "замовник",
        "źródło", "projekt", "wymagania", "klient",
    }
    return bool((claim_words & source_words) - generic)


def _safe_text_errors(analysis: "JobAnalysis") -> list[str]:
    proposal = analysis.proposal_draft or ""
    errors: list[str] = []
    if _PLACEHOLDER_RE.search(proposal):
        errors.append("proposal_contains_placeholder")
    if (
        _EMAIL_RE.search(proposal)
        or _TELEGRAM_RE.search(proposal)
        or _PHONE_RE.search(proposal)
        or _OFF_PLATFORM_RE.search(proposal)
    ):
        errors.append("proposal_contains_external_contact")
    if _UNSUPPORTED_CLAIM_RE.search(proposal):
        errors.append("proposal_contains_unsupported_claim")
    return errors


def _commercial_consistency_errors(analysis: "JobAnalysis") -> list[str]:
    errors: list[str] = []
    budget = analysis.budget or ""
    price = analysis.recommended_price or ""
    budget_currency = (_CURRENCY_RE.search(budget).group(0).upper() if _CURRENCY_RE.search(budget) else "")
    price_currency = (_CURRENCY_RE.search(price).group(0).upper() if _CURRENCY_RE.search(price) else "")
    aliases = {"ГРН": "UAH", "₴": "UAH", "$": "USD", "€": "EUR", "ZŁ": "PLN"}
    budget_currency = aliases.get(budget_currency, budget_currency)
    price_currency = aliases.get(price_currency, price_currency)
    if budget_currency and price_currency and budget_currency != price_currency:
        errors.append("recommended_price_currency_conflicts_with_budget")

    effort_match = re.search(r"(?i)(\d+)(?:\s*[-–—]\s*(\d+))?\s*(?:hours?|годин\w*|час\w*|godzin\w*)", analysis.estimated_effort or "")
    day_match = re.search(r"(?i)(\d+)(?:\s*[-–—]\s*(\d+))?\s*(?:days?|дн(?:і|ів|я)|дн(?:я|ей|и)|dni|dzień)", analysis.realistic_timeline or "")
    if effort_match and day_match:
        effort_high = int(effort_match.group(2) or effort_match.group(1))
        days_high = int(day_match.group(2) or day_match.group(1))
        if days_high > 0 and effort_high > days_high * 16:
            errors.append("effort_timeline_inconsistent")

    if (
        str(analysis.evidence_case_id or "").upper() in {"NO_DIRECT_CASE", "DEMO_REQUIRED"}
        and _DIRECT_CASE_RE.search(analysis.proposal_draft or "")
    ):
        errors.append("proposal_claims_unapproved_direct_case")
    return errors


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def validate_analysis(
    analysis: "JobAnalysis",
    *,
    repaired: bool = False,
    now: datetime | None = None,
) -> QualityValidation:
    """Validate one analysis and return a fail-closed quality decision."""

    checked_at = now or datetime.now(timezone.utc)
    executable = str(analysis.executable or "maybe").strip().casefold()
    if executable == "no":
        errors: list[str] = []
        if analysis.recommended_price:
            errors.append("non_executable_has_price")
        if analysis.realistic_timeline:
            errors.append("non_executable_has_timeline")
        if analysis.proposal_draft:
            errors.append("non_executable_has_proposal")
        if not (analysis.reason or "").strip():
            errors.append("missing_non_executable_reason")
        return QualityValidation(
            QualityStatus.NON_EXECUTABLE.value,
            _dedupe(errors),
            checked_at,
            0.0,
        )

    errors = []
    if not analysis.analysis_succeeded:
        errors.append("analysis_provider_failed")
    if not analysis.is_relevant:
        errors.append("analysis_not_relevant")
    if str(analysis.live_status or "") != "ACTIVE_BIDDABLE" or analysis.biddable is not True:
        errors.append("live_status_not_active_biddable")
    live_checked_at = analysis.live_status_checked_at
    if live_checked_at is None:
        errors.append("live_status_not_fresh")
    else:
        if live_checked_at.tzinfo is None:
            live_checked_at = live_checked_at.replace(tzinfo=timezone.utc)
        live_age = (checked_at - live_checked_at).total_seconds()
        if live_age < -5 or live_age > 60:
            errors.append("live_status_not_fresh")

    score = finite_score(analysis.score)
    fit = finite_score(analysis.fit_score)
    if score is None:
        errors.append("score_missing_or_invalid")
    elif score == 0.0:
        errors.append("score_zero_not_proposal_ready")
    if fit is None:
        errors.append("fit_score_missing_or_invalid")
    elif fit == 0.0:
        errors.append("fit_score_zero_not_proposal_ready")

    if analysis.language not in {"uk", "ru", "en", "pl"}:
        errors.append("invalid_client_language")
    if not (analysis.service_lane or "").strip():
        errors.append("missing_service_lane")
    if not (analysis.reason or "").strip():
        errors.append("missing_commercial_reason")
    if not ((analysis.why_relevant or "").strip() or (analysis.evidence or "").strip()):
        errors.append("missing_relevance_evidence")
    if (analysis.evidence or "").strip() and not _source_grounded(
        analysis.evidence, analysis
    ):
        errors.append("analysis_evidence_not_source_grounded")
    if not (analysis.estimated_effort or "").strip():
        errors.append("missing_estimated_effort")
    if not (analysis.delivery_risk or "").strip():
        errors.append("missing_delivery_risk")
    if not (analysis.client_payment_risk or "").strip():
        errors.append("missing_client_payment_risk")
    if analysis.project_mode not in {"CASH", "REPUTATION", "STRATEGIC"}:
        errors.append("invalid_project_mode")
    if not (analysis.project_mode_reason or "").strip():
        errors.append("missing_project_mode_reason")

    price = analysis.recommended_price or ""
    if not _PRICE_RE.search(price):
        errors.append("recommended_price_missing_amount_or_currency")
    timeline = analysis.realistic_timeline or ""
    if not timeline.strip() or not _TIMELINE_RE.search(timeline):
        errors.append("realistic_timeline_missing_or_unparseable")

    evidence_id = str(analysis.evidence_case_id or "").strip().upper()
    approved = approved_evidence_text(evidence_id)
    if not approved:
        errors.append("invalid_evidence_case_id")

    proposal = analysis.proposal_draft or ""
    if not proposal.strip():
        errors.append("missing_proposal")
    else:
        errors.extend(_safe_text_errors(analysis))
        if not _language_matches(analysis.language, proposal):
            errors.append("proposal_language_mismatch")
        if not _project_specific(analysis):
            errors.append("proposal_not_project_specific")
        if len(proposal) > 3500:
            errors.append("proposal_not_concise")
        errors.extend(_commercial_consistency_errors(analysis))

    if not _one_action(analysis.next_action or ""):
        errors.append("next_action_must_be_exactly_one")

    partial = str(analysis.description_completeness or "PARTIAL").upper() == "PARTIAL"
    question_count = _question_count(proposal)
    if partial and proposal and not (_PARTIAL_RE.search(proposal) or question_count == 1):
        errors.append("partial_scope_not_bounded")
    if question_count > 1:
        errors.append("more_than_one_clarification_question")

    if executable == "maybe":
        if question_count != 1:
            errors.append("maybe_requires_one_clarification_question")
        if not _CONDITION_RE.search(proposal):
            errors.append("maybe_proposal_not_conditioned")
        # A maybe analysis is intentionally never a normal bid-ready card.
        return QualityValidation(
            QualityStatus.MANUAL_REVIEW.value,
            _dedupe(errors or ["executable_maybe_requires_owner_review"]),
            checked_at,
            _quality_score(errors),
            _first_question(proposal),
        )

    if executable != "yes":
        errors.append("invalid_executable_state")

    unique_errors = _dedupe(errors)
    if unique_errors:
        status = (
            QualityStatus.FAILED.value
            if not analysis.analysis_succeeded
            else QualityStatus.MANUAL_REVIEW.value
        )
    else:
        status = QualityStatus.REPAIRED.value if repaired else QualityStatus.VALID.value
    return QualityValidation(
        status,
        unique_errors,
        checked_at,
        _quality_score(unique_errors),
        _first_question(proposal),
    )


def _quality_score(errors: Any) -> float:
    count = len(errors)
    return max(0.0, round(10.0 - (count * 0.75), 2))


def _first_question(text: str) -> str:
    match = re.search(r"([^?\n]{3,}\?)", text or "")
    return " ".join(match.group(1).split()) if match else ""


def apply_validation(
    analysis: "JobAnalysis",
    validation: QualityValidation,
    *,
    repair_count: int = 0,
) -> "JobAnalysis":
    """Persist the deterministic decision on the mutable analysis object."""

    analysis.analysis_quality_status = validation.status
    analysis.quality_checked_at = validation.checked_at
    analysis.quality_errors = validation.errors_json()
    analysis.quality_repair_count = max(0, min(1, int(repair_count)))
    analysis.proposal_quality_score = validation.proposal_quality_score
    analysis.quality_clarification_question = validation.clarification_question
    analysis.analysis_version = analysis.analysis_version or ANALYSIS_VERSION
    if analysis.evidence_case_id:
        analysis.evidence_case_id = analysis.evidence_case_id.strip().upper()
    approved = approved_evidence_text(analysis.evidence_case_id)
    if approved:
        analysis.selected_evidence = approved
    if validation.proposal_ready:
        analysis.proposal_version = proposal_version(analysis)
    else:
        analysis.qualified = False
        analysis.proposal_version = ""
        # Manual/non-executable states must never leak a usable bid package.
        analysis.recommended_price = ""
        analysis.realistic_timeline = ""
        analysis.proposal_draft = ""
        if validation.status == QualityStatus.NON_EXECUTABLE.value:
            analysis.next_action = "Do not bid."
        elif validation.status in {
            QualityStatus.MANUAL_REVIEW.value,
            QualityStatus.FAILED.value,
        }:
            analysis.next_action = "Review the quality errors; do not submit a bid."
    return analysis


def proposal_version(analysis: "JobAnalysis") -> str:
    payload = {
        "analysis_version": analysis.analysis_version or ANALYSIS_VERSION,
        "evidence_case_id": analysis.evidence_case_id,
        "fit_score": finite_score(analysis.fit_score),
        "price": analysis.recommended_price,
        "proposal": analysis.proposal_draft,
        "score": finite_score(analysis.score),
        "timeline": analysis.realistic_timeline,
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"{PROPOSAL_VERSION_PREFIX}:{digest}"


def quality_errors(analysis: Any) -> list[str]:
    raw = (
        getattr(analysis, "quality_errors", "")
        if not isinstance(analysis, dict)
        else analysis.get("quality_errors", "")
    )
    if isinstance(raw, list):
        return [str(item) for item in raw]
    try:
        parsed = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return [str(raw)] if raw else []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def is_proposal_ready(record: Any) -> bool:
    getter = (
        record.get
        if isinstance(record, dict)
        else lambda key, default=None: getattr(record, key, default)
    )
    live_checked_at = getter("live_status_checked_at", None)
    if not isinstance(live_checked_at, datetime):
        return False
    if live_checked_at.tzinfo is None:
        live_checked_at = live_checked_at.replace(tzinfo=timezone.utc)
    live_age = (datetime.now(timezone.utc) - live_checked_at).total_seconds()
    return (
        getter("analysis_quality_status", "") in PROPOSAL_READY_QUALITY_STATUSES
        and getter("live_status", "") == "ACTIVE_BIDDABLE"
        and getter("biddable", None) is True
        and -5 <= live_age <= 60
        and str(getter("executable", "")).casefold() == "yes"
        and finite_score(getter("score", None)) not in {None, 0.0}
        and finite_score(getter("fit_score", None)) not in {None, 0.0}
        and bool(str(getter("proposal_version", "") or "").strip())
    )
