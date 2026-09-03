"""Stage 5A AI Sales Closer Copilot.

This is a drafting and audit service only.  It has no dependency on a
Freelancehunt write API and cannot submit bids, send messages, accept a
contract or move money.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta, timezone
from email.utils import parseaddr
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse, urlunparse
from uuid import uuid4
from zoneinfo import ZoneInfo

from .commercial_terms import parse_money_terms, parse_timeline_terms
from .email_analyzer import detect_language
from .gmail_provider import EmailMessage
from .quality_gate import (
    PROPOSAL_READY_QUALITY_STATUSES,
    QualityStatus,
    approved_evidence_text,
    contains_external_contact,
    contains_unsupported_case_or_capability_claim,
)
from .sales_decisions import (
    HumanDecision,
    access_or_contract_errors,
    application_owned_decision_reply,
    application_owned_proof_reply,
    application_owned_sensitive_reply,
    decision_from_request,
    human_decision_errors,
    parse_human_decision,
)
from .sales_storage import (
    ConversationTurn,
    HumanInformationRequest,
    LeadContextSync,
    OpportunityState,
    OwnerActionConfirmation,
    SalesOpportunity,
    SalesRepository,
    TERMINAL_STATES,
    utc_now,
)
from .security import redact_sensitive_content

KYIV = ZoneInfo("Europe/Kyiv")
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_PROJECT_PATH_RE = re.compile(r"/project/(?:[^/?#]+/)?(?P<id>\d+)(?:\.html)?/?$", re.IGNORECASE)
_THREAD_PATH_RE = re.compile(r"/(?:thread|dialog|messages?)/(?P<id>\d+)/?$", re.IGNORECASE)
_MESSAGE_ID_RE = re.compile(r"<[^<>\s]+>")
_MONEY_RE = re.compile(
    r"(?<!\w)(?:\$|€)?\s*\d[\d\s.,-]*\s*(?:USD|EUR|UAH|PLN|грн|зл|zł|\$|€)(?!\w)",
    re.IGNORECASE,
)
_TIMELINE_RE = re.compile(
    r"(?<!\w)\d+(?:\s*[-–]\s*\d+)?\s*"
    r"(?:hours?|days?|weeks?|months?|годин(?:и)?|дн(?:і|ів|я)|тиж(?:день|ні|нів)|"
    r"місяц(?:ь|і|ів)|час(?:а|ов)?|дн(?:я|ей)?|недел(?:я|и|ь)|месяц(?:а|ев)?|"
    r"godzin(?:y)?|dni|tygodni(?:e)?|miesi(?:ąc|ące|ęcy))\b",
    re.IGNORECASE,
)


class ClientIntent(StrEnum):
    CLARIFICATION = "CLARIFICATION"
    TECHNICAL_QUESTION = "TECHNICAL_QUESTION"
    PORTFOLIO_OR_PROOF_REQUEST = "PORTFOLIO_OR_PROOF_REQUEST"
    PRICE_OBJECTION = "PRICE_OBJECTION"
    TIMELINE_OBJECTION = "TIMELINE_OBJECTION"
    SCOPE_CHANGE = "SCOPE_CHANGE"
    CALL_REQUEST = "CALL_REQUEST"
    ACCESS_REQUEST = "ACCESS_REQUEST"
    NEGOTIATION = "NEGOTIATION"
    CLIENT_READY_TO_SELECT = "CLIENT_READY_TO_SELECT"
    SELECTED_OR_CONTRACT_STEP = "SELECTED_OR_CONTRACT_STEP"
    REJECTION = "REJECTION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MessageIdentity:
    project_id: str
    thread_id: str
    project_url: str
    thread_url: str
    message_reference_id: str
    reply_reference_id: str
    canonical_turn_identity: str


@dataclass(slots=True)
class SalesReplyCandidate:
    reply: str
    russian_summary: str
    actual_ask: str
    strategy: str
    risks: str


@dataclass(slots=True)
class SalesProcessResult:
    opportunity: SalesOpportunity
    incoming_turn: ConversationTurn
    reply_turn: ConversationTurn | None
    human_request: HumanInformationRequest | None
    resolution_basis: str
    missing_context: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    duplicate: bool = False
    notification_deferred: bool = False

    @property
    def next_action(self) -> str:
        if self.missing_context:
            return (
                "Preview this exact opportunity and paste one sanitized thread copy: "
                f"/sync_lead_context {self.opportunity.id}"
            )
        if self.human_request is not None:
            return (
                f"Answer one fact: /answer_lead {self.human_request.id} <answer>"
            )
        if self.reply_turn is not None:
            return (
                "Manually send the exact draft in Freelancehunt, then confirm: "
                f"/mark_reply_sent {self.opportunity.id} {self.reply_turn.reply_version}"
            )
        return "Review the client message manually; no platform action was performed."


class SalesCloserError(RuntimeError):
    pass


class UntrustedSalesMessage(SalesCloserError):
    pass


ReplyGenerator = Callable[
    [dict[str, Any], Any | None, list[str] | None], Awaitable[SalesReplyCandidate]
]


def opportunity_id_for(project_id: str = "", project_url: str = "", fallback: str = "") -> str:
    identity = (
        f"project:{project_id.strip()}"
        if project_id.strip()
        else f"url:{safe_freelancehunt_url(project_url)}"
        if safe_freelancehunt_url(project_url)
        else f"source:{fallback.strip()}"
    )
    return "opp_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def opportunity_id_for_analysis(analysis: Any) -> str:
    return opportunity_id_for(
        str(getattr(analysis, "project_id", "") or ""),
        str(getattr(analysis, "url", "") or ""),
        str(getattr(analysis, "email_id", "") or ""),
    )


def safe_freelancehunt_url(value: str) -> str:
    candidate = str(value or "").strip().rstrip(".,);]}")
    try:
        parsed = urlparse(candidate)
    except ValueError:
        return ""
    host = (parsed.hostname or "").casefold().rstrip(".")
    if parsed.scheme.casefold() != "https" or not (
        host == "freelancehunt.com" or host.endswith(".freelancehunt.com")
    ):
        return ""
    return urlunparse(("https", parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def trusted_freelancehunt_sender(sender: str) -> bool:
    address = parseaddr(sender or "")[1].casefold().strip()
    if "@" not in address:
        return False
    domain = address.rsplit("@", 1)[1].rstrip(".")
    return domain == "freelancehunt.com" or domain.endswith(".freelancehunt.com")


def _header_value(headers: dict[str, str], key: str) -> str:
    for name, value in (headers or {}).items():
        if name.casefold() == key.casefold():
            return str(value or "").strip()
    return ""


def _first_message_id(value: str) -> str:
    matches = _MESSAGE_ID_RE.findall(value or "")
    return matches[0].casefold() if matches else str(value or "").strip().casefold()


def extract_message_identity(email: EmailMessage, safe_body: str | None = None) -> MessageIdentity:
    body = safe_body if safe_body is not None else (email.text_body or email.body or "")
    urls: list[str] = []
    for value in [*(email.links or []), *_URL_RE.findall(f"{body}\n{email.html_body or ''}")]:
        safe = safe_freelancehunt_url(value)
        if safe and safe not in urls:
            urls.append(safe)

    project_id = ""
    thread_id = ""
    project_url = ""
    thread_url = ""
    for url in urls:
        path = urlparse(url).path
        project_match = _PROJECT_PATH_RE.search(path)
        thread_match = _THREAD_PATH_RE.search(path)
        if project_match and not project_id:
            project_id = project_match.group("id")
            project_url = url
        if thread_match and not thread_id:
            thread_id = thread_match.group("id")
            thread_url = url

    searchable = f"{email.subject}\n{body}"
    if not project_id:
        match = re.search(
            r"(?:project|проєкт|проект|zlecenie)\s*(?:(?:id)\s*[:#№]?|[#№:])?\s*(\d{4,})",
            searchable,
            re.IGNORECASE,
        )
        project_id = match.group(1) if match else ""
    if not thread_id:
        match = re.search(
            r"(?:thread|dialog|діалог|диалог|wątek)\s*(?:(?:id)\s*[:#№]?|[#№:])?\s*(\d{3,})",
            searchable,
            re.IGNORECASE,
        )
        thread_id = match.group(1) if match else ""

    message_reference = _first_message_id(_header_value(email.raw_headers, "Message-ID"))
    reply_reference = _first_message_id(
        _header_value(email.raw_headers, "In-Reply-To")
        or _header_value(email.raw_headers, "References")
    )
    if message_reference:
        canonical = f"fh-turn:{message_reference}"
    else:
        received = email.received_at.isoformat() if email.received_at else ""
        normalized_body = re.sub(r"\s+", " ", body).strip().casefold()
        material = f"{thread_id}|{project_id}|{received}|{normalized_body}"
        canonical = "fh-turn:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    return MessageIdentity(
        project_id=project_id,
        thread_id=thread_id,
        project_url=project_url,
        thread_url=thread_url,
        message_reference_id=message_reference,
        reply_reference_id=reply_reference,
        canonical_turn_identity=canonical,
    )


def classify_client_intent(text: str) -> ClientIntent:
    value = re.sub(r"\s+", " ", str(text or "")).casefold()
    patterns: tuple[tuple[ClientIntent, tuple[str, ...]], ...] = (
        (ClientIntent.REJECTION, ("not proceed", "not to proceed", "decline", "rejected", "не подходит", "відмов", "не будем", "rezygn", "odrzuc")),
        (
            ClientIntent.SELECTED_OR_CONTRACT_STEP,
            (
                "contract created", "contract was created", "contract and safe are ready",
                "executor selected", "safe payment",
                "funds reserved", "workspace opened", "контракт создан",
                "контракт створено", "исполнитель выбран", "виконавця обрано",
                "средства зарезервированы", "кошти зарезервовано",
                "workspace открыт", "workspace відкрито", "umowa utworzona",
                "wybrano wykonawcę", "środki zarezerwowane", "workspace otwarty",
            ),
        ),
        (ClientIntent.CLIENT_READY_TO_SELECT, ("choose you", "selected you", "ready to start", "обираємо вас", "выбираем вас", "готовы начать", "wybieramy", "zaczynamy")),
        (ClientIntent.PRICE_OBJECTION, ("too expensive", "lower price", "discount", "budget is", "дорого", "дешевле", "знижк", "бюджет", "za drogo", "rabat")),
        (ClientIntent.TIMELINE_OBJECTION, ("too long", "sooner", "faster", "urgent", "быстрее", "срочно", "раніше", "терміново", "szybciej", "pilne")),
        (ClientIntent.SCOPE_CHANGE, ("also add", "additional", "one more", "extra feature", "добавить еще", "додати ще", "дополнительно", "додатков", "dodatkowo", "jeszcze")),
        (ClientIntent.CALL_REQUEST, ("call", "meeting", "zoom", "созвон", "дзвінок", "встреч", "spotkanie", "rozmow")),
        (ClientIntent.ACCESS_REQUEST, ("access", "credentials", "password", "доступ", "парол", "логин", "dostęp", "hasło")),
        (ClientIntent.PORTFOLIO_OR_PROOF_REQUEST, ("portfolio", "case study", "client case", "example", "proof", "портфолио", "кейс", "приклад", "przykład", "realizac")),
        (ClientIntent.TECHNICAL_QUESTION, ("api", "crm", "webhook", "database", "integration", "інтеграц", "техніч", "интеграц", "техничес", "technicz", "integrac")),
        (ClientIntent.NEGOTIATION, ("terms", "milestone", "offer", "услов", "этап", "умов", "етап", "warunk", "etap")),
        (ClientIntent.CLARIFICATION, ("clarify", "explain", "what do you mean", "уточн", "поясн", "doprecyz", "wyjaś")),
    )
    for intent, needles in patterns:
        if any(needle in value for needle in needles):
            return intent
    if "?" in value:
        return ClientIntent.CLARIFICATION
    return ClientIntent.UNKNOWN


def notification_due_at(now: datetime) -> datetime:
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    local = aware.astimezone(KYIV)
    if time(8, 0) <= local.time() < time(21, 0):
        return aware.astimezone(timezone.utc)
    target_date = local.date() if local.time() < time(8, 0) else local.date() + timedelta(days=1)
    target = datetime.combine(target_date, time(8, 0), tzinfo=KYIV)
    return target.astimezone(timezone.utc)


def _normalize_term(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґąćęłńóśźż0-9$€]+", "", value.casefold())


def _detected_reply_language(text: str) -> str:
    value = str(text or "").casefold()
    if re.search(r"[іїєґ]", value):
        return "uk"
    if re.search(r"[ыэъё]", value):
        return "ru"
    if re.search(r"[ąćęłńóśźż]", value) or re.search(
        r"\b(czy|jest|możemy|proszę|termin|dziękuję|dzień|projekt)\b", value
    ):
        return "pl"
    if re.search(r"[а-я]", value):
        uk_words = len(re.findall(r"\b(можемо|потрібно|проєкт|термін|дякую|будь ласка)\b", value))
        ru_words = len(re.findall(r"\b(можем|нужно|проект|срок|спасибо|пожалуйста)\b", value))
        return "uk" if uk_words > ru_words else "ru"
    return "en"


def reply_quality_errors(
    reply: str,
    *,
    opportunity: SalesOpportunity,
    latest_message: str,
    language: str,
    intent: ClientIntent,
    context_complete: bool,
    confirmed_history: list[str] | tuple[str, ...] = (),
    human_decision: HumanDecision | None = None,
    model_owned_text: str = "",
    application_evidence_text: str = "",
    application_owned_text: str = "",
) -> list[str]:
    """Reject unsafe or ungrounded client replies deterministically."""

    text = str(reply or "").strip()
    lowered = text.casefold()
    errors: list[str] = []
    if not context_complete:
        errors.append("required_context_missing")
    if not text:
        errors.append("reply_missing")
        return errors
    if _detected_reply_language(text) != language:
        errors.append("wrong_language")
    if text.count("?") > 1:
        errors.append("more_than_one_question")
    contact_text = model_owned_text or text.replace(
        application_evidence_text, ""
    ).replace(application_owned_text, "")
    if contains_external_contact(contact_text):
        errors.append("external_contact")
    if re.search(r"\b(?:guarantee|promise|100%|гарантир\w*|обещ\w*|гаранту\w*|обіця\w*|gwarantuj\w*)\b", lowered):
        errors.append("unsupported_commitment")
    money_mentions = _MONEY_RE.findall(text)
    allowed_money = {_normalize_term(opportunity.actual_submitted_price)}
    if human_decision and human_decision.canonical_money_json:
        from .commercial_terms import money_terms_from_json

        approved_money = money_terms_from_json(human_decision.canonical_money_json)
        if approved_money:
            allowed_money.add(_normalize_term(approved_money.canonical_model_text()))
    if money_mentions and any(_normalize_term(value) not in allowed_money for value in money_mentions):
        errors.append("price_mismatch")
    timeline_mentions = _TIMELINE_RE.findall(text)
    allowed_timelines = {_normalize_term(opportunity.actual_submitted_timeline)}
    if human_decision and human_decision.canonical_timeline_json:
        from .commercial_terms import timeline_terms_from_json

        approved_timeline = timeline_terms_from_json(
            human_decision.canonical_timeline_json
        )
        if approved_timeline:
            allowed_timelines.add(
                _normalize_term(approved_timeline.canonical_model_text())
            )
    if timeline_mentions and any(_normalize_term(value) not in allowed_timelines for value in timeline_mentions):
        errors.append("unapproved_deadline")
    evidence_claim = re.search(
        r"(?:\b\d+(?:[.,]\d+)?\s*%|\b(?:increased|reduced|grew|achieved|improved)\b|"
        r"(?:увеличил|повысил|достиг|збільшил|покращил|osiągnęli|zwiększyli))",
        lowered,
    )
    approved_evidence = _normalize_term(opportunity.approved_evidence)
    if evidence_claim and (
        not approved_evidence or approved_evidence not in _normalize_term(text)
    ):
        errors.append("invented_case_metric_or_result")
    reply_terms = set(re.findall(r"[\wąćęłńóśźżіїєґ]{4,}", lowered))
    model_body = model_owned_text or text.replace(
        application_evidence_text, ""
    ).replace(application_owned_text, "")
    if contains_unsupported_case_or_capability_claim(model_body):
        errors.append("invented_case_metric_or_result")
    availability_claim = re.search(
        r"(?:i am|we are) available|(?:я|мы) (?:свободен|свободны|доступны)|"
        r"(?:я|ми) (?:вільний|вільні|доступні)|jesteśmy dostępni",
        lowered,
    )
    approved_call = bool(
        human_decision
        and human_decision.intent == ClientIntent.CALL_REQUEST.value
        and human_decision.code == "APPROVED_WINDOWS"
    )
    if availability_claim and not approved_call:
        errors.append("unsupported_commitment")
    history = "\n".join(confirmed_history).casefold()
    if history and (
        (
            re.search(r"\b(?:we can|можем|можемо|możemy)\b", history)
            and re.search(r"\b(?:we cannot|can't|не можем|не можемо|nie możemy)\b", lowered)
        )
        or (
            "included" in history
            and re.search(r"\bnot included\b", lowered)
        )
    ):
        errors.append("contradicts_confirmed_dialogue")
    if intent == ClientIntent.SCOPE_CHANGE and re.search(
        r"(?:included at no extra|for free|free of charge|без доплат|бесплат|безкоштов|za darmo)",
        lowered,
    ):
        errors.append("expanded_scope_accepted_for_free")
    if (
        intent == ClientIntent.SCOPE_CHANGE
        and human_decision is None
        and re.search(
            r"(?:we (?:will )?include|sure.{0,20}include|we(?:'ll| will) add|"
            r"(?:да|так).{0,20}(?:добавим|додамо|зробимо)|dodamy to)",
            lowered,
        )
    ):
        errors.append("scope_inclusion_without_explicit_approval")
    errors.extend(access_or_contract_errors(text, intent.value))
    errors.extend(human_decision_errors(text, human_decision, opportunity))
    latest_without_urls = _URL_RE.sub(" ", latest_message.casefold())
    latest_terms = {
        word
        for word in re.findall(r"[\wąćęłńóśźżіїєґ]{4,}", latest_without_urls)
        if word not in {"please", "could", "would", "можете", "пожалуйста", "будь", "ласка", "proszę"}
    }
    related = bool(latest_terms.intersection(reply_terms)) or any(
        left[:5] == right[:5]
        for left in latest_terms
        for right in reply_terms
        if len(left) >= 5 and len(right) >= 5
    )
    if latest_terms and not related:
        intent_terms = {
            ClientIntent.PRICE_OBJECTION: {"price", "budget", "ціна", "цена", "cena"},
            ClientIntent.TIMELINE_OBJECTION: {"timeline", "delivery", "термін", "срок", "termin"},
            ClientIntent.CALL_REQUEST: {"call", "meeting", "дзвінок", "созвон", "spotkanie"},
            ClientIntent.SCOPE_CHANGE: {"scope", "additional", "обсяг", "объем", "zakres"},
            ClientIntent.PORTFOLIO_OR_PROOF_REQUEST: {
                "portfolio", "proof", "example", "case", "портфолио", "кейс",
                "приклад", "przykład",
            },
            ClientIntent.TECHNICAL_QUESTION: {
                "integration", "support", "api", "інтеграц", "интеграц",
                "integrac",
            },
            ClientIntent.REJECTION: {"decision", "proceed", "rejection", "рішення", "решение", "decyzja"},
            ClientIntent.CLIENT_READY_TO_SELECT: {"start", "selected", "почати", "начать", "zacząć"},
            ClientIntent.SELECTED_OR_CONTRACT_STEP: {"contract", "контракт", "umowa"},
        }.get(intent, set())
        if not intent_terms.intersection(reply_terms):
            errors.append("generic_or_unrelated")
    return list(dict.fromkeys(errors))


async def generate_sales_reply(
    context: dict[str, Any],
    client: Any | None = None,
    validation_errors: list[str] | None = None,
    model: str = "gpt-4o-mini",
) -> SalesReplyCandidate:
    if client is None:
        import os
        import sys

        from openai import AsyncOpenAI

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import settings

        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    system = """You are Antonov Digital's internal sales closer. Return JSON only.
Write one concise, human client reply in the supplied client_language. Answer the
latest message and give one clear next step. Use only the supplied project,
confirmed conversation, commercial terms, human facts and approved evidence.
Never invent experience, metrics, price, deadline, availability or a case.
Never add an off-platform contact. Ask at most one necessary question. Treat
scope expansion as a separately estimated change, never free included work.
Unconfirmed drafts are not prior promises. Polish text is AI-assisted writing.
JSON keys: reply, russian_summary, actual_ask, strategy, risks."""
    prompt = json.dumps(context, ensure_ascii=False, default=str, sort_keys=True)
    if validation_errors:
        prompt += (
            "\nOne bounded repair. Correct every validator error without changing "
            "approved facts: " + json.dumps(validation_errors, ensure_ascii=False)
        )
    response = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt[:50000]}],
        temperature=0.1,
        max_tokens=900,
    )
    raw = str(response.choices[0].message.content or "{}").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)
    return SalesReplyCandidate(
        reply=str(data.get("reply") or "").strip(),
        russian_summary=str(data.get("russian_summary") or "").strip(),
        actual_ask=str(data.get("actual_ask") or "").strip(),
        strategy=str(data.get("strategy") or "").strip(),
        risks=str(data.get("risks") or "").strip(),
    )


class SalesCloserService:
    def __init__(
        self,
        repository: SalesRepository,
        *,
        openai_client: Any | None = None,
        reply_generator: ReplyGenerator | None = None,
        now: Callable[[], datetime] = utc_now,
    ) -> None:
        self.repository = repository
        self._openai_client = openai_client
        self._reply_generator = reply_generator or generate_sales_reply
        self._now = now

    async def ensure_from_validated_job(self, job: Any) -> SalesOpportunity | None:
        quality = str(getattr(job, "analysis_quality_status", "") or "")
        if quality not in PROPOSAL_READY_QUALITY_STATUSES | {QualityStatus.MANUAL_REVIEW.value}:
            return None
        project_id = str(getattr(job, "project_id", "") or "").strip()
        project_url = safe_freelancehunt_url(str(getattr(job, "url", "") or ""))
        fallback = str(getattr(job, "stable_key", "") or getattr(job, "email_id", "") or "")
        identity_key = (
            f"project:{project_id}" if project_id else f"project_url:{project_url}" if project_url else f"job:{fallback}"
        )
        opportunity_id = opportunity_id_for(project_id, project_url, fallback)
        state = OpportunityState.DISCOVERED.value
        ready = quality in PROPOSAL_READY_QUALITY_STATUSES
        score = getattr(job, "score", None)
        fit = getattr(job, "fit_score", None)
        decision = (
            "GO"
            if ready and isinstance(score, (int, float)) and score >= 6
            else "REVIEW"
        )
        risks = "; ".join(
            value
            for value in (
                str(getattr(job, "delivery_risk", "") or ""),
                str(getattr(job, "client_payment_risk", "") or ""),
            )
            if value
        )
        opportunity = SalesOpportunity(
            id=opportunity_id,
            identity_key=identity_key,
            title=str(getattr(job, "title", "") or fallback),
            state=state,
            source=str(getattr(job, "discovery_source", "") or "proposal_quality_gate"),
            gmail_job_key=fallback,
            project_id=project_id,
            thread_id=str(getattr(job, "thread_id", "") or ""),
            project_url=project_url,
            client_name=str(getattr(job, "client_name", "") or ""),
            source_description=str(getattr(job, "full_description", "") or ""),
            description_completeness=str(getattr(job, "description_completeness", "") or "PARTIAL"),
            decision=decision,
            live_status=str(getattr(job, "live_status", "") or ""),
            score=float(score) if isinstance(score, (int, float)) else None,
            fit_score=float(fit) if isinstance(fit, (int, float)) else None,
            competition_signal=(
                f"public bids={job.bid_count}"
                if getattr(job, "bid_count", None) is not None
                else str(getattr(job, "win_probability_signal", "") or "not available")
            ),
            recommended_price=str(getattr(job, "recommended_price", "") or ""),
            recommended_timeline=str(getattr(job, "realistic_timeline", "") or ""),
            risks=risks,
            approved_evidence=str(getattr(job, "selected_evidence", "") or ""),
            evidence_case_id=str(getattr(job, "evidence_case_id", "") or ""),
            initial_proposal=str(getattr(job, "proposal_draft", "") or ""),
            proposal_version=str(getattr(job, "proposal_version", "") or ""),
            proposal_content_sha256=str(getattr(job, "proposal_content_sha256", "") or ""),
        )
        stored, created = await self.repository.ensure_opportunity(
            opportunity,
            reason="validated project discovered by the application-owned quality gate",
            actor="system",
        )
        if not created and stored.state not in {
            OpportunityState.BID_SUBMITTED.value,
            OpportunityState.CLIENT_REPLIED.value,
            OpportunityState.NEEDS_CONTEXT.value,
            OpportunityState.NEEDS_HUMAN_INPUT.value,
            OpportunityState.NEGOTIATING.value,
            OpportunityState.WAITING_CLIENT.value,
            OpportunityState.SELECTED.value,
            OpportunityState.HANDOFF_READY.value,
            OpportunityState.LOST.value,
            OpportunityState.CLOSED.value,
        }:
            stored = await self.repository.update_opportunity_fields(
                stored.id,
                {
                    key: value
                    for key, value in asdict(opportunity).items()
                    if key not in {"id", "identity_key", "state", "created_at", "updated_at"}
                },
            ) or stored
        target = OpportunityState.PROPOSAL_READY if ready else OpportunityState.MANUAL_REVIEW
        if stored.state in {OpportunityState.DISCOVERED.value, OpportunityState.MANUAL_REVIEW.value, OpportunityState.PROPOSAL_READY.value}:
            stored = await self.repository.transition(
                stored.id,
                target.value,
                source="proposal_quality_gate",
                reason=("exact validated proposal package is ready" if ready else "quality gate requires manual review"),
                actor="system",
            )
        return stored

    async def mark_bid_sent(
        self,
        opportunity_id: str,
        proposal_version: str,
        actual_price: str,
        actual_timeline: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
        confirmed_at: datetime | None = None,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        if actor_role != "ADULT_OWNER" or not actor_telegram_user_id:
            raise SalesCloserError("only the actual ADULT_OWNER Telegram actor may confirm a bid")
        raw_price = str(actual_price or "").strip()
        raw_timeline = str(actual_timeline or "").strip()
        money = parse_money_terms(raw_price)
        timeline_terms = parse_timeline_terms(raw_timeline)
        if money is None:
            raise SalesCloserError("actual price is not valid canonical MoneyTerms")
        if timeline_terms is None:
            raise SalesCloserError("actual timeline is not valid canonical TimelineTerms")
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        version = str(proposal_version or "").strip()
        if not version or not opportunity.proposal_version or not opportunity.proposal_content_sha256:
            raise SalesCloserError("exact validated proposal version is unavailable")
        at = confirmed_at or self._now()
        confirmation = OwnerActionConfirmation(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            action="BID_SENT",
            idempotency_key=(
                f"BID_SENT:{opportunity.id}:{version}:{opportunity.proposal_content_sha256}"
            ),
            actor="adult_owner",
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
            proposal_version=version,
            content_sha256=opportunity.proposal_content_sha256,
            actual_price=money.canonical_model_text(),
            actual_timeline=timeline_terms.canonical_model_text(),
            actual_price_raw=raw_price,
            actual_timeline_raw=raw_timeline,
            money_terms_json=money.to_json(),
            timeline_terms_json=timeline_terms.to_json(),
            confirmed_at=at,
        )
        try:
            return await self.repository.confirm_bid(opportunity.id, confirmation)
        except (KeyError, ValueError) as exc:
            raise SalesCloserError(str(exc)) from exc

    async def process_client_message(self, email: EmailMessage) -> SalesProcessResult:
        if not trusted_freelancehunt_sender(email.sender):
            raise UntrustedSalesMessage("CLIENT_PRIVATE_MESSAGE sender is not trusted Freelancehunt mail")
        safe_body, _redacted = redact_sensitive_content(email.text_body or email.body or "")
        identity = extract_message_identity(email, safe_body)
        client_name = _client_name(email.subject)
        resolution = await self.repository.resolve_opportunity(
            thread_id=identity.thread_id,
            project_id=identity.project_id,
            project_url=identity.project_url,
            reply_reference_id=identity.reply_reference_id,
            client_name=client_name,
        )
        opportunity = resolution.opportunity
        if opportunity is None:
            identity_key = (
                f"conflict:{identity.canonical_turn_identity}"
                if resolution.ambiguous
                else f"project:{identity.project_id}"
                if identity.project_id
                else f"thread:{identity.thread_id}"
                if identity.thread_id
                else f"reply:{identity.reply_reference_id}"
                if identity.reply_reference_id
                else f"turn:{identity.canonical_turn_identity}"
            )
            fallback = (
                identity.canonical_turn_identity
                if resolution.ambiguous
                else identity.project_id or identity.thread_id or identity.canonical_turn_identity
            )
            opportunity = SalesOpportunity(
                id=opportunity_id_for(
                    "" if resolution.ambiguous else identity.project_id,
                    "" if resolution.ambiguous else identity.project_url,
                    fallback,
                ),
                identity_key=identity_key,
                title=email.subject or "Unresolved Freelancehunt dialogue",
                source="gmail_private_message",
                project_id="" if resolution.ambiguous else identity.project_id,
                thread_id="" if resolution.ambiguous else identity.thread_id,
                project_url="" if resolution.ambiguous else identity.project_url,
                thread_url="" if resolution.ambiguous else identity.thread_url,
                reply_reference_id=(
                    identity.canonical_turn_identity
                    if resolution.ambiguous
                    else identity.reply_reference_id
                ),
                client_name=client_name,
            )
            opportunity, _created = await self.repository.ensure_opportunity(
                opportunity,
                reason="private message discovered before an exact proposal mapping was available",
                actor="system",
            )
            resolution_basis = resolution.basis
        else:
            resolution_basis = resolution.basis
            binding: dict[str, Any] = {}
            for field_name, value in (
                ("thread_id", identity.thread_id),
                ("thread_url", identity.thread_url),
                ("project_id", identity.project_id),
                ("project_url", identity.project_url),
                ("reply_reference_id", identity.message_reference_id),
                ("client_name", client_name),
            ):
                if value and not getattr(opportunity, field_name):
                    binding[field_name] = value
            if binding:
                opportunity = await self.repository.update_opportunity_fields(opportunity.id, binding) or opportunity

        now = self._now()
        received = email.received_at
        if received and received.tzinfo is None:
            received = received.replace(tzinfo=timezone.utc)
        intent = classify_client_intent(safe_body)
        language = detect_language(f"{email.subject}\n{safe_body}")
        due = notification_due_at(now)
        incoming = ConversationTurn(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            direction="INCOMING",
            content=safe_body,
            content_sha256=_hash_text(safe_body),
            canonical_turn_identity=identity.canonical_turn_identity,
            gmail_message_id=email.id,
            source_reference_id=identity.message_reference_id,
            language=language,
            intent=intent.value,
            source_received_at=received,
            detected_at=now,
            response_latency_seconds=(max(0.0, (now - received).total_seconds()) if received else None),
            notification_due_at=due,
            source="GMAIL",
        )
        incoming, created = await self.repository.add_turn(incoming)
        if not created:
            return await self._result_for_turn(incoming, resolution_basis, duplicate=True)

        for previous_turn in await self.repository.list_turns(opportunity.id):
            if (
                previous_turn.direction == "OUTGOING_DRAFT"
                and previous_turn.source_reference_id != incoming.id
            ):
                await self.repository.update_turn_fields(
                    previous_turn.id, {"direction": "OUTGOING_SUPERSEDED"}
                )

        opportunity = await self.repository.update_opportunity_fields(
            opportunity.id,
            {"last_client_message_at": received or now},
        ) or opportunity
        if opportunity.state in TERMINAL_STATES:
            incoming = await self.repository.update_turn_fields(
                incoming.id,
                {
                    "russian_summary": (
                        "Новое сообщение по terminal opportunity; требуется срочный ручной просмотр."
                    ),
                    "actual_ask": safe_body[:500],
                    "negotiation_strategy": "Не менять terminal state автоматически.",
                    "risks": "Только владелица может отдельно подтвердить изменение terminal state.",
                    "missing_facts": "terminal opportunity requires owner review",
                },
            ) or incoming
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=None,
                resolution_basis=resolution_basis,
                validation_errors=("terminal_state_manual_review",),
                notification_deferred=due > now,
            )
        if opportunity.state in {
            OpportunityState.BID_SUBMITTED.value,
            OpportunityState.WAITING_CLIENT.value,
            OpportunityState.NEGOTIATING.value,
            OpportunityState.NEEDS_CONTEXT.value,
            OpportunityState.NEEDS_HUMAN_INPUT.value,
            OpportunityState.SELECTION_REVIEW.value,
            OpportunityState.CONTRACT_REVIEW.value,
        }:
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.CLIENT_REPLIED.value,
                source="gmail_private_message",
                reason=f"trusted client message stored; intent={intent.value}",
                actor="system",
            )

        missing = self._context_errors(opportunity, resolution_basis)
        if missing or resolution.ambiguous:
            if resolution.ambiguous:
                missing.append("conflicting or ambiguous project/thread mapping")
            incoming = await self.repository.update_turn_fields(
                incoming.id,
                {
                    "missing_facts": "; ".join(missing),
                    "russian_summary": "Контекст диалога нельзя безопасно связать с одной ставкой.",
                    "actual_ask": safe_body[:500],
                    "negotiation_strategy": "Сначала восстановить точную ветку и предыдущие обещания.",
                    "risks": "Ответ без контекста может противоречить ставке.",
                },
            ) or incoming
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.NEEDS_CONTEXT.value,
                source="sales_context_guard",
                reason="; ".join(missing),
                actor="system",
            )
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=None,
                resolution_basis=resolution_basis,
                missing_context=tuple(missing),
                notification_deferred=due > now,
            )

        request_spec = self._required_human_fact(opportunity, incoming, intent)
        if request_spec is not None:
            fact_key, question = request_spec
            request, _created = await self.repository.create_human_request(
                HumanInformationRequest(
                    id="hir_" + uuid4().hex[:16],
                    opportunity_id=opportunity.id,
                    source_turn_id=incoming.id,
                    fact_key=fact_key,
                    intent=intent.value,
                    subject_fingerprint=_subject_fingerprint(incoming.content, intent),
                    question=question,
                    asked_at=now,
                )
            )
            questions = _json_list(opportunity.unresolved_questions_json)
            if question not in questions:
                questions.append(question)
                opportunity = await self.repository.update_opportunity_fields(
                    opportunity.id,
                    {
                        "unresolved_questions_json": json.dumps(
                            questions, ensure_ascii=False
                        )
                    },
                ) or opportunity
            incoming = await self.repository.update_turn_fields(
                incoming.id,
                {
                    "missing_facts": question,
                    "russian_summary": _fallback_russian_summary(intent),
                    "actual_ask": safe_body[:500],
                    "negotiation_strategy": "Получить один факт и затем подготовить проверенный ответ.",
                    "risks": "Нельзя честно подтвердить неизвестный факт.",
                },
            ) or incoming
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.NEEDS_HUMAN_INPUT.value,
                source="sales_human_fact_guard",
                reason=f"missing human fact: {fact_key}",
                actor="system",
            )
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=request,
                resolution_basis=resolution_basis,
                notification_deferred=due > now,
            )

        reply, errors = await self._generate_and_store(opportunity, incoming, intent)
        opportunity = await self.repository.get_opportunity(opportunity.id) or opportunity
        return SalesProcessResult(
            opportunity=opportunity,
            incoming_turn=await self.repository.get_turn(incoming.id) or incoming,
            reply_turn=reply,
            human_request=None,
            resolution_basis=resolution_basis,
            validation_errors=tuple(errors),
            notification_deferred=due > now,
        )

    async def answer_human_request(
        self,
        request_id: str,
        answer: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> SalesProcessResult:
        if actor_role not in {"ARTEM", "VADIM"} or not actor_telegram_user_id:
            raise SalesCloserError("only the actual ARTEM or VADIM Telegram actor may answer")
        value = str(answer or "").strip()
        if not value:
            raise SalesCloserError("answer is required")
        request = await self.repository.get_human_request(request_id)
        if request is None:
            raise SalesCloserError("human information request not found")
        opportunity = await self.repository.get_opportunity(request.opportunity_id)
        incoming = await self.repository.get_turn(request.source_turn_id)
        if opportunity is None or incoming is None:
            raise SalesCloserError("request context is unavailable")
        try:
            decision = parse_human_decision(request, value)
        except ValueError as exc:
            raise SalesCloserError(str(exc)) from exc
        if request.status == "ANSWERED" and (
            request.answer_code != decision.code or request.answer_text != decision.text
        ):
            raise SalesCloserError("request was already answered with a different fact")
        if request.status == "ANSWERED" and request.resulting_reply_version:
            return await self._result_for_turn(incoming, "human_answer", duplicate=True)
        questions = [
            item
            for item in _json_list(opportunity.unresolved_questions_json)
            if item != request.question
        ]
        decisions = _json_list(opportunity.decisions_json)
        if not any(
            isinstance(item, dict)
            and item.get("request_id") == request.id
            and item.get("answer_code") == decision.code
            for item in decisions
        ):
            decisions.append(
                {
                    "source": actor_role,
                    "request_id": request.id,
                    "source_turn_id": incoming.id,
                    "intent": request.intent,
                    "subject_fingerprint": request.subject_fingerprint,
                    "fact_key": request.fact_key,
                    "answer_code": decision.code,
                    "answer_text": decision.text,
                    "recorded_at": self._now().isoformat(),
                }
            )
        opportunity = await self.repository.update_opportunity_fields(
            opportunity.id,
            {
                "unresolved_questions_json": json.dumps(questions, ensure_ascii=False),
                "decisions_json": json.dumps(decisions, ensure_ascii=False),
            },
        ) or opportunity
        answer_fields = {
            "status": "ANSWERED",
            "answer": value,
            "answer_code": decision.code,
            "answer_text": decision.text,
            "canonical_money_json": decision.canonical_money_json,
            "canonical_timeline_json": decision.canonical_timeline_json,
            "approved_availability_json": decision.approved_availability_json,
            "approved_evidence_case_id": decision.approved_evidence_case_id,
            "answered_at": self._now(),
            "answered_by": "Artem" if actor_role == "ARTEM" else "Vadim",
            "answered_by_role": actor_role,
            "answered_by_telegram_user_id": actor_telegram_user_id,
        }
        request = await self.repository.update_human_request(
            request.id, answer_fields
        ) or request
        await self.repository.acknowledge_turn(
            incoming.id,
            at=self._now(),
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        existing_turns = await self.repository.list_turns(opportunity.id)
        recovered_reply = next(
            (
                turn
                for turn in reversed(existing_turns)
                if turn.source_reference_id == incoming.id
                and turn.direction in {"OUTGOING_DRAFT", "OUTGOING_CONFIRMED"}
            ),
            None,
        )
        if recovered_reply is not None:
            request = await self.repository.update_human_request(
                request.id,
                {
                    "resulting_reply_version": recovered_reply.reply_version,
                },
            ) or request
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=recovered_reply,
                human_request=request,
                resolution_basis="human_answer_restart_reconcile",
                duplicate=True,
            )
        intent = ClientIntent(incoming.intent)
        reply, errors = await self._generate_and_store(
            opportunity, incoming, intent, human_decision=decision
        )
        if reply is None:
            return SalesProcessResult(
                opportunity=await self.repository.get_opportunity(opportunity.id) or opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=request,
                resolution_basis="human_answer",
                validation_errors=tuple(errors),
            )
        request = await self.repository.update_human_request(
            request.id,
            {
                "resulting_reply_version": reply.reply_version,
            },
        ) or request
        return SalesProcessResult(
            opportunity=await self.repository.get_opportunity(opportunity.id) or opportunity,
            incoming_turn=await self.repository.get_turn(incoming.id) or incoming,
            reply_turn=reply,
            human_request=request,
            resolution_basis="human_answer",
        )

    async def mark_reply_sent(
        self,
        opportunity_id: str,
        reply_version: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
        confirmed_at: datetime | None = None,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        if actor_role != "ADULT_OWNER" or not actor_telegram_user_id:
            raise SalesCloserError(
                "only the actual ADULT_OWNER Telegram actor may confirm a reply"
            )
        try:
            return await self.repository.confirm_reply(
                opportunity_id,
                str(reply_version or "").strip(),
                actor="adult_owner",
                actor_role=actor_role,
                actor_telegram_user_id=actor_telegram_user_id,
                confirmed_at=confirmed_at or self._now(),
            )
        except (KeyError, ValueError, RuntimeError) as exc:
            raise SalesCloserError(str(exc)) from exc

    async def pending_cards(self) -> list[SalesProcessResult]:
        turns = await self.repository.list_pending_incoming_turns(self._now())
        return [await self._result_for_turn(turn, "pending_notification") for turn in turns]

    async def mark_notified(self, turn_id: str) -> None:
        await self.repository.mark_turn_notified(turn_id, self._now())

    async def acknowledge_lead(
        self,
        incoming_turn_id: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> ConversationTurn:
        if actor_role not in {"ADULT_OWNER", "ARTEM", "VADIM"} or not actor_telegram_user_id:
            raise SalesCloserError("only an authorized team role may acknowledge a lead")
        turn = await self.repository.acknowledge_turn(
            incoming_turn_id,
            at=self._now(),
            actor_role=actor_role,
            actor_telegram_user_id=actor_telegram_user_id,
        )
        if turn is None:
            raise SalesCloserError("incoming turn not found")
        return turn

    async def pending_escalations(self) -> list[ConversationTurn]:
        return await self.repository.list_pending_escalations(self._now())

    async def mark_escalated(self, turn_id: str) -> None:
        await self.repository.mark_turn_escalated(turn_id, self._now())

    async def begin_context_sync(
        self,
        opportunity_id: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> tuple[LeadContextSync, SalesOpportunity]:
        if actor_role not in {"ADULT_OWNER", "ARTEM"} or not actor_telegram_user_id:
            raise SalesCloserError("only an authorized team role may sync context")
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        sync, _created = await self.repository.create_context_sync(
            LeadContextSync(
                id="sync_" + uuid4().hex[:16],
                opportunity_id=opportunity_id,
                status="PENDING",
                requested_at=self._now(),
                requested_by_role=actor_role,
                requested_by_telegram_user_id=actor_telegram_user_id,
            )
        )
        turns = await self.repository.list_turns(opportunity_id)
        latest_incoming = next(
            (turn for turn in reversed(turns) if turn.direction == "INCOMING"), None
        )
        if latest_incoming is not None:
            await self.repository.acknowledge_turn(
                latest_incoming.id,
                at=self._now(),
                actor_role=actor_role,
                actor_telegram_user_id=actor_telegram_user_id,
            )
        return sync, opportunity

    async def cancel_context_sync(
        self,
        actor_telegram_user_id: int,
        *,
        actor_role: str,
    ) -> bool:
        if actor_role not in {"ADULT_OWNER", "ARTEM", "VADIM"} or not actor_telegram_user_id:
            raise SalesCloserError("only an authorized team role may cancel context sync")
        sync = await self.repository.get_pending_context_sync(actor_telegram_user_id)
        if sync is None:
            return False
        await self.repository.update_context_sync(sync.id, {"status": "CANCELLED"})
        return True

    async def import_context(
        self,
        copied_text: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> SalesProcessResult:
        if actor_role not in {"ADULT_OWNER", "ARTEM"} or not actor_telegram_user_id:
            raise SalesCloserError("only an authorized team role may import context")
        sync = await self.repository.get_pending_context_sync(actor_telegram_user_id)
        if sync is None:
            raise SalesCloserError("no pending /sync_lead_context request")
        raw = str(copied_text or "")
        if not raw.strip() or len(raw) > 12000 or any(
            ord(char) < 32 and char not in "\r\n\t" for char in raw
        ):
            raise SalesCloserError("copied context must be plain text up to 12000 characters")
        safe_text, redacted = redact_sensitive_content(raw)
        safe_text = _redact_access_secrets(safe_text)
        project_ids, thread_ids = _copied_identity_values(safe_text)
        if len(project_ids) > 1 or len(thread_ids) > 1:
            raise SalesCloserError(
                "copied context contains more than one opportunity identity"
            )
        opportunity = await self.repository.get_opportunity(sync.opportunity_id)
        if opportunity is None:
            raise SalesCloserError("sync opportunity not found")
        imported_identity = _identity_from_copied_text(safe_text)
        resolution = await self.repository.resolve_opportunity(
            thread_id=imported_identity.thread_id,
            project_id=imported_identity.project_id,
            project_url=imported_identity.project_url,
        )
        if resolution.opportunity is not None and resolution.opportunity.id != opportunity.id:
            raise SalesCloserError("copied context belongs to a different opportunity")
        for field_name, current, imported in (
            ("project_id", opportunity.project_id, imported_identity.project_id),
            ("thread_id", opportunity.thread_id, imported_identity.thread_id),
            ("project_url", opportunity.project_url, imported_identity.project_url),
            ("thread_url", opportunity.thread_url, imported_identity.thread_url),
        ):
            if current and imported and current != imported:
                raise SalesCloserError(f"copied context conflicts with opportunity {field_name}")
        bindings = {
            field_name: imported
            for field_name, current, imported in (
                ("project_id", opportunity.project_id, imported_identity.project_id),
                ("thread_id", opportunity.thread_id, imported_identity.thread_id),
                ("project_url", opportunity.project_url, imported_identity.project_url),
                ("thread_url", opportunity.thread_url, imported_identity.thread_url),
            )
            if imported and not current
        }
        if bindings:
            opportunity = await self.repository.update_opportunity_fields(
                opportunity.id, bindings
            ) or opportunity
        imported_at = self._now()
        imported_turn, _created = await self.repository.add_turn(
            ConversationTurn(
                id=uuid4().hex,
                opportunity_id=opportunity.id,
                direction="UNKNOWN_DIRECTION",
                content=safe_text,
                content_sha256=_hash_text(safe_text),
                canonical_turn_identity=(
                    f"owner-copy:{opportunity.id}:{_hash_text(safe_text)}"
                ),
                source="OWNER_COPIED_THREAD",
                imported_at=imported_at,
                imported_by_role=actor_role,
                imported_by_telegram_user_id=actor_telegram_user_id,
            )
        )
        await self.repository.update_context_sync(
            sync.id,
            {
                "status": "IMPORTED",
                "imported_at": imported_at,
                "content_sha256": imported_turn.content_sha256,
                "redaction_applied": redacted or safe_text != raw,
            },
        )
        turns = await self.repository.list_turns(opportunity.id)
        incoming = next(
            (turn for turn in reversed(turns) if turn.direction == "INCOMING"), None
        )
        if incoming is None:
            raise SalesCloserError("no incoming client turn exists for regeneration")
        missing = self._context_errors(opportunity, "OWNER_COPIED_THREAD")
        if missing:
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=None,
                resolution_basis="OWNER_COPIED_THREAD",
                missing_context=tuple(missing),
            )
        if opportunity.state == OpportunityState.NEEDS_CONTEXT.value:
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.CLIENT_REPLIED.value,
                source="telegram:/sync_lead_context",
                reason="sanitized owner-copied thread context imported for exact opportunity",
                actor="adult_owner" if actor_role == "ADULT_OWNER" else "Artem" if actor_role == "ARTEM" else "Vadim",
                actor_role=actor_role,
                actor_telegram_user_id=actor_telegram_user_id,
            )
        request_spec = self._required_human_fact(opportunity, incoming, ClientIntent(incoming.intent))
        if request_spec is not None:
            request, _created = await self.repository.create_human_request(
                HumanInformationRequest(
                    id="hir_" + uuid4().hex[:16],
                    opportunity_id=opportunity.id,
                    source_turn_id=incoming.id,
                    fact_key=request_spec[0],
                    intent=incoming.intent,
                    subject_fingerprint=_subject_fingerprint(
                        incoming.content, ClientIntent(incoming.intent)
                    ),
                    question=request_spec[1],
                    asked_at=self._now(),
                )
            )
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.NEEDS_HUMAN_INPUT.value,
                source="sales_human_fact_guard",
                reason=f"missing turn-scoped decision: {request.fact_key}",
                actor="system",
            )
            return SalesProcessResult(
                opportunity=opportunity,
                incoming_turn=incoming,
                reply_turn=None,
                human_request=request,
                resolution_basis="OWNER_COPIED_THREAD",
            )
        reply, errors = await self._generate_and_store(
            opportunity,
            incoming,
            ClientIntent(incoming.intent),
            allow_repair=False,
        )
        return SalesProcessResult(
            opportunity=await self.repository.get_opportunity(opportunity.id) or opportunity,
            incoming_turn=incoming,
            reply_turn=reply,
            human_request=None,
            resolution_basis="OWNER_COPIED_THREAD",
            validation_errors=tuple(errors),
        )

    async def regenerate_latest_reply(
        self,
        opportunity_id: str,
        *,
        actor_role: str,
        actor_telegram_user_id: int,
    ) -> SalesProcessResult:
        if actor_role not in {"ADULT_OWNER", "ARTEM", "VADIM"} or not actor_telegram_user_id:
            raise SalesCloserError("only an authorized team role may regenerate a reply")
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        turns = await self.repository.list_turns(opportunity_id)
        incoming = next(
            (turn for turn in reversed(turns) if turn.direction == "INCOMING"), None
        )
        if incoming is None:
            raise SalesCloserError("latest incoming turn not found")
        for turn in turns:
            if turn.direction == "OUTGOING_DRAFT":
                await self.repository.update_turn_fields(
                    turn.id, {"direction": "OUTGOING_SUPERSEDED"}
                )
        requests = await self.repository.list_human_requests(opportunity_id)
        decision = next(
            (
                decision_from_request(request)
                for request in reversed(requests)
                if request.source_turn_id == incoming.id and request.status == "ANSWERED"
            ),
            None,
        )
        if self._required_human_fact(opportunity, incoming, ClientIntent(incoming.intent)) and decision is None:
            raise SalesCloserError("latest incoming turn still needs a structured human decision")
        reply, errors = await self._generate_and_store(
            opportunity,
            incoming,
            ClientIntent(incoming.intent),
            human_decision=decision,
        )
        return SalesProcessResult(
            opportunity=await self.repository.get_opportunity(opportunity.id) or opportunity,
            incoming_turn=incoming,
            reply_turn=reply,
            human_request=None,
            resolution_basis="authorized_regeneration",
            validation_errors=tuple(errors),
        )

    async def pipeline_counts(self) -> dict[str, int]:
        return await self.repository.pipeline_counts()

    async def lead_timeline(
        self, opportunity_id: str
    ) -> tuple[SalesOpportunity, list[Any], list[ConversationTurn], list[HumanInformationRequest]]:
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        return (
            opportunity,
            await self.repository.list_transitions(opportunity_id),
            await self.repository.list_turns(opportunity_id),
            await self.repository.list_human_requests(opportunity_id),
        )

    def _context_errors(self, opportunity: SalesOpportunity, resolution_basis: str) -> list[str]:
        missing: list[str] = []
        if resolution_basis in {"unresolved", "ambiguous_client_name_hint", "conflicting_authoritative_identifiers"}:
            missing.append("exact project/thread mapping")
        if not opportunity.source_description:
            missing.append("source project description")
        if not opportunity.description_completeness:
            missing.append("description completeness")
        if not opportunity.initial_proposal or not opportunity.proposal_version:
            missing.append("exact submitted proposal/version")
        if not opportunity.actual_submitted_price:
            missing.append("actual submitted price")
        if not opportunity.actual_submitted_timeline:
            missing.append("actual submitted timeline")
        if opportunity.bid_submitted_at is None:
            missing.append("owner bid confirmation")
        return missing

    def _required_human_fact(
        self,
        opportunity: SalesOpportunity,
        incoming: ConversationTurn,
        intent: ClientIntent,
    ) -> tuple[str, str] | None:
        specs = {
            ClientIntent.TECHNICAL_QUESTION: (
                "technical_capability",
                "Подтвердите только этот запрос: YES | NO | NEED_DOCS.",
            ),
            ClientIntent.PRICE_OBJECTION: (
                "minimum_price",
                "Решение по цене: KEEP_CURRENT_PRICE или COUNTER_PRICE | <MoneyTerms>.",
            ),
            ClientIntent.TIMELINE_OBJECTION: (
                "earliest_delivery",
                "Решение по сроку: KEEP_CURRENT_TIMELINE или EARLIEST_TIMELINE | <TimelineTerms>.",
            ),
            ClientIntent.SCOPE_CHANGE: (
                "scope_change_decision",
                "Решение по новому требованию: INCLUDE_IN_CURRENT_SCOPE | SEPARATE_PAID_ESTIMATE | DECLINE.",
            ),
            ClientIntent.CALL_REQUEST: (
                "call_availability",
                "Решение по звонку: APPROVED_WINDOWS | <exact windows>, NOT_AVAILABLE или NEED_CLIENT_OPTIONS.",
            ),
        }
        if intent == ClientIntent.PORTFOLIO_OR_PROOF_REQUEST and (
            not opportunity.approved_evidence or opportunity.evidence_case_id in {"", "NO_DIRECT_CASE", "DEMO_REQUIRED"}
        ):
            specs[intent] = (
                "direct_case_availability",
                "Выберите approved evidence_case_id, NO_DIRECT_CASE или DEMO_REQUIRED.",
            )
        spec = specs.get(intent)
        return spec

    async def _generate_and_store(
        self,
        opportunity: SalesOpportunity,
        incoming: ConversationTurn,
        intent: ClientIntent,
        *,
        human_decision: HumanDecision | None = None,
        allow_repair: bool = True,
    ) -> tuple[ConversationTurn | None, list[str]]:
        turns = await self.repository.list_turns(opportunity.id)
        context = self._full_context(
            opportunity, turns, incoming, intent, human_decision=human_decision
        )
        candidate: SalesReplyCandidate | None = None
        errors: list[str] = []
        application_evidence = ""
        fixed_reply = (
            application_owned_decision_reply(
                human_decision, incoming.language, opportunity
            )
            if human_decision is not None
            else application_owned_sensitive_reply(intent.value, incoming.language)
        )
        if fixed_reply is None and intent == ClientIntent.PORTFOLIO_OR_PROOF_REQUEST:
            application_evidence = approved_evidence_text(
                opportunity.evidence_case_id, incoming.language
            )
            fixed_reply = application_owned_proof_reply(
                opportunity.evidence_case_id, incoming.language
            )
        attempts = 1 if fixed_reply is not None or not allow_repair else 2
        for attempt in range(attempts):
            model_errors: list[str] = []
            if fixed_reply is not None:
                candidate = SalesReplyCandidate(
                    reply=fixed_reply,
                    russian_summary=_fallback_russian_summary(intent),
                    actual_ask=incoming.content[:500],
                    strategy="Application-owned deterministic response for the exact current turn.",
                    risks="No unconfirmed commitment or platform action.",
                )
                model_owned = ""
            else:
                try:
                    candidate = await self._reply_generator(
                        context,
                        self._openai_client,
                        errors if attempt else None,
                    )
                except Exception as exc:  # noqa: BLE001 - provider failures are fail-closed
                    errors = [f"reply_provider_failed:{type(exc).__name__}"]
                    break
                model_owned = candidate.reply
                if contains_unsupported_case_or_capability_claim(model_owned):
                    model_errors.append("model_owned_case_or_capability_claim")
            errors = list(
                dict.fromkeys(
                    model_errors
                    + reply_quality_errors(
                        candidate.reply,
                        opportunity=opportunity,
                        latest_message=incoming.content,
                        language=incoming.language,
                        intent=intent,
                        context_complete=True,
                        confirmed_history=[
                            turn.content
                            for turn in turns
                            if turn.direction == "OUTGOING_CONFIRMED"
                        ],
                        human_decision=human_decision,
                        model_owned_text=model_owned,
                        application_evidence_text=application_evidence,
                        application_owned_text=fixed_reply or "",
                    )
                )
            )
            if not errors:
                break
            await self.repository.add_turn(
                ConversationTurn(
                    id=uuid4().hex,
                    opportunity_id=opportunity.id,
                    direction="OUTGOING_REJECTED",
                    content=candidate.reply,
                    content_sha256=_hash_text(candidate.reply),
                    canonical_turn_identity=f"rejected:{opportunity.id}:{incoming.id}:{attempt}:{_hash_text(candidate.reply)}",
                    source_reference_id=incoming.id,
                    incoming_gmail_message_id=incoming.gmail_message_id,
                    incoming_canonical_identity=incoming.canonical_turn_identity,
                    generated_at=self._now(),
                    language=incoming.language,
                    intent=intent.value,
                    russian_summary=candidate.russian_summary,
                    actual_ask=candidate.actual_ask,
                    negotiation_strategy=candidate.strategy,
                    risks=candidate.risks,
                    missing_facts=",".join(errors),
                )
            )
        if candidate is None or errors:
            current = await self.repository.get_opportunity(opportunity.id)
            if current and current.state not in TERMINAL_STATES:
                await self.repository.transition(
                    opportunity.id,
                    OpportunityState.MANUAL_REVIEW.value,
                    source="sales_reply_validator",
                    reason="; ".join(errors or ["reply generation failed"]),
                    actor="system",
                )
            return None, errors

        version = await self.repository.allocate_reply_version(opportunity.id)
        generated_at = self._now()
        draft = ConversationTurn(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            direction="OUTGOING_DRAFT",
            content=candidate.reply,
            content_sha256=_hash_text(candidate.reply),
            canonical_turn_identity=f"draft:{opportunity.id}:{version}:{_hash_text(candidate.reply)}",
            source_reference_id=incoming.id,
            reply_version=version,
            incoming_gmail_message_id=incoming.gmail_message_id,
            incoming_canonical_identity=incoming.canonical_turn_identity,
            generated_at=generated_at,
            language=incoming.language,
            intent=intent.value,
            russian_summary=candidate.russian_summary,
            actual_ask=candidate.actual_ask,
            negotiation_strategy=candidate.strategy,
            risks=candidate.risks,
        )
        draft, _created = await self.repository.add_reply_draft_if_current(draft)
        await self.repository.update_turn_fields(
            incoming.id,
            {
                "russian_summary": candidate.russian_summary,
                "actual_ask": candidate.actual_ask,
                "negotiation_strategy": candidate.strategy,
                "risks": candidate.risks,
            },
        )
        if draft.direction == "OUTGOING_SUPERSEDED":
            return None, ["newer_incoming_turn"]
        target = (
            OpportunityState.LOST
            if intent == ClientIntent.REJECTION
            else OpportunityState.SELECTION_REVIEW
            if intent == ClientIntent.CLIENT_READY_TO_SELECT
            else OpportunityState.CONTRACT_REVIEW
            if intent == ClientIntent.SELECTED_OR_CONTRACT_STEP
            else OpportunityState.NEGOTIATING
        )
        await self.repository.transition(
            opportunity.id,
            target.value,
            source="sales_reply_generator",
            reason=f"validated reply {version} prepared for intent={intent.value}; not sent",
            actor="system",
        )
        return draft, []

    def _full_context(
        self,
        opportunity: SalesOpportunity,
        turns: list[ConversationTurn],
        incoming: ConversationTurn,
        intent: ClientIntent,
        *,
        human_decision: HumanDecision | None = None,
    ) -> dict[str, Any]:
        confirmed = [
            {
                "direction": turn.direction,
                "content": turn.content,
                "sent_at": turn.sent_at,
                "reply_version": turn.reply_version,
            }
            for turn in turns
            if turn.direction in {
                "INCOMING", "OUTGOING_CONFIRMED", "UNKNOWN_DIRECTION"
            }
        ]
        return {
            "opportunity_id": opportunity.id,
            "current_state": opportunity.state,
            "project_title": opportunity.title,
            "source_project_description": opportunity.source_description,
            "description_completeness": opportunity.description_completeness,
            "initial_submitted_proposal": opportunity.initial_proposal,
            "submitted_proposal_version": opportunity.proposal_version,
            "actual_submitted_price": opportunity.actual_submitted_price,
            "actual_submitted_timeline": opportunity.actual_submitted_timeline,
            "confirmed_conversation": confirmed,
            "client_constraints": _json_list(opportunity.client_constraints_json),
            "decisions": _json_list(opportunity.decisions_json),
            "unresolved_questions": _json_list(opportunity.unresolved_questions_json),
            "current_turn_human_decision": (
                asdict(human_decision) if human_decision is not None else None
            ),
            "approved_evidence": opportunity.approved_evidence,
            "evidence_case_id": opportunity.evidence_case_id,
            "latest_message": incoming.content,
            "client_language": incoming.language,
            "deterministic_intent": intent.value,
        }

    async def _result_for_turn(
        self, incoming: ConversationTurn, basis: str, duplicate: bool = False
    ) -> SalesProcessResult:
        opportunity = await self.repository.get_opportunity(incoming.opportunity_id)
        if opportunity is None:
            raise SalesCloserError("turn opportunity disappeared")
        turns = await self.repository.list_turns(opportunity.id)
        reply = next(
            (
                item
                for item in reversed(turns)
                if item.source_reference_id == incoming.id
                and item.direction in {"OUTGOING_DRAFT", "OUTGOING_CONFIRMED"}
            ),
            None,
        )
        requests = await self.repository.list_human_requests(opportunity.id)
        request = next(
            (item for item in reversed(requests) if item.source_turn_id == incoming.id and item.status == "OPEN"),
            None,
        )
        missing = tuple(filter(None, (incoming.missing_facts or "").split("; ")))
        return SalesProcessResult(
            opportunity=opportunity,
            incoming_turn=incoming,
            reply_turn=reply,
            human_request=request,
            resolution_basis=basis,
            missing_context=missing if opportunity.state == OpportunityState.NEEDS_CONTEXT.value else (),
            duplicate=duplicate,
            notification_deferred=bool(incoming.notification_due_at and incoming.notification_due_at > self._now()),
        )


def _client_name(subject: str) -> str:
    value = str(subject or "").strip()
    match = re.search(r"(?:from|від|от|od)\s+([^:|—-]{2,80})", value, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _fallback_russian_summary(intent: ClientIntent) -> str:
    labels = {
        ClientIntent.TECHNICAL_QUESTION: "Клиент задаёт технический вопрос.",
        ClientIntent.PRICE_OBJECTION: "Клиент возражает по цене.",
        ClientIntent.TIMELINE_OBJECTION: "Клиент просит изменить срок.",
        ClientIntent.SCOPE_CHANGE: "Клиент расширяет исходный объём.",
        ClientIntent.CALL_REQUEST: "Клиент предлагает звонок.",
        ClientIntent.PORTFOLIO_OR_PROOF_REQUEST: "Клиент просит доказательство или кейс.",
    }
    return labels.get(intent, "Клиент ждёт конкретный ответ.")


def _hash_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _subject_fingerprint(text: str, intent: ClientIntent) -> str:
    normalized = " ".join(str(text or "").casefold().split())
    return hashlib.sha256(f"{intent.value}\n{normalized}".encode("utf-8")).hexdigest()


def _redact_access_secrets(value: str) -> str:
    """Remove copied credential values without retaining the original secret."""

    text = str(value or "")
    labels = (
        r"password|passwd|pwd|otp|2fa|one[- ]time code|recovery code|"
        r"api[_ -]?key|api[_ -]?secret|client[_ -]?secret|access[_ -]?token|"
        r"парол(?:ь|я)|одноразов(?:ый|ий) код|код восстановления|"
        r"секрет(?:ный)? ключ|токен|hasło|kod jednorazowy|tajny klucz"
    )
    return re.sub(
        rf"(?im)\b({labels})\b\s*[:=]\s*[^\s,;]+",
        r"\1: [REDACTED]",
        text,
    )


def _identity_from_copied_text(value: str) -> MessageIdentity:
    text = str(value or "")
    synthetic = EmailMessage(
        id="owner-copied-thread",
        subject="Owner-copied Freelancehunt thread",
        sender="notify@freelancehunt.com",
        body=text,
        received_at=None,
        text_body=text,
        links=_URL_RE.findall(text),
    )
    return extract_message_identity(synthetic, text)


def _copied_identity_values(value: str) -> tuple[set[str], set[str]]:
    text = str(value or "")
    project_ids = set(
        re.findall(
            r"(?:project|проєкт|проект|zlecenie)\s*"
            r"(?:(?:id)\s*[:#№]?|[#№:])?\s*(\d{4,})",
            text,
            re.IGNORECASE,
        )
    )
    thread_ids = set(
        re.findall(
            r"(?:thread|dialog|діалог|диалог|wątek)\s*"
            r"(?:(?:id)\s*[:#№]?|[#№:])?\s*(\d{3,})",
            text,
            re.IGNORECASE,
        )
    )
    for value in _URL_RE.findall(text):
        safe = safe_freelancehunt_url(value)
        if not safe:
            continue
        path = urlparse(safe).path
        project_match = _PROJECT_PATH_RE.search(path)
        thread_match = _THREAD_PATH_RE.search(path)
        if project_match:
            project_ids.add(project_match.group("id"))
        if thread_match:
            thread_ids.add(thread_match.group("id"))
    return project_ids, thread_ids


def _next_reply_version(turns: list[ConversationTurn]) -> str:
    versions = []
    for turn in turns:
        match = re.fullmatch(r"r(\d+)", turn.reply_version or "")
        if match:
            versions.append(int(match.group(1)))
    return f"r{max(versions, default=0) + 1}"


def _json_list(value: str) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
        return list(parsed) if isinstance(parsed, list) else []
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
