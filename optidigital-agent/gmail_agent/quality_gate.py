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


ANALYSIS_VERSION = "proposal-quality-gate-v2"
PROPOSAL_VERSION_PREFIX = "pqg-v2"

SCORE_VALID = "VALID"
SCORE_MISSING = "MISSING"
SCORE_INVALID = "INVALID"
SCORE_FAILED = "FAILED"
SCORE_STATES = frozenset({SCORE_VALID, SCORE_MISSING, SCORE_INVALID, SCORE_FAILED})

APPLICATION_EVIDENCE_PREFIX = "Approved evidence: "
APPLICATION_COMMERCIAL_PREFIX = "Commercial terms: "


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
_PAST_CAPABILITY_RE = re.compile(
    r"(?i)\b(?:we|our team|ми|наша команда|мы|наша команда|nasz zespół)\s+"
    r"(?:have\s+)?(?:built|created|developed|implemented|integrated|launched|delivered|"
    r"створил\w*|розробил\w*|реалізувал\w*|впровадил\w*|інтегрувал\w*|запустил\w*|"
    r"создал\w*|разработал\w*|реализовал\w*|внедрил\w*|интегрировал\w*|"
    r"zbudowal\w*|stworzyl\w*|wdrozyl\w*|zintegrowal\w*)\b"
)
_BUDGET_RATIONALE_RE = re.compile(
    r"(?i)\b(?:because|scope|milestone|complex|integration|risk|reason|"
    r"тому що|обсяг|етап|складн|інтеграц|ризик|"
    r"потому что|объ[её]м|этап|сложн|интеграц|риск|"
    r"ponieważ|zakres|etap|złożon|integrac|ryzyko)\b"
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


def score_state(
    value: Any,
    *,
    raw: Any = None,
    explicit_state: str = "",
    explicit_valid: bool | None = None,
    analysis_succeeded: bool = True,
) -> str:
    """Preserve missing/invalid/failure semantics independently of float storage."""

    state = str(explicit_state or "").strip().upper()
    if state in SCORE_STATES:
        return state
    if analysis_succeeded is False:
        return SCORE_FAILED
    if explicit_valid is False:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return SCORE_MISSING
        return SCORE_INVALID
    candidate = (
        value
        if raw is None or (isinstance(raw, str) and not raw.strip())
        else raw
    )
    if candidate is None or (isinstance(candidate, str) and not candidate.strip()):
        return SCORE_MISSING
    return SCORE_VALID if finite_score(candidate) is not None else SCORE_INVALID


def score_display(
    value: Any,
    *,
    raw: Any = None,
    explicit_state: str = "",
    explicit_valid: bool | None = None,
    analysis_succeeded: bool = True,
) -> str:
    state = score_state(
        value,
        raw=raw,
        explicit_state=explicit_state,
        explicit_valid=explicit_valid,
        analysis_succeeded=analysis_succeeded,
    )
    if state == SCORE_MISSING:
        return "—"
    if state == SCORE_INVALID:
        return "INVALID"
    if state == SCORE_FAILED:
        return "FAILED"
    parsed = finite_score(value if raw is None else raw)
    if parsed is None:
        parsed = finite_score(value)
    return f"{parsed:.1f}/10" if parsed is not None else "INVALID"


def approved_evidence_text(case_id: str) -> str:
    return EVIDENCE_REGISTRY.get(str(case_id or "").strip().upper(), "")


def _record_value(record: Any, field_name: str, default: Any = "") -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name, default)
    return getattr(record, field_name, default)


def _normalized_text(value: str) -> str:
    return " ".join((value or "").split())


def application_owned_commercial_block(analysis: Any) -> str:
    return (
        f"{APPLICATION_COMMERCIAL_PREFIX}"
        f"{_normalized_text(str(_record_value(analysis, 'recommended_price') or ''))}; "
        "timeline: "
        f"{_normalized_text(str(_record_value(analysis, 'realistic_timeline') or ''))}."
    )


def application_owned_evidence_clause(analysis: Any) -> str:
    return APPLICATION_EVIDENCE_PREFIX + approved_evidence_text(
        str(_record_value(analysis, "evidence_case_id") or "")
    )


def proposal_body(value: str) -> str:
    """Return only the model-owned body, excluding application-owned suffixes."""

    text = (value or "").strip()
    marker = f"\n\n{APPLICATION_EVIDENCE_PREFIX}"
    if marker in text:
        return text.split(marker, 1)[0].strip()
    return text


def compose_application_owned_proposal(analysis: Any) -> str:
    body = proposal_body(str(_record_value(analysis, "proposal_draft") or ""))
    approved = approved_evidence_text(
        str(_record_value(analysis, "evidence_case_id") or "")
    )
    if not body or not approved:
        return body
    return (
        f"{body}\n\n{application_owned_evidence_clause(analysis)}\n"
        f"{application_owned_commercial_block(analysis)}"
    )


def _score_state_for(analysis: "JobAnalysis", field_name: str) -> str:
    return score_state(
        getattr(analysis, field_name, None),
        raw=getattr(analysis, f"{field_name}_raw", None),
        explicit_state=getattr(analysis, f"{field_name}_state", ""),
        explicit_valid=getattr(analysis, f"{field_name}_valid", None),
        analysis_succeeded=getattr(analysis, "analysis_succeeded", True),
    )


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


def _number(value: str) -> float | None:
    compact = re.sub(r"\s+", "", value or "")
    if not compact:
        return None
    if "," in compact and "." not in compact:
        tail = compact.rsplit(",", 1)[-1]
        compact = compact.replace(",", "" if len(tail) == 3 else ".")
    else:
        compact = compact.replace(",", "")
    try:
        parsed = float(compact)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _money_signature(text: str) -> tuple[float, float, str] | None:
    match = re.search(
        r"(?i)(\d[\d\s.,]*?)(?:\s*[-–—]\s*(\d[\d\s.,]*?))?\s*"
        r"(UAH|USD|EUR|PLN|грн|₴|\$|€|zł)",
        text or "",
    )
    if not match:
        return None
    low = _number(match.group(1))
    high = _number(match.group(2) or match.group(1))
    if low is None or high is None:
        return None
    aliases = {"ГРН": "UAH", "₴": "UAH", "$": "USD", "€": "EUR", "ZŁ": "PLN"}
    currency = aliases.get(match.group(3).upper(), match.group(3).upper())
    return min(low, high), max(low, high), currency


def _timeline_signature(text: str) -> tuple[int, int, str] | None:
    match = re.search(
        r"(?i)\b(\d+)(?:\s*[-–—]\s*(\d+))?\s*"
        r"(hours?|days?|weeks?|months?|годин\w*|дн(?:і|ів|я)|тижн\w*|місяц\w*|"
        r"час(?:а|ов)?|дн(?:я|ей|и)|недел\w*|месяц\w*|godzin\w*|dni|dzień|tygodn\w*|miesi(?:ą|a)c\w*)\b",
        text or "",
    )
    if not match:
        return None
    low = int(match.group(1))
    high = int(match.group(2) or match.group(1))
    token = match.group(3).casefold()
    if token.startswith(("hour", "годин", "час", "godzin")):
        unit = "hours"
    elif token.startswith(("day", "дн", "dni", "dzień")):
        unit = "days"
    elif token.startswith(("week", "тижн", "недел", "tygodn")):
        unit = "weeks"
    else:
        unit = "months"
    return min(low, high), max(low, high), unit


def _milestone_signature(text: str) -> int | None:
    match = re.search(
        r"(?i)\b(one|two|three|1|2|3|один|одна|два|дві|три|jeden|jedna|dwa|dwie|trzy)\s+"
        r"(?:funded\s+)?(?:milestones?|етап\w*|этап\w*)\b",
        text or "",
    )
    if not match:
        return None
    token = match.group(1).casefold()
    return 1 if token in {"one", "1", "один", "одна", "jeden", "jedna"} else 2 if token in {"two", "2", "два", "дві", "dwa", "dwie"} else 3


def _application_owned_proposal_errors(analysis: "JobAnalysis") -> list[str]:
    proposal = analysis.proposal_draft or ""
    body = proposal_body(proposal)
    errors: list[str] = []
    evidence_id = str(analysis.evidence_case_id or "").strip().upper()
    approved = approved_evidence_text(evidence_id)
    has_injected_suffix = f"\n\n{APPLICATION_EVIDENCE_PREFIX}" in proposal

    case_labels = {
        "bella dent", "dental supplier ai agent", "gmail job agent",
        "status dent", "amidental", "art studio 184", "audiobook cleaner",
        "mentium", "nfc review cards",
    }
    body_folded = body.casefold()
    if any(label in body_folded for label in case_labels):
        errors.append("proposal_contains_model_owned_case_claim")
    if _PAST_CAPABILITY_RE.search(body) or _DIRECT_CASE_RE.search(body):
        errors.append("proposal_contains_unapproved_capability_claim")

    body_money = _money_signature(body)
    structured_money = _money_signature(analysis.recommended_price or "")
    if body_money is not None:
        if structured_money is None or body_money != structured_money:
            errors.append("proposal_price_conflicts_with_recommended_price")
        errors.append("proposal_contains_model_owned_commercial_terms")
    body_timeline = _timeline_signature(body)
    structured_timeline = _timeline_signature(analysis.realistic_timeline or "")
    if body_timeline is not None:
        if structured_timeline is None or body_timeline != structured_timeline:
            errors.append("proposal_timeline_conflicts_with_realistic_timeline")
        errors.append("proposal_contains_model_owned_commercial_terms")
    body_milestones = _milestone_signature(body)
    structured_milestones = _milestone_signature(analysis.recommended_price or "")
    if body_milestones is not None:
        if body_milestones != structured_milestones:
            errors.append("proposal_milestone_logic_conflicts_with_recommended_price")
        errors.append("proposal_contains_model_owned_commercial_terms")

    if has_injected_suffix:
        expected = compose_application_owned_proposal(analysis)
        if _normalized_text(proposal) != _normalized_text(expected):
            errors.append("proposal_application_owned_suffix_mismatch")
        if not approved or _normalized_text(analysis.selected_evidence) != _normalized_text(approved):
            errors.append("selected_evidence_not_registry_exact")
        if proposal.count(application_owned_evidence_clause(analysis)) != 1:
            errors.append("evidence_clause_not_application_owned_exact")
        if proposal.count(application_owned_commercial_block(analysis)) != 1:
            errors.append("commercial_block_not_application_owned_exact")

    budget_money = _money_signature(analysis.budget or "")
    if budget_money and structured_money and budget_money[2] == structured_money[2]:
        _, budget_high, _ = budget_money
        price_low, _, _ = structured_money
        if budget_high > 0 and price_low > budget_high * 1.5:
            rationale = f"{analysis.reason or ''} {analysis.project_mode_reason or ''}"
            if not _BUDGET_RATIONALE_RE.search(rationale):
                errors.append("price_outside_budget_requires_rationale")

    if evidence_id in {"NO_DIRECT_CASE", "DEMO_REQUIRED"} and (
        _PAST_CAPABILITY_RE.search(body) or _DIRECT_CASE_RE.search(body)
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
    score_semantics = _score_state_for(analysis, "score")
    fit_semantics = _score_state_for(analysis, "fit_score")
    if score_semantics == SCORE_MISSING:
        errors.append("score_missing")
    elif score_semantics == SCORE_INVALID:
        errors.append("score_invalid")
    elif score_semantics == SCORE_FAILED:
        errors.append("score_provider_failed")
    elif score is None:
        errors.append("score_invalid")
    elif score == 0.0:
        errors.append("score_zero_not_proposal_ready")
    if fit_semantics == SCORE_MISSING:
        errors.append("fit_score_missing")
    elif fit_semantics == SCORE_INVALID:
        errors.append("fit_score_invalid")
    elif fit_semantics == SCORE_FAILED:
        errors.append("fit_score_provider_failed")
    elif fit is None:
        errors.append("fit_score_invalid")
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
        errors.extend(_application_owned_proposal_errors(analysis))

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
        analysis.proposal_draft = compose_application_owned_proposal(analysis)
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


def proposal_version(analysis: Any) -> str:
    payload = {
        "analysis_version": _record_value(analysis, "analysis_version") or ANALYSIS_VERSION,
        "evidence_case_id": _record_value(analysis, "evidence_case_id"),
        "fit_score": finite_score(_record_value(analysis, "fit_score", None)),
        "price": _record_value(analysis, "recommended_price"),
        "proposal": _record_value(analysis, "proposal_draft"),
        "score": finite_score(_record_value(analysis, "score", None)),
        "timeline": _record_value(analysis, "realistic_timeline"),
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]
    return f"{PROPOSAL_VERSION_PREFIX}:{digest}"


def proposal_text_hash(text: str) -> str:
    """Bind a persisted direct Response version to the exact text copied."""

    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


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
    proposal = str(getter("proposal_draft", "") or "")
    approved = approved_evidence_text(str(getter("evidence_case_id", "") or ""))
    expected_proposal = compose_application_owned_proposal(record)
    stored_version = str(getter("proposal_version", "") or "")
    return (
        getter("analysis_quality_status", "") in PROPOSAL_READY_QUALITY_STATUSES
        and getter("analysis_version", "") == ANALYSIS_VERSION
        and getter("live_status", "") == "ACTIVE_BIDDABLE"
        and getter("biddable", None) is True
        and -5 <= live_age <= 60
        and str(getter("executable", "")).casefold() == "yes"
        and score_state(
            getter("score", None),
            raw=getter("score_raw", None),
            explicit_state=getter("score_state", ""),
            explicit_valid=getter("score_valid", None),
            analysis_succeeded=getter("analysis_succeeded", True),
        ) == SCORE_VALID
        and score_state(
            getter("fit_score", None),
            raw=getter("fit_score_raw", None),
            explicit_state=getter("fit_score_state", ""),
            explicit_valid=getter("fit_score_valid", None),
            analysis_succeeded=getter("analysis_succeeded", True),
        ) == SCORE_VALID
        and finite_score(getter("score", None)) not in {None, 0.0}
        and finite_score(getter("fit_score", None)) not in {None, 0.0}
        and bool(approved)
        and _normalized_text(str(getter("selected_evidence", "") or ""))
        == _normalized_text(approved)
        and _normalized_text(proposal) == _normalized_text(expected_proposal)
        and stored_version.startswith(f"{PROPOSAL_VERSION_PREFIX}:")
        and stored_version == proposal_version(record)
    )
