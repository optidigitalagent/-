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

from .email_analyzer import detect_language
from .gmail_provider import EmailMessage
from .quality_gate import PROPOSAL_READY_QUALITY_STATUSES, QualityStatus
from .sales_storage import (
    ConversationTurn,
    HumanInformationRequest,
    OpportunityState,
    OwnerActionConfirmation,
    SalesOpportunity,
    SalesRepository,
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
            return "Open and sync the exact Freelancehunt thread before drafting a reply."
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
        (ClientIntent.SELECTED_OR_CONTRACT_STEP, ("contract", "safe", "escrow", "контракт", "сейф", "резерв", "umow", "depozyt")),
        (ClientIntent.CLIENT_READY_TO_SELECT, ("choose you", "selected you", "ready to start", "обираємо вас", "выбираем вас", "готовы начать", "wybieramy", "zaczynamy")),
        (ClientIntent.PRICE_OBJECTION, ("too expensive", "lower price", "discount", "budget is", "дорого", "дешевле", "знижк", "бюджет", "za drogo", "rabat")),
        (ClientIntent.TIMELINE_OBJECTION, ("too long", "sooner", "faster", "urgent", "быстрее", "срочно", "раніше", "терміново", "szybciej", "pilne")),
        (ClientIntent.SCOPE_CHANGE, ("also add", "additional", "one more", "extra feature", "добавить еще", "додати ще", "дополнительно", "додатков", "dodatkowo", "jeszcze")),
        (ClientIntent.CALL_REQUEST, ("call", "meeting", "zoom", "созвон", "дзвінок", "встреч", "spotkanie", "rozmow")),
        (ClientIntent.ACCESS_REQUEST, ("access", "credentials", "password", "доступ", "парол", "логин", "dostęp", "hasło")),
        (ClientIntent.PORTFOLIO_OR_PROOF_REQUEST, ("portfolio", "case study", "example", "proof", "портфолио", "кейс", "приклад", "przykład", "realizac")),
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
    if re.search(r"https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:telegram|whatsapp|viber|skype)\b|@\w{3,}", lowered):
        errors.append("external_contact")
    if re.search(r"\b(?:guarantee|promise|100%|гарантир\w*|обещ\w*|гаранту\w*|обіця\w*|gwarantuj\w*)\b", lowered):
        errors.append("unsupported_commitment")
    money_mentions = _MONEY_RE.findall(text)
    allowed_money = {_normalize_term(opportunity.actual_submitted_price)}
    minimum_price = opportunity.human_facts.get("minimum_price", "")
    if minimum_price:
        allowed_money.add(_normalize_term(minimum_price))
    if money_mentions and any(_normalize_term(value) not in allowed_money for value in money_mentions):
        errors.append("price_mismatch")
    timeline_mentions = _TIMELINE_RE.findall(text)
    allowed_timelines = {_normalize_term(opportunity.actual_submitted_timeline)}
    earliest = opportunity.human_facts.get("earliest_delivery", "")
    if earliest:
        allowed_timelines.add(_normalize_term(earliest))
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
    past_work_claim = re.search(
        r"(?:\bwe (?:built|delivered|implemented)|\bour (?:case|project)|"
        r"мы (?:создали|разработали|внедрили)|наш (?:кейс|проект)|"
        r"ми (?:створили|розробили|впровадили)|наш (?:кейс|проєкт)|"
        r"(?:zbudowaliśmy|wdrożyliśmy)|nasz projekt)",
        lowered,
    )
    reply_terms = set(re.findall(r"[\wąćęłńóśźżіїєґ]{4,}", lowered))
    case_terms = {
        value.casefold()
        for value in opportunity.evidence_case_id.split("_")
        if len(value) >= 4 and value not in {"DIRECT", "CASE"}
    }
    case_grounded = bool(case_terms) and case_terms.issubset(reply_terms)
    exact_evidence_grounded = (
        bool(approved_evidence) and approved_evidence in _normalize_term(text)
    )
    if past_work_claim and not (case_grounded or exact_evidence_grounded):
        errors.append("invented_case_metric_or_result")
    availability_claim = re.search(
        r"(?:i am|we are) available|(?:я|мы) (?:свободен|свободны|доступны)|"
        r"(?:я|ми) (?:вільний|вільні|доступні)|jesteśmy dostępni",
        lowered,
    )
    if availability_claim and "call_availability" not in opportunity.human_facts:
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
        actual_price: str,
        actual_timeline: str,
        *,
        confirmed_at: datetime | None = None,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        price = str(actual_price or "").strip()
        timeline = str(actual_timeline or "").strip()
        if not price or not timeline:
            raise SalesCloserError("actual submitted price and timeline are required")
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        if not opportunity.proposal_version or not opportunity.proposal_content_sha256:
            raise SalesCloserError("exact validated proposal version is unavailable")
        key = f"BID_SENT:{opportunity.id}:{opportunity.proposal_version}"
        existing = await self.repository.get_confirmation_by_key(key)
        if existing:
            if existing.actual_price != price or existing.actual_timeline != timeline:
                raise SalesCloserError("bid confirmation already exists with different actual terms")
            # A confirmation is the idempotency anchor. If a process stopped
            # after inserting it but before updating the opportunity, retrying
            # the same command safely completes the remaining state writes.
            opportunity = await self.repository.update_opportunity_fields(
                opportunity.id,
                {
                    "actual_submitted_price": existing.actual_price,
                    "actual_submitted_timeline": existing.actual_timeline,
                    "bid_submitted_at": existing.confirmed_at,
                    "last_owner_message_at": existing.confirmed_at,
                },
            ) or opportunity
            if opportunity.state in {
                OpportunityState.DISCOVERED.value,
                OpportunityState.MANUAL_REVIEW.value,
                OpportunityState.PROPOSAL_READY.value,
            }:
                opportunity = await self.repository.transition(
                    opportunity.id,
                    OpportunityState.BID_SUBMITTED.value,
                    source="telegram:/mark_bid_sent:reconcile",
                    reason="reconciled persisted adult-owner bid confirmation after restart",
                    actor="adult_owner",
                )
            return opportunity, existing, False
        if opportunity.state != OpportunityState.PROPOSAL_READY.value:
            raise SalesCloserError(f"bid cannot be confirmed from state {opportunity.state}")
        at = confirmed_at or self._now()
        confirmation = OwnerActionConfirmation(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            action="BID_SENT",
            idempotency_key=key,
            actor="adult_owner",
            proposal_version=opportunity.proposal_version,
            content_sha256=opportunity.proposal_content_sha256,
            actual_price=price,
            actual_timeline=timeline,
            confirmed_at=at,
        )
        confirmation, created = await self.repository.add_confirmation(confirmation)
        if created:
            opportunity = await self.repository.update_opportunity_fields(
                opportunity.id,
                {
                    "actual_submitted_price": price,
                    "actual_submitted_timeline": timeline,
                    "bid_submitted_at": at,
                    "last_owner_message_at": at,
                },
            ) or opportunity
            opportunity = await self.repository.transition(
                opportunity.id,
                OpportunityState.BID_SUBMITTED.value,
                source="telegram:/mark_bid_sent",
                reason="adult owner confirmed the exact bid was submitted manually",
                actor="adult_owner",
            )
        return opportunity, confirmation, created

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
        )
        incoming, created = await self.repository.add_turn(incoming)
        if not created:
            return await self._result_for_turn(incoming, resolution_basis, duplicate=True)

        opportunity = await self.repository.update_opportunity_fields(
            opportunity.id,
            {"last_client_message_at": received or now},
        ) or opportunity
        if opportunity.state not in {OpportunityState.LOST.value, OpportunityState.CLOSED.value}:
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
        self, request_id: str, answer: str
    ) -> SalesProcessResult:
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
        if request.status == "ANSWERED" and request.answer != value:
            raise SalesCloserError("request was already answered with a different fact")
        if request.status == "ANSWERED" and request.resulting_reply_version:
            return await self._result_for_turn(incoming, "human_answer", duplicate=True)

        facts = opportunity.human_facts
        if request.fact_key in facts and facts[request.fact_key] != value:
            raise SalesCloserError(
                "a different persisted fact already exists for this request"
            )
        facts[request.fact_key] = value
        questions = [
            item
            for item in _json_list(opportunity.unresolved_questions_json)
            if item != request.question
        ]
        decisions = _json_list(opportunity.decisions_json)
        if not any(
            isinstance(item, dict)
            and item.get("fact_key") == request.fact_key
            and item.get("answer") == value
            for item in decisions
        ):
            decisions.append(
                {
                    "source": "Artem",
                    "fact_key": request.fact_key,
                    "answer": value,
                    "recorded_at": self._now().isoformat(),
                }
            )
        opportunity = await self.repository.update_opportunity_fields(
            opportunity.id,
            {
                "human_facts_json": json.dumps(facts, ensure_ascii=False, sort_keys=True),
                "unresolved_questions_json": json.dumps(questions, ensure_ascii=False),
                "decisions_json": json.dumps(decisions, ensure_ascii=False),
            },
        ) or opportunity
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
                    "status": "ANSWERED",
                    "answer": value,
                    "answered_at": self._now(),
                    "answered_by": "Artem",
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
        reply, errors = await self._generate_and_store(opportunity, incoming, intent)
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
                "status": "ANSWERED",
                "answer": value,
                "answered_at": self._now(),
                "answered_by": "Artem",
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
        confirmed_at: datetime | None = None,
    ) -> tuple[SalesOpportunity, OwnerActionConfirmation, bool]:
        opportunity = await self.repository.get_opportunity(opportunity_id)
        if opportunity is None:
            raise SalesCloserError("opportunity not found")
        version = str(reply_version or "").strip()
        key = f"REPLY_SENT:{opportunity_id}:{version}"
        existing = await self.repository.get_confirmation_by_key(key)
        if existing:
            turns = await self.repository.list_turns(opportunity_id)
            confirmed_turn = next(
                (item for item in turns if item.reply_version == version), None
            )
            if confirmed_turn is None or confirmed_turn.content_sha256 != existing.content_sha256:
                raise SalesCloserError("persisted reply confirmation does not match stored content")
            if confirmed_turn.direction == "OUTGOING_DRAFT":
                await self.repository.update_turn_fields(
                    confirmed_turn.id,
                    {
                        "direction": "OUTGOING_CONFIRMED",
                        "sent_at": existing.confirmed_at,
                        "response_latency_seconds": existing.response_latency_seconds,
                    },
                )
            opportunity = await self.repository.update_opportunity_fields(
                opportunity_id,
                {"last_owner_message_at": existing.confirmed_at},
            ) or opportunity
            if opportunity.state in {
                OpportunityState.CLIENT_REPLIED.value,
                OpportunityState.NEEDS_HUMAN_INPUT.value,
                OpportunityState.MANUAL_REVIEW.value,
                OpportunityState.NEGOTIATING.value,
            }:
                opportunity = await self.repository.transition(
                    opportunity_id,
                    OpportunityState.WAITING_CLIENT.value,
                    source="telegram:/mark_reply_sent:reconcile",
                    reason=f"reconciled persisted adult-owner reply confirmation {version} after restart",
                    actor="adult_owner",
                )
            return opportunity, existing, False
        turns = await self.repository.list_turns(opportunity_id)
        draft = next(
            (item for item in turns if item.reply_version == version and item.direction == "OUTGOING_DRAFT"),
            None,
        )
        if draft is None:
            raise SalesCloserError("exact unconfirmed reply version not found")
        at = confirmed_at or self._now()
        latest_incoming = next((item for item in reversed(turns) if item.direction == "INCOMING"), None)
        latency = None
        if latest_incoming and latest_incoming.source_received_at:
            received = latest_incoming.source_received_at
            if received.tzinfo is None:
                received = received.replace(tzinfo=timezone.utc)
            latency = max(0.0, (at - received).total_seconds())
        confirmation = OwnerActionConfirmation(
            id=uuid4().hex,
            opportunity_id=opportunity_id,
            action="REPLY_SENT",
            idempotency_key=key,
            actor="adult_owner",
            reply_version=version,
            content_sha256=draft.content_sha256,
            response_latency_seconds=latency,
            confirmed_at=at,
        )
        confirmation, created = await self.repository.add_confirmation(confirmation)
        if created:
            await self.repository.update_turn_fields(
                draft.id,
                {
                    "direction": "OUTGOING_CONFIRMED",
                    "sent_at": at,
                    "response_latency_seconds": latency,
                },
            )
            opportunity = await self.repository.update_opportunity_fields(
                opportunity_id,
                {"last_owner_message_at": at},
            ) or opportunity
            opportunity = await self.repository.transition(
                opportunity_id,
                OpportunityState.WAITING_CLIENT.value,
                source="telegram:/mark_reply_sent",
                reason=f"adult owner confirmed exact reply {version} was sent manually",
                actor="adult_owner",
            )
        return opportunity, confirmation, created

    async def pending_cards(self) -> list[SalesProcessResult]:
        turns = await self.repository.list_pending_incoming_turns(self._now())
        return [await self._result_for_turn(turn, "pending_notification") for turn in turns]

    async def mark_notified(self, turn_id: str) -> None:
        await self.repository.mark_turn_notified(turn_id, self._now())

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
        facts = opportunity.human_facts
        specs = {
            ClientIntent.TECHNICAL_QUESTION: (
                "technical_capability",
                "Артём, подтверждает ли Вадим поддержку запрошенной клиентом интеграции/API?",
            ),
            ClientIntent.PRICE_OBJECTION: (
                "minimum_price",
                "Артём, какая минимальная допустимая цена для этого точного объёма?",
            ),
            ClientIntent.TIMELINE_OBJECTION: (
                "earliest_delivery",
                "Артём, какой самый ранний реалистичный срок можно подтвердить?",
            ),
            ClientIntent.SCOPE_CHANGE: (
                "scope_change_decision",
                "Артём, включать ли новое требование в текущий объём или оценивать отдельно?",
            ),
            ClientIntent.CALL_REQUEST: (
                "call_availability",
                "Артём, какие подтверждённые окна доступны для звонка?",
            ),
        }
        if intent == ClientIntent.PORTFOLIO_OR_PROOF_REQUEST and (
            not opportunity.approved_evidence or opportunity.evidence_case_id in {"", "NO_DIRECT_CASE", "DEMO_REQUIRED"}
        ):
            specs[intent] = (
                "direct_case_availability",
                "Артём, есть ли подтверждённый прямой кейс для этого запроса, или честно предложить demo?",
            )
        spec = specs.get(intent)
        return spec if spec and spec[0] not in facts else None

    async def _generate_and_store(
        self,
        opportunity: SalesOpportunity,
        incoming: ConversationTurn,
        intent: ClientIntent,
    ) -> tuple[ConversationTurn | None, list[str]]:
        turns = await self.repository.list_turns(opportunity.id)
        context = self._full_context(opportunity, turns, incoming, intent)
        candidate: SalesReplyCandidate | None = None
        errors: list[str] = []
        for attempt in range(2):
            try:
                candidate = await self._reply_generator(
                    context,
                    self._openai_client,
                    errors if attempt else None,
                )
            except Exception as exc:  # noqa: BLE001 - provider failures are fail-closed
                errors = [f"reply_provider_failed:{type(exc).__name__}"]
                break
            errors = reply_quality_errors(
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
            await self.repository.transition(
                opportunity.id,
                OpportunityState.MANUAL_REVIEW.value,
                source="sales_reply_validator",
                reason="; ".join(errors or ["reply generation failed"]),
                actor="system",
            )
            return None, errors

        version = _next_reply_version(turns)
        draft = ConversationTurn(
            id=uuid4().hex,
            opportunity_id=opportunity.id,
            direction="OUTGOING_DRAFT",
            content=candidate.reply,
            content_sha256=_hash_text(candidate.reply),
            canonical_turn_identity=f"draft:{opportunity.id}:{version}:{_hash_text(candidate.reply)}",
            source_reference_id=incoming.id,
            reply_version=version,
            language=incoming.language,
            intent=intent.value,
            russian_summary=candidate.russian_summary,
            actual_ask=candidate.actual_ask,
            negotiation_strategy=candidate.strategy,
            risks=candidate.risks,
        )
        draft, _created = await self.repository.add_turn(draft)
        await self.repository.update_turn_fields(
            incoming.id,
            {
                "russian_summary": candidate.russian_summary,
                "actual_ask": candidate.actual_ask,
                "negotiation_strategy": candidate.strategy,
                "risks": candidate.risks,
            },
        )
        target = (
            OpportunityState.LOST
            if intent == ClientIntent.REJECTION
            else OpportunityState.SELECTED
            if intent in {ClientIntent.CLIENT_READY_TO_SELECT, ClientIntent.SELECTED_OR_CONTRACT_STEP}
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
    ) -> dict[str, Any]:
        confirmed = [
            {
                "direction": turn.direction,
                "content": turn.content,
                "sent_at": turn.sent_at,
                "reply_version": turn.reply_version,
            }
            for turn in turns
            if turn.direction in {"INCOMING", "OUTGOING_CONFIRMED"}
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
            "human_facts": opportunity.human_facts,
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
