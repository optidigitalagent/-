"""Deterministic multilingual classification of incoming platform emails."""

from __future__ import annotations

import re
from email.utils import parseaddr
from enum import Enum


class EmailType(str, Enum):
    """Stable event types persisted by the Gmail revenue pipeline."""

    PROJECT_SINGLE = "PROJECT_SINGLE"
    PROJECT_DIGEST = "PROJECT_DIGEST"
    PROJECT_FEED = "PROJECT_FEED"
    CLIENT_PRIVATE_MESSAGE = "CLIENT_PRIVATE_MESSAGE"
    PROJECT_STATUS_EVENT = "PROJECT_STATUS_EVENT"
    WORKSPACE_OR_CONTRACT_EVENT = "WORKSPACE_OR_CONTRACT_EVENT"
    ACCOUNT_OR_SECURITY_EVENT = "ACCOUNT_OR_SECURITY_EVENT"
    MARKETING = "MARKETING"
    UNKNOWN = "UNKNOWN"

    # Backward-compatible names used by the Stage 1 implementation/tests.
    SINGLE_JOB = PROJECT_SINGLE
    JOB_DIGEST = PROJECT_DIGEST
    ACCOUNT_NOTIFICATION = ACCOUNT_OR_SECURITY_EVENT
    INFORMATIONAL_NEWSLETTER = MARKETING


_PRIVATE_MESSAGE_SUBJECT = re.compile(
    r"(?:"
    r"нове\s+особисте\s+повідомлення\s+від|"
    r"новое\s+личное\s+сообщение\s+от|"
    r"new\s+private\s+message\s+from|"
    r"(?:nowa\s+)?wiadomo(?:ś|s)ć\s+prywatna\s+od"
    r")",
    re.IGNORECASE,
)

_DIGEST_SUBJECT = re.compile(
    r"(?:"
    r"підбірка\s+(?:вакансій|проєктів|проектів)|"
    r"подборка\s+(?:вакансий|проектов)|"
    r"(?:daily\s+)?(?:project|job)\s+digest|"
    r"(?:new|matching)\s+(?:projects|jobs)\s+for\s+you|"
    r"(?:zestawienie|wybór|lista)\s+(?:projektów|ofert)|"
    r"nowe\s+projekty\s+dla\s+ciebie"
    r")",
    re.IGNORECASE,
)

_SINGLE_PROJECT_SUBJECT = re.compile(
    r"(?:"
    r"новий\s+(?:проєкт|проект)|"
    r"новый\s+проект|"
    r"new\s+(?:project|job)|"
    r"nowy\s+projekt|"
    r"нова\s+вакансія|"
    r"new\s+vacancy"
    r")",
    re.IGNORECASE,
)

_PROJECT_STATUS_MARKERS = (
    "статус проєкту",
    "статус проекту",
    "статус проекта",
    "проєкт закрито",
    "проект закрыт",
    "вашу ставку",
    "вашу заявку",
    "your bid",
    "project status",
    "project was closed",
    "project has been closed",
    "status projektu",
    "projekt został zamknięty",
    "wybrano wykonawcę",
)

_WORKSPACE_MARKERS = (
    "workspace",
    "робоча область",
    "рабочая область",
    "резервування коштів",
    "резервирование средств",
    "safe payment",
    "сейф",
    "контракт",
    "угода",
    "договір",
    "договор",
    "milestone",
    "contract",
    "agreement",
    "umowa",
    "obszar roboczy",
    "rezerwacja środków",
)

_ACCOUNT_OR_SECURITY_MARKERS = (
    "підтвердіть акаунт",
    "підтвердження акаунта",
    "верифікац",
    "верификац",
    "зміна пароля",
    "скидання пароля",
    "сброс пароля",
    "новий вхід",
    "новый вход",
    "код підтвердження",
    "код подтверждения",
    "одноразовий код",
    "одноразовый код",
    "security alert",
    "verify your account",
    "password reset",
    "new sign-in",
    "one-time code",
    "account notice",
    "alert bezpieczeństwa",
    "resetowanie hasła",
    "nowe logowanie",
    "kod jednorazowy",
)

_MARKETING_MARKERS = (
    "знижка",
    "розпродаж",
    "спеціальна пропозиція",
    "акція",
    "новини freelancehunt",
    "дайджест блогу",
    "распродаж",
    "скидк",
    "sale",
    "discount",
    "special offer",
    "newsletter",
    "promocja",
    "rabat",
)

_WORK_UA_INFORMATIONAL_MARKERS = (
    "ринок праці",
    "дослідження",
    "статті",
    "стаття",
    "поради",
    "як скласти резюме",
    "кар'єр",
    "кар’єр",
)

_PROJECT_LINK_EVIDENCE = re.compile(
    r"freelancehunt\.com/(?:ua/)?(?:project|job)/[^\s<>\"']+/\d+\.html",
    re.IGNORECASE,
)


def sender_domain(sender: str) -> str:
    """Return a normalized RFC 5322 sender domain."""

    address = parseaddr(sender or "")[1].strip().lower()
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].rstrip(".")


def is_domain(domain: str, expected: str) -> bool:
    return domain == expected or domain.endswith(f".{expected}")


def is_trusted_freelancehunt_sender(sender: str) -> bool:
    return is_domain(sender_domain(sender), "freelancehunt.com")


def _normalized_text(value: str) -> str:
    return " ".join((value or "").casefold().split())


def classify_email(
    sender: str,
    subject: str,
    text_body: str = "",
    html_body: str = "",
) -> EmailType:
    """Classify from trusted sender identity plus multilingual evidence.

    Freelancehunt types require an authenticated-looking platform sender domain.
    This prevents a personal email from becoming an actionable platform event
    merely by copying a subject line.
    """

    domain = sender_domain(sender)
    normalized_subject = _normalized_text(subject)
    normalized_body = _normalized_text(text_body)
    normalized_html = _normalized_text(html_body)
    combined = f"{normalized_subject} {normalized_body} {normalized_html}"

    if is_domain(domain, "freelancehunt.com"):
        if _PRIVATE_MESSAGE_SUBJECT.search(normalized_subject):
            return EmailType.CLIENT_PRIVATE_MESSAGE
        if _DIGEST_SUBJECT.search(normalized_subject):
            return EmailType.PROJECT_DIGEST
        if _SINGLE_PROJECT_SUBJECT.search(normalized_subject):
            return EmailType.PROJECT_SINGLE
        if any(marker in normalized_subject for marker in _WORKSPACE_MARKERS):
            return EmailType.WORKSPACE_OR_CONTRACT_EVENT
        if any(marker in normalized_subject for marker in _PROJECT_STATUS_MARKERS):
            return EmailType.PROJECT_STATUS_EVENT
        if any(marker in combined for marker in _ACCOUNT_OR_SECURITY_MARKERS):
            return EmailType.ACCOUNT_OR_SECURITY_EVENT
        if any(marker in combined for marker in _MARKETING_MARKERS):
            return EmailType.MARKETING
        if _PROJECT_LINK_EVIDENCE.search(combined):
            return EmailType.PROJECT_SINGLE
        return EmailType.UNKNOWN

    # Preserve the existing non-Freelancehunt job-alert behavior.
    if is_domain(domain, "work.ua"):
        informational_text = f"{normalized_subject} {normalized_body}"
        if any(marker in informational_text for marker in _WORK_UA_INFORMATIONAL_MARKERS):
            return EmailType.MARKETING
        if "/articles/" in normalized_html:
            return EmailType.MARKETING
        if "нові вакансії" in normalized_subject or "добірка вакансій" in normalized_subject:
            return EmailType.PROJECT_DIGEST
        if _SINGLE_PROJECT_SUBJECT.search(normalized_subject):
            return EmailType.PROJECT_SINGLE

    if any(marker in combined for marker in _ACCOUNT_OR_SECURITY_MARKERS):
        return EmailType.ACCOUNT_OR_SECURITY_EVENT
    if any(marker in combined for marker in _MARKETING_MARKERS):
        return EmailType.MARKETING
    return EmailType.UNKNOWN
