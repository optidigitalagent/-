"""Deterministic classification of incoming platform emails."""

from __future__ import annotations

import re
from email.utils import parseaddr
from enum import Enum


class EmailType(str, Enum):
    """Kinds of platform email understood by the Gmail pipeline."""

    SINGLE_JOB = "single_job"
    JOB_DIGEST = "job_digest"
    INFORMATIONAL_NEWSLETTER = "informational_newsletter"
    ACCOUNT_NOTIFICATION = "account_notification"
    MARKETING = "marketing"
    UNKNOWN = "unknown"


_FREELANCEHUNT_DIGEST_SUBJECT = re.compile(
    r"^\s*підбірка\s+(?:вакансій|проєктів|проектів)\b",
    re.IGNORECASE,
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

_ACCOUNT_MARKERS = (
    "підтвердіть акаунт",
    "підтвердження акаунта",
    "зміна пароля",
    "скидання пароля",
    "новий вхід",
    "security alert",
    "verify your account",
    "password reset",
)

_MARKETING_MARKERS = (
    "знижка",
    "розпродаж",
    "спеціальна пропозиція",
    "акція",
    "sale",
    "discount",
)

_SINGLE_JOB_SUBJECT = re.compile(
    r"\b(?:нова\s+вакансія|новий\s+(?:проєкт|проект|job)|new\s+job)\b",
    re.IGNORECASE,
)


def _sender_domain(sender: str) -> str:
    address = parseaddr(sender or "")[1].strip().lower()
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].rstrip(".")


def _is_domain(domain: str, expected: str) -> bool:
    return domain == expected or domain.endswith(f".{expected}")


def _normalized_text(value: str) -> str:
    return " ".join((value or "").casefold().split())


def classify_email(
    sender: str,
    subject: str,
    text_body: str = "",
    html_body: str = "",
) -> EmailType:
    """Classify an email without invoking AI or following any links.

    Freelancehunt digests deliberately require both a trusted sender domain and
    the platform's specific digest subject form.  A generic occurrence of a
    word such as ``вакансія`` is not sufficient.
    """

    domain = _sender_domain(sender)
    normalized_subject = _normalized_text(subject)
    normalized_body = _normalized_text(text_body)
    normalized_html = _normalized_text(html_body)

    if _is_domain(domain, "freelancehunt.com"):
        if _FREELANCEHUNT_DIGEST_SUBJECT.search(normalized_subject):
            return EmailType.JOB_DIGEST
        if _SINGLE_JOB_SUBJECT.search(normalized_subject):
            return EmailType.SINGLE_JOB

    if _is_domain(domain, "work.ua"):
        informational_text = f"{normalized_subject} {normalized_body}"
        if any(marker in informational_text for marker in _WORK_UA_INFORMATIONAL_MARKERS):
            return EmailType.INFORMATIONAL_NEWSLETTER
        if "/articles/" in normalized_html:
            return EmailType.INFORMATIONAL_NEWSLETTER
        if "нові вакансії" in normalized_subject or "добірка вакансій" in normalized_subject:
            return EmailType.JOB_DIGEST
        if _SINGLE_JOB_SUBJECT.search(normalized_subject):
            return EmailType.SINGLE_JOB

    combined = f"{normalized_subject} {normalized_body}"
    if any(marker in combined for marker in _ACCOUNT_MARKERS):
        return EmailType.ACCOUNT_NOTIFICATION
    if any(marker in combined for marker in _MARKETING_MARKERS):
        return EmailType.MARKETING

    return EmailType.UNKNOWN
