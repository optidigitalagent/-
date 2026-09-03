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
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from .commercial_terms import (
    MoneyTerms,
    PricingMode,
    TimelineTerms,
    TimelineUnit,
    money_terms_from_json,
    parse_money_terms,
    parse_timeline_terms,
    timeline_terms_from_json,
)

if TYPE_CHECKING:
    from .email_analyzer import JobAnalysis


ANALYSIS_VERSION = "proposal-quality-gate-v3"
PROPOSAL_VERSION_PREFIX = "pqg-v3"

SCORE_VALID = "VALID"
SCORE_MISSING = "MISSING"
SCORE_INVALID = "INVALID"
SCORE_FAILED = "FAILED"
SCORE_STATES = frozenset({SCORE_VALID, SCORE_MISSING, SCORE_INVALID, SCORE_FAILED})

APPLICATION_EVIDENCE_PREFIXES: Mapping[str, str] = {
    "uk": "Підтверджений досвід: ",
    "ru": "Подтверждённый опыт: ",
    "en": "Approved evidence: ",
    "pl": "Potwierdzone doświadczenie: ",
}
APPLICATION_COMMERCIAL_PREFIXES: Mapping[str, str] = {
    "uk": "Комерційні умови: ",
    "ru": "Коммерческие условия: ",
    "en": "Commercial terms: ",
    "pl": "Warunki komercyjne: ",
}

# Backward-compatible English names remain public for the protected V2 tests.
APPLICATION_EVIDENCE_PREFIX = APPLICATION_EVIDENCE_PREFIXES["en"]
APPLICATION_COMMERCIAL_PREFIX = APPLICATION_COMMERCIAL_PREFIXES["en"]


class QualityStatus(StrEnum):
    VALID = "QUALITY_VALID"
    REPAIRED = "QUALITY_REPAIRED"
    MANUAL_REVIEW = "QUALITY_MANUAL_REVIEW"
    NON_EXECUTABLE = "QUALITY_NON_EXECUTABLE"
    FAILED = "QUALITY_FAILED"


PROPOSAL_READY_QUALITY_STATUSES = frozenset(
    {QualityStatus.VALID.value, QualityStatus.REPAIRED.value}
)


class LocalizedEvidence(str):
    """A nested language registry entry with a string-compatible English view."""

    def __new__(cls, values: Mapping[str, str] | str) -> Self:
        if isinstance(values, str):
            instance = super().__new__(cls, values)
            instance._values = {"en": values}
            return instance
        instance = super().__new__(cls, values["en"])
        instance._values = dict(values)
        return instance

    def __getitem__(self, key: Any) -> str:
        if isinstance(key, str):
            return self._values[key]
        return super().__getitem__(key)

    def get(self, language: str, default: str = "") -> str:
        return self._values.get(language, default)


def _evidence(*, uk: str, ru: str, en: str, pl: str) -> LocalizedEvidence:
    return LocalizedEvidence({"uk": uk, "ru": ru, "en": en, "pl": pl})


# Exact approved factual claims from the canonical Project Brain portfolio
# registry. EVIDENCE_REGISTRY[case_id][language] is application-owned.
EVIDENCE_REGISTRY: Mapping[str, LocalizedEvidence] = {
    "BELLA_DENT": _evidence(
        uk="Bella Dent — сайт, автоматизація лідів, Telegram-боти, PostgreSQL і Cloudinary; підтверджено історією робочої системи та реалізації.",
        ru="Bella Dent — сайт, автоматизация лидов, Telegram-боты, PostgreSQL и Cloudinary; подтверждено историей рабочей системы и реализации.",
        en="Bella Dent — website, lead automation, Telegram bots, PostgreSQL and Cloudinary; supported by live-system and implementation history.",
        pl="Bella Dent — strona internetowa, automatyzacja leadów, boty Telegram, PostgreSQL i Cloudinary; potwierdzone historią działającego systemu i realizacji.",
    ),
    "DENTAL_SUPPLIER_AI_AGENT": _evidence(
        uk="Dental Supplier AI Agent — AI-агент, Telegram, порівняння постачальників і звітність; підтверджено приватним кодом та архітектурою.",
        ru="Dental Supplier AI Agent — AI-агент, Telegram, сравнение поставщиков и отчётность; подтверждено приватным кодом и архитектурой.",
        en="Dental Supplier AI Agent — AI agent, Telegram, supplier comparison and reporting; supported by private code and architecture.",
        pl="Dental Supplier AI Agent — agent AI, Telegram, porównywanie dostawców i raportowanie; potwierdzone prywatnym kodem i architekturą.",
    ),
    "GMAIL_JOB_AGENT": _evidence(
        uk="Gmail Job Agent — обробка Gmail, AI-кваліфікація, Telegram, Railway і PostgreSQL; підтверджено робочим кодом та історією production-системи.",
        ru="Gmail Job Agent — обработка Gmail, AI-квалификация, Telegram, Railway и PostgreSQL; подтверждено рабочим кодом и историей production-системы.",
        en="Gmail Job Agent — Gmail ingestion, AI qualification, Telegram, Railway and PostgreSQL; supported by working code and production history.",
        pl="Gmail Job Agent — obsługa Gmail, kwalifikacja AI, Telegram, Railway i PostgreSQL; potwierdzone działającym kodem i historią systemu produkcyjnego.",
    ),
    "STATUS_DENT": _evidence(
        uk="Status Dent — сайт, SEO та локальний пошук; підтверджено робочим сайтом і роботою в Google Search Console.",
        ru="Status Dent — сайт, SEO и локальный поиск; подтверждено рабочим сайтом и работой в Google Search Console.",
        en="Status Dent — website, SEO and local search; supported by a live site and Google Search Console work.",
        pl="Status Dent — strona internetowa, SEO i wyszukiwanie lokalne; potwierdzone działającą stroną i pracą w Google Search Console.",
    ),
    "AMIDENTAL": _evidence(
        uk="Amidental — сайт, форми та розгортання; підтверджено робочим сайтом і матеріалами дизайну.",
        ru="Amidental — сайт, формы и развёртывание; подтверждено рабочим сайтом и материалами дизайна.",
        en="Amidental — website, forms and deployment; supported by a live site and design work.",
        pl="Amidental — strona internetowa, formularze i wdrożenie; potwierdzone działającą stroną i materiałami projektowymi.",
    ),
    "ART_STUDIO_184": _evidence(
        uk="Art Studio 184 — сайт, автоматизація, інструменти ціноутворення та HR; підтверджено історією проєкту й матеріалами.",
        ru="Art Studio 184 — сайт, автоматизация, инструменты ценообразования и HR; подтверждено историей проекта и материалами.",
        en="Art Studio 184 — website, automation, pricing and HR tools; supported by project history and assets.",
        pl="Art Studio 184 — strona internetowa, automatyzacja oraz narzędzia cenowe i HR; potwierdzone historią projektu i materiałami.",
    ),
    "AUDIOBOOK_CLEANER": _evidence(
        uk="Audiobook Cleaner — аудіо AI, очищення ASR та QA-пайплайн; підтверджено CLI, тестами й відгуками користувачів.",
        ru="Audiobook Cleaner — аудио AI, очистка ASR и QA-пайплайн; подтверждено CLI, тестами и отзывами пользователей.",
        en="Audiobook Cleaner — audio AI, ASR cleanup and QA pipeline; supported by CLI, tests and human feedback.",
        pl="Audiobook Cleaner — AI dla dźwięku, oczyszczanie ASR i proces QA; potwierdzone przez CLI, testy i opinie użytkowników.",
    ),
    "MENTIUM": _evidence(
        uk="Mentium — освітній AI-продукт і дослідження MVP; підтверджено історією платформи та дослідження.",
        ru="Mentium — образовательный AI-продукт и исследование MVP; подтверждено историей платформы и исследования.",
        en="Mentium — education AI product and MVP discovery; supported by platform and discovery history.",
        pl="Mentium — edukacyjny produkt AI i badanie MVP; potwierdzone historią platformy i badań.",
    ),
    "NFC_REVIEW_CARDS": _evidence(
        uk="NFC Review Cards — процес роботи NFC-продукту та клієнтська активність; підтверджено фізичним продуктом і продажами.",
        ru="NFC Review Cards — процесс работы NFC-продукта и клиентская активность; подтверждено физическим продуктом и продажами.",
        en="NFC Review Cards — NFC product workflow and reviews; supported by physical-product and sales activity.",
        pl="NFC Review Cards — proces działania produktu NFC i aktywność klientów; potwierdzone fizycznym produktem i sprzedażą.",
    ),
    "NO_DIRECT_CASE": _evidence(
        uk="Не заявляємо про прямо відповідний production-кейс; підхід ґрунтується лише на зазначених компетенціях і вимогах джерела.",
        ru="Не заявляем о прямо соответствующем production-кейсе; подход основан только на указанных компетенциях и требованиях источника.",
        en="No directly matching production case is claimed; the approach is based only on the stated capabilities and source requirements.",
        pl="Nie deklarujemy bezpośrednio odpowiadającego wdrożenia produkcyjnego; podejście opiera się wyłącznie na wskazanych kompetencjach i wymaganiach źródłowych.",
    ),
    "DEMO_REQUIRED": _evidence(
        uk="Потрібен демонстраційний зразок або прототип для цього проєкту, перш ніж заявляти про production-результат чи розгортання.",
        ru="Для этого проекта нужен демонстрационный образец или прототип, прежде чем заявлять о production-результате или развёртывании.",
        en="A project-specific demo or prototype is required before any production result or deployment claim can be made.",
        pl="Przed zadeklarowaniem wyniku produkcyjnego lub wdrożenia potrzebna jest demonstracja albo prototyp przygotowany dla tego projektu.",
    ),
}


_PLACEHOLDER_RE = re.compile(
    r"(?i)(?:\[(?:name|price|link|client|company|budget|timeline)[^\]]*\]|"
    r"\{\{?[^{}]+\}?\}|\bTBD\b|\bTBC\b|\b(?-i:N/?A)\b|<insert\b|lorem ipsum)"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_OBFUSCATED_EMAIL_RE = re.compile(
    r"(?i)\b[a-z0-9._%+-]+\s*(?:\[|\(|\{)?\s*at\s*(?:\]|\)|\})?\s*"
    r"[a-z0-9-]+(?:\s*(?:\[|\(|\{)?\s*dot\s*(?:\]|\)|\})?\s*[a-z0-9-]+)+\b"
)
_URL_RE = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.-]{1,31}://|\bwww\.|\bt\.me/)"
)
_BARE_DOMAIN_RE = re.compile(
    r"(?i)(?<![@\w])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:[a-z]{2,24}|xn--[a-z0-9-]{2,59})\b"
)
_TELEGRAM_RE = re.compile(
    r"(?i)(?:\bt\.me/|(?<![\w.])@[a-z][a-z0-9_.-]{2,}|"
    r"\b(?:message|contact|write|напиш\w*|пиш\w*)\b.{0,24}\btelegram\b)"
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){9,15}(?!\d)")
_OFF_PLATFORM_RE = re.compile(
    r"(?i)\b(?:whatsapp|viber|signal|discord|slack|linkedin|skype|"
    r"instagram|facebook|email me|write me at|contact (?:me|us) (?:on|via|at)|"
    r"find (?:me|us) (?:on|via)|(?:review|see|view) (?:my|our) (?:work|portfolio) (?:on|at)|"
    r"напиш(?:іть|ите)\s+(?:мені|мне|нам)\s+(?:у|в|на)|пишіть\s+на|"
    r"знайд(?:іть|ите)\s+(?:мене|нас)\s+(?:через|у|в)|"
    r"посмотр(?:ите|еть)\s+(?:мо[её]|наше)\s+портфолио\s+(?:на|в)|"
    r"перегляньте\s+(?:моє|наше)\s+портфоліо\s+(?:на|у)|"
    r"napisz\w*\s+(?:do mnie|do nas|na)|znajdź\w*\s+nas|"
    r"zobacz\w*\s+(?:moje|nasze)\s+portfolio)\b"
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
    r"(?ix)\b(?:"
    r"we\s+(?:(?:have|have\s+already|already|previously)\s+)?(?:successfully\s+)?"
    r"(?:built|created|developed|implemented|integrated|launched|delivered|completed)|"
    r"we['’]ve\s+(?:successfully\s+)?(?:built|created|developed|implemented|integrated|launched|delivered|completed)|"
    r"our\s+(?:team|engineers?|developers?)\s+(?:has\s+|have\s+)?(?:successfully\s+|previously\s+|already\s+)?"
    r"(?:built|created|developed|implemented|integrated|launched|delivered|completed)|"
    r"our\s+(?:experience|track\s+record|portfolio)\s+(?:includes?|covers?|shows?)|"
    r"ми\s+(?:(?:вже|раніше|успішно)\s+)*(?:реалізували|розробляли|розробили|впровадили|створили|запустили|інтегрували|виконали)|"
    r"наша\s+команда\s+(?:(?:вже|раніше|успішно)\s+)*(?:реалізувала|розробляла|розробила|впровадила|створила|запустила|інтегрувала|виконала)|"
    r"маємо\s+досвід(?:\s+створення|\s+розробки|\s+впровадження|\s+у|\s+в)?|"
    r"наш\s+досвід\s+(?:включає|охоплює)|"
    r"мы\s+(?:(?:уже|ранее|успешно)\s+)*(?:реализовали|разрабатывали|разработали|внедрили|создали|запустили|интегрировали|выполнили)|"
    r"наша\s+команда\s+(?:(?:уже|ранее|успешно)\s+)*(?:реализовала|разрабатывала|разработала|внедрила|создала|запустила|интегрировала|выполнила)|"
    r"у\s+нас\s+есть\s+опыт(?:\s+создания|\s+разработки|\s+внедрения|\s+в)?|"
    r"наш\s+опыт\s+(?:включает|охватывает)|"
    r"nasz\s+zesp[oó]ł\s+(?:(?:już|wcześniej|z\s+powodzeniem)\s+)*(?:wdrożył|opracował|zbudował|stworzył|zrealizował|uruchomił|zintegrował)|"
    r"wcześniej\s+(?:opracowaliśmy|wdrożyliśmy|zbudowaliśmy|stworzyliśmy|zrealizowaliśmy)|"
    r"mamy\s+doświadczenie\s+(?:w|tworzeniu|opracowywaniu|wdrażaniu)|"
    r"zrealizowaliśmy\s+(?:już\s+)?(?:podobny\s+)?projekt|"
    r"nasze\s+doświadczenie\s+(?:obejmuje|zawiera)"
    r")\b"
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


@dataclass(frozen=True, slots=True)
class ScoreMetadata:
    """Canonical persistence representation for one Score/Fit field."""

    value: float
    valid: bool
    raw: str
    state: str


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


def normalize_score_metadata(
    value: Any,
    *,
    raw: Any = None,
    explicit_state: str = "",
    explicit_valid: bool | None = None,
    analysis_succeeded: bool = True,
) -> ScoreMetadata:
    """Return one coherent, non-null Score/Fit persistence contract.

    A real zero remains ``VALID``. Missing, malformed, non-finite, out-of-range,
    and provider-failure inputs use the numeric database fallback ``0.0`` while
    retaining their distinct state, so the fallback can never imply a genuine
    score or make a proposal eligible.
    """

    try:
        raw_text = "" if raw is None else str(raw)
    except Exception:
        raw_text = ""
    raw_text = raw_text.strip()
    requested_state = str(explicit_state or "").strip().upper()
    parsed_value = finite_score(value)
    parsed_raw = finite_score(raw_text) if raw_text else None
    parsed = parsed_raw if raw_text else parsed_value
    value_supplied = value is not None and not (
        isinstance(value, str) and not value.strip()
    )

    if analysis_succeeded is False or requested_state == SCORE_FAILED:
        state = SCORE_FAILED
    elif requested_state == SCORE_MISSING:
        state = SCORE_MISSING
    elif requested_state == SCORE_INVALID:
        state = SCORE_INVALID
    elif value_supplied and parsed_value is None:
        state = SCORE_INVALID
    elif requested_state == SCORE_VALID:
        state = SCORE_VALID if parsed is not None else SCORE_INVALID
    elif explicit_valid is False:
        state = SCORE_INVALID if raw_text else SCORE_MISSING
    elif explicit_valid is True:
        state = SCORE_VALID if parsed is not None else SCORE_INVALID
    elif raw_text:
        state = SCORE_VALID if parsed_raw is not None else SCORE_INVALID
    elif value is None or (isinstance(value, str) and not value.strip()):
        state = SCORE_MISSING
    else:
        state = SCORE_VALID if parsed_value is not None else SCORE_INVALID

    return ScoreMetadata(
        value=(parsed if state == SCORE_VALID and parsed is not None else 0.0),
        valid=state == SCORE_VALID,
        raw=raw_text,
        state=state,
    )


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


def approved_evidence_text(case_id: str, language: str = "en") -> str:
    entry = EVIDENCE_REGISTRY.get(str(case_id or "").strip().upper())
    return entry.get(language, "") if entry is not None else ""


def _record_value(record: Any, field_name: str, default: Any = "") -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name, default)
    return getattr(record, field_name, default)


def _normalized_text(value: str) -> str:
    return " ".join((value or "").split())


def _commercial_terms(analysis: Any) -> tuple[MoneyTerms | None, TimelineTerms | None]:
    raw_money = parse_money_terms(
        str(_record_value(analysis, "recommended_price") or "")
    )
    raw_timeline = parse_timeline_terms(
        str(_record_value(analysis, "realistic_timeline") or "")
    )
    money_json = str(_record_value(analysis, "money_terms_json") or "")
    timeline_json = str(_record_value(analysis, "timeline_terms_json") or "")
    if money_json:
        stored_money = money_terms_from_json(money_json)
        raw_money = stored_money if stored_money == raw_money else None
    if timeline_json:
        stored_timeline = timeline_terms_from_json(timeline_json)
        raw_timeline = stored_timeline if stored_timeline == raw_timeline else None
    return raw_money, raw_timeline


def _plural_index(low: int, high: int) -> str:
    return "one" if low == high == 1 else "many"


def _amount_text(terms: MoneyTerms) -> str:
    value = terms.canonical_model_text().split(" as ", 1)[0]
    return value


_TIMELINE_WORDS: Mapping[str, Mapping[TimelineUnit, Mapping[str, str]]] = {
    "uk": {
        TimelineUnit.HOURS: {"one": "година", "many": "годин"},
        TimelineUnit.DAYS: {"one": "день", "many": "днів"},
        TimelineUnit.WEEKS: {"one": "тиждень", "many": "тижнів"},
        TimelineUnit.MONTHS: {"one": "місяць", "many": "місяців"},
    },
    "ru": {
        TimelineUnit.HOURS: {"one": "час", "many": "часов"},
        TimelineUnit.DAYS: {"one": "день", "many": "дней"},
        TimelineUnit.WEEKS: {"one": "неделя", "many": "недель"},
        TimelineUnit.MONTHS: {"one": "месяц", "many": "месяцев"},
    },
    "en": {
        TimelineUnit.HOURS: {"one": "hour", "many": "hours"},
        TimelineUnit.DAYS: {"one": "day", "many": "days"},
        TimelineUnit.WEEKS: {"one": "week", "many": "weeks"},
        TimelineUnit.MONTHS: {"one": "month", "many": "months"},
    },
    "pl": {
        TimelineUnit.HOURS: {"one": "godzina", "many": "godzin"},
        TimelineUnit.DAYS: {"one": "dzień", "many": "dni"},
        TimelineUnit.WEEKS: {"one": "tydzień", "many": "tygodni"},
        TimelineUnit.MONTHS: {"one": "miesiąc", "many": "miesięcy"},
    },
}

_MILESTONE_WORDING: Mapping[str, Mapping[int, str]] = {
    "uk": {1: "оплата одним етапом", 2: "оплата двома етапами", 3: "оплата трьома етапами"},
    "ru": {1: "оплата одним этапом", 2: "оплата двумя этапами", 3: "оплата тремя этапами"},
    "en": {1: "payment in one milestone", 2: "payment in two milestones", 3: "payment in three milestones"},
    "pl": {1: "płatność w jednym etapie", 2: "płatność w dwóch etapach", 3: "płatność w trzech etapach"},
}

_PRICE_WORDING: Mapping[str, str] = {
    "uk": "вартість — {amount}",
    "ru": "стоимость — {amount}",
    "en": "price — {amount}",
    "pl": "cena — {amount}",
}

_TIMELINE_WORDING: Mapping[str, str] = {
    "uk": "строк — {timeline}",
    "ru": "срок — {timeline}",
    "en": "timeline — {timeline}",
    "pl": "termin — {timeline}",
}


def _localized_timeline(terms: TimelineTerms, language: str) -> str:
    amount = str(terms.min_value)
    if terms.max_value != terms.min_value:
        amount += f"–{terms.max_value}"
    form = _plural_index(terms.min_value, terms.max_value)
    return f"{amount} {_TIMELINE_WORDS[language][terms.unit][form]}"


def application_owned_commercial_block(analysis: Any) -> str:
    language = str(_record_value(analysis, "language") or "")
    money, timeline = _commercial_terms(analysis)
    if language not in APPLICATION_COMMERCIAL_PREFIXES or money is None or timeline is None:
        return ""
    clauses = [_PRICE_WORDING[language].format(amount=_amount_text(money))]
    if money.pricing_mode == PricingMode.MILESTONE:
        clauses.append(_MILESTONE_WORDING[language][int(money.milestone_count or 0)])
    clauses.append(
        _TIMELINE_WORDING[language].format(
            timeline=_localized_timeline(timeline, language)
        )
    )
    return APPLICATION_COMMERCIAL_PREFIXES[language] + "; ".join(clauses) + "."


def application_owned_evidence_clause(analysis: Any) -> str:
    language = str(_record_value(analysis, "language") or "")
    prefix = APPLICATION_EVIDENCE_PREFIXES.get(language, "")
    return prefix + approved_evidence_text(
        str(_record_value(analysis, "evidence_case_id") or ""), language
    )


def proposal_body(value: str) -> str:
    """Return only the model-owned body, excluding application-owned suffixes."""

    text = (value or "").strip()
    markers = [f"\n\n{prefix}" for prefix in APPLICATION_EVIDENCE_PREFIXES.values()]
    positions = [text.find(marker) for marker in markers if marker in text]
    if positions:
        return text[:min(positions)].strip()
    return text


def compose_application_owned_proposal(analysis: Any) -> str:
    body = proposal_body(str(_record_value(analysis, "proposal_draft") or ""))
    language = str(_record_value(analysis, "language") or "")
    approved = approved_evidence_text(
        str(_record_value(analysis, "evidence_case_id") or ""), language
    )
    commercial = application_owned_commercial_block(analysis)
    if not body or not approved or not commercial:
        return body
    return (
        f"{body}\n\n{application_owned_evidence_clause(analysis)}\n"
        f"{commercial}"
    )


def _score_state_for(analysis: JobAnalysis, field_name: str) -> str:
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


_LANGUAGE_MARKERS: Mapping[str, tuple[str, ...]] = {
    "uk": ("проєкт", "можемо", "потріб", "вартість", "підтверд", "реалізуємо", "етап", "досвід"),
    "ru": ("проект", "можем", "нужно", "стоимость", "подтвержд", "реализуем", "этап", "опыт"),
    "en": ("the", "we", "your", "project", "can", "will", "price", "timeline", "approved", "evidence", "commercial", "deliver"),
    "pl": ("możemy", "projekt", "państwa", "termin", "cena", "potwierd", "wdroż", "etap", "warunki", "doświadczenie"),
}

_ALLOWED_PROPER_NAMES = (
    "Bella Dent", "Dental Supplier AI Agent", "Gmail Job Agent", "Status Dent",
    "Amidental", "Art Studio 184", "Audiobook Cleaner", "Mentium",
    "NFC Review Cards", "Telegram", "PostgreSQL", "Cloudinary", "Gmail",
    "Railway", "Google Search Console", "AI", "ASR", "QA", "CLI", "MVP",
    "API", "CRM", "production", "HR", "SEO", "NFC",
)


def _without_allowed_names(text: str) -> str:
    value = str(text or "")
    for name in sorted(_ALLOWED_PROPER_NAMES, key=len, reverse=True):
        value = re.sub(re.escape(name), " ", value, flags=re.IGNORECASE)
    return value


def _final_language_matches(language: str, proposal: str) -> bool:
    if language not in _LANGUAGE_MARKERS or not _language_matches(language, proposal):
        return False
    value = _without_allowed_names(proposal).casefold()
    target_hits = sum(
        len(re.findall(rf"(?<!\w){re.escape(marker)}", value))
        for marker in _LANGUAGE_MARKERS[language]
    )
    foreign_hits = {
        candidate: sum(
            len(re.findall(rf"(?<!\w){re.escape(marker)}", value))
            for marker in markers
        )
        for candidate, markers in _LANGUAGE_MARKERS.items()
        if candidate != language
    }
    # Proper names and technology labels are removed above. Two or more
    # explanatory markers from another language make the final text mixed.
    return target_hits > 0 and all(count < 2 for count in foreign_hits.values())


def _project_specific(analysis: JobAnalysis) -> bool:
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


def _source_grounded(text: str, analysis: JobAnalysis) -> bool:
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


_CONFUSABLES = str.maketrans(
    {
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
        "у": "y", "і": "i", "ј": "j", "к": "k", "м": "m", "т": "t",
        "в": "b", "н": "h", "А": "A", "Е": "E", "О": "O", "Р": "P",
        "С": "C", "Х": "X", "У": "Y", "І": "I", "Ј": "J", "К": "K",
        "М": "M", "Т": "T", "В": "B", "Н": "H",
    }
)

_MODEL_OWNED_TEXT_FIELDS = (
    "reason", "why_relevant", "service_lane", "win_probability_signal",
    "scope_clarity", "estimated_effort", "delivery_risk",
    "client_payment_risk", "project_mode_reason", "recommended_price",
    "realistic_timeline", "selected_evidence", "evidence", "proposal_draft",
    "next_action",
)


def _contains_external_contact(text: str) -> bool:
    value = str(text or "")
    normalized = value.translate(_CONFUSABLES)
    return bool(
        _EMAIL_RE.search(value)
        or _OBFUSCATED_EMAIL_RE.search(normalized)
        or _URL_RE.search(normalized)
        or _BARE_DOMAIN_RE.search(normalized)
        or _TELEGRAM_RE.search(normalized)
        or _PHONE_RE.search(value)
        or _OFF_PLATFORM_RE.search(normalized)
    )


def _safe_text_errors(analysis: JobAnalysis) -> list[str]:
    proposal = analysis.proposal_draft or ""
    errors: list[str] = []
    if _PLACEHOLDER_RE.search(proposal):
        errors.append("proposal_contains_placeholder")
    if _contains_external_contact(proposal):
        errors.append("proposal_contains_external_contact")
    if _UNSUPPORTED_CLAIM_RE.search(proposal):
        errors.append("proposal_contains_unsupported_claim")
    for field_name in _MODEL_OWNED_TEXT_FIELDS:
        value = str(getattr(analysis, field_name, "") or "")
        if field_name != "proposal_draft" and _PLACEHOLDER_RE.search(value):
            errors.append("structured_field_contains_placeholder")
        if field_name != "proposal_draft" and _contains_external_contact(value):
            errors.append("structured_field_contains_external_contact")
        if field_name != "proposal_draft" and (
            _PAST_CAPABILITY_RE.search(value) or _DIRECT_CASE_RE.search(value)
        ):
            errors.append("structured_field_contains_unapproved_capability_claim")
    return errors


def _commercial_consistency_errors(analysis: JobAnalysis) -> list[str]:
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
    timeline_terms = parse_timeline_terms(analysis.realistic_timeline or "")
    day_match = (
        (timeline_terms.min_value, timeline_terms.max_value)
        if timeline_terms is not None and timeline_terms.unit == TimelineUnit.DAYS
        else None
    )
    if effort_match and day_match:
        effort_high = int(effort_match.group(2) or effort_match.group(1))
        days_high = day_match[1]
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


def _application_owned_proposal_errors(analysis: JobAnalysis) -> list[str]:
    proposal = analysis.proposal_draft or ""
    body = proposal_body(proposal)
    errors: list[str] = []
    evidence_id = str(analysis.evidence_case_id or "").strip().upper()
    approved = approved_evidence_text(evidence_id, analysis.language)
    has_injected_suffix = any(
        f"\n\n{prefix}" in proposal
        for prefix in APPLICATION_EVIDENCE_PREFIXES.values()
    )

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
    money_terms = parse_money_terms(analysis.recommended_price or "")
    structured_money = (
        (float(money_terms.min_amount), float(money_terms.max_amount), money_terms.currency.value)
        if money_terms is not None
        else None
    )
    if body_money is not None:
        if structured_money is None or body_money != structured_money:
            errors.append("proposal_price_conflicts_with_recommended_price")
        errors.append("proposal_contains_model_owned_commercial_terms")
    body_timeline = _timeline_signature(body)
    timeline_terms = parse_timeline_terms(analysis.realistic_timeline or "")
    structured_timeline = (
        (timeline_terms.min_value, timeline_terms.max_value, timeline_terms.unit.value.casefold())
        if timeline_terms is not None
        else None
    )
    if body_timeline is not None:
        if structured_timeline is None or body_timeline != structured_timeline:
            errors.append("proposal_timeline_conflicts_with_realistic_timeline")
        errors.append("proposal_contains_model_owned_commercial_terms")
    body_milestones = _milestone_signature(body)
    structured_milestones = money_terms.milestone_count if money_terms else None
    if body_milestones is not None:
        if body_milestones != structured_milestones:
            errors.append("proposal_milestone_logic_conflicts_with_recommended_price")
        errors.append("proposal_contains_model_owned_commercial_terms")

    if has_injected_suffix:
        if not (
            str(getattr(analysis, "money_terms_json", "") or "")
            and str(getattr(analysis, "timeline_terms_json", "") or "")
        ):
            errors.append("proposal_contains_raw_application_suffix")
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


def _canonical_commercial_errors(analysis: Any) -> list[str]:
    errors: list[str] = []
    money = parse_money_terms(str(_record_value(analysis, "recommended_price") or ""))
    timeline = parse_timeline_terms(str(_record_value(analysis, "realistic_timeline") or ""))
    if money is None:
        errors.append("recommended_price_not_full_string_canonical")
    if timeline is None:
        errors.append("realistic_timeline_not_full_string_canonical")

    money_json = str(_record_value(analysis, "money_terms_json") or "")
    timeline_json = str(_record_value(analysis, "timeline_terms_json") or "")
    if money_json and money_terms_from_json(money_json) != money:
        errors.append("money_terms_json_mismatch")
    if timeline_json and timeline_terms_from_json(timeline_json) != timeline:
        errors.append("timeline_terms_json_mismatch")
    return errors


def final_composed_proposal_errors(analysis: Any, proposal: str) -> tuple[str, ...]:
    """Revalidate the exact final text before hashing, versioning or delivery."""

    errors: list[str] = []
    expected = compose_application_owned_proposal(analysis)
    if not expected or _normalized_text(proposal) != _normalized_text(expected):
        errors.append("final_proposal_composition_mismatch")
    if _contains_external_contact(proposal):
        errors.append("final_proposal_contains_external_contact")
    if _PLACEHOLDER_RE.search(proposal):
        errors.append("final_proposal_contains_placeholder")
    if _UNSUPPORTED_CLAIM_RE.search(proposal_body(proposal)):
        errors.append("final_proposal_contains_unsupported_claim")
    if not _final_language_matches(
        str(_record_value(analysis, "language") or ""), proposal
    ):
        errors.append("final_proposal_language_mismatch")
    errors.extend(_canonical_commercial_errors(analysis))
    if proposal.count(application_owned_evidence_clause(analysis)) != 1:
        errors.append("final_evidence_clause_not_exact")
    if proposal.count(application_owned_commercial_block(analysis)) != 1:
        errors.append("final_commercial_block_not_exact")
    return _dedupe(errors)


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def validate_analysis(
    analysis: JobAnalysis,
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
    if parse_money_terms(price) is None:
        errors.append("recommended_price_not_full_string_canonical")
    timeline = analysis.realistic_timeline or ""
    if not timeline.strip() or not _TIMELINE_RE.search(timeline):
        errors.append("realistic_timeline_missing_or_unparseable")
    if parse_timeline_terms(timeline) is None:
        errors.append("realistic_timeline_not_full_string_canonical")
    errors.extend(_canonical_commercial_errors(analysis))

    evidence_id = str(analysis.evidence_case_id or "").strip().upper()
    approved = approved_evidence_text(evidence_id, analysis.language)
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
        final_candidate = compose_application_owned_proposal(analysis)
        errors.extend(final_composed_proposal_errors(analysis, final_candidate))

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
    analysis: JobAnalysis,
    validation: QualityValidation,
    *,
    repair_count: int = 0,
) -> JobAnalysis:
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
    approved = approved_evidence_text(analysis.evidence_case_id, analysis.language)
    if approved:
        analysis.selected_evidence = approved
    if validation.proposal_ready:
        money = parse_money_terms(analysis.recommended_price or "")
        timeline = parse_timeline_terms(analysis.realistic_timeline or "")
        if money is None or timeline is None:
            final_errors = ("canonical_commercial_terms_missing_after_validation",)
        else:
            # Raw model strings stop here. Persist and render canonical values.
            analysis.money_terms_json = money.to_json()
            analysis.timeline_terms_json = timeline.to_json()
            analysis.recommended_price = money.canonical_model_text()
            analysis.realistic_timeline = timeline.canonical_model_text()
            final_text = compose_application_owned_proposal(analysis)
            final_errors = final_composed_proposal_errors(analysis, final_text)
        if final_errors:
            analysis.analysis_quality_status = QualityStatus.MANUAL_REVIEW.value
            analysis.quality_errors = json.dumps(list(final_errors), ensure_ascii=False)
            analysis.proposal_quality_score = _quality_score(final_errors)
            analysis.qualified = False
            analysis.proposal_version = ""
            analysis.proposal_content_sha256 = ""
            analysis.recommended_price = ""
            analysis.realistic_timeline = ""
            analysis.money_terms_json = ""
            analysis.timeline_terms_json = ""
            analysis.proposal_draft = ""
            analysis.next_action = "Review the quality errors; do not submit a bid."
        else:
            analysis.proposal_draft = final_text
            analysis.proposal_content_sha256 = proposal_text_hash(final_text)
            analysis.proposal_version = proposal_version(analysis)
    else:
        analysis.qualified = False
        analysis.proposal_version = ""
        analysis.proposal_content_sha256 = ""
        # Manual/non-executable states must never leak a usable bid package.
        analysis.recommended_price = ""
        analysis.realistic_timeline = ""
        analysis.money_terms_json = ""
        analysis.timeline_terms_json = ""
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
        "language": _record_value(analysis, "language"),
        "money_terms": _record_value(analysis, "money_terms_json"),
        "price": _record_value(analysis, "recommended_price"),
        "proposal": _record_value(analysis, "proposal_draft"),
        "proposal_content_sha256": _record_value(analysis, "proposal_content_sha256"),
        "score": finite_score(_record_value(analysis, "score", None)),
        "selected_evidence": _record_value(analysis, "selected_evidence"),
        "timeline_terms": _record_value(analysis, "timeline_terms_json"),
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
    language = str(getter("language", "") or "")
    approved = approved_evidence_text(
        str(getter("evidence_case_id", "") or ""), language
    )
    expected_proposal = compose_application_owned_proposal(record)
    stored_version = str(getter("proposal_version", "") or "")
    content_hash = str(getter("proposal_content_sha256", "") or "")
    final_errors = final_composed_proposal_errors(record, proposal)
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
        and not final_errors
        and content_hash == proposal_text_hash(proposal)
        and stored_version.startswith(f"{PROPOSAL_VERSION_PREFIX}:")
        and stored_version == proposal_version(record)
    )
