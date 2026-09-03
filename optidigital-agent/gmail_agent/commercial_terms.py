"""Strict canonical commercial terms for proposal composition.

Model output is accepted only when the complete field matches the small
allowlisted grammar below.  Proposal text is rendered from these typed values,
never from the original model string.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class Currency(StrEnum):
    UAH = "UAH"
    USD = "USD"
    EUR = "EUR"
    PLN = "PLN"


class PricingMode(StrEnum):
    FIXED = "FIXED"
    RANGE = "RANGE"
    MILESTONE = "MILESTONE"


class TimelineUnit(StrEnum):
    HOURS = "HOURS"
    DAYS = "DAYS"
    WEEKS = "WEEKS"
    MONTHS = "MONTHS"


MAX_MONEY_AMOUNT = Decimal(1000000000)
MAX_TIMELINE_VALUE = 10000
SAFE_RATIONALE_ID = "MODEL_SCOPE_ESTIMATE"

_AMOUNT_TOKEN = r"(?:\d{1,3}(?:[ \u00a0]\d{3})+|\d+)(?:[.,]\d{1,2})?"
_MONEY_RE = re.compile(
    rf"^\s*(?P<minimum>{_AMOUNT_TOKEN})"
    rf"(?:\s*[-–—]\s*(?P<maximum>{_AMOUNT_TOKEN}))?\s*"
    r"(?P<currency>UAH|USD|EUR|PLN|грн|₴|\$|€|zł)"
    r"(?:\s+(?P<milestone>"
    r"as (?:one|two|three|1|2|3) milestones?|"
    r"за (?:один|одна|два|дві|три) етап\w*|"
    r"(?:одним|двома|трьома) етап\w*|"
    r"за (?:один|одна|два|три) этап\w*|"
    r"(?:одним|двумя|тремя) этап\w*|"
    r"jako (?:jeden|jedna|dwa|dwie|trzy) etap\w*"
    r"))?\s*$",
    re.IGNORECASE,
)

_TIMELINE_RE = re.compile(
    r"^\s*(?P<minimum>\d+)"
    r"(?:\s*[-–—]\s*(?P<maximum>\d+))?\s*"
    r"(?P<unit>"
    r"hours?|calendar\s+days?|days?|weeks?|months?|"
    r"годин(?:а|и)?|день|дні|днів|тиждень|тижні|тижнів|місяць|місяці|місяців|"
    r"час|часа|часов|день|дня|дней|неделя|недели|недель|месяц|месяца|месяцев|"
    r"godzina|godziny|godzin|dzień|dni|tydzień|tygodnie|tygodni|"
    r"miesiąc|miesiące|miesięcy"
    r")\s*$",
    re.IGNORECASE,
)

_CURRENCY_ALIASES = {
    "UAH": Currency.UAH,
    "ГРН": Currency.UAH,
    "₴": Currency.UAH,
    "USD": Currency.USD,
    "$": Currency.USD,
    "EUR": Currency.EUR,
    "€": Currency.EUR,
    "PLN": Currency.PLN,
    "ZŁ": Currency.PLN,
}

_MILESTONE_COUNTS = {
    "one": 1,
    "1": 1,
    "один": 1,
    "одна": 1,
    "одним": 1,
    "jeden": 1,
    "jedna": 1,
    "two": 2,
    "2": 2,
    "два": 2,
    "дві": 2,
    "двома": 2,
    "двумя": 2,
    "dwa": 2,
    "dwie": 2,
    "three": 3,
    "3": 3,
    "три": 3,
    "трьома": 3,
    "тремя": 3,
    "trzy": 3,
}


def _decimal_from_token(value: str) -> Decimal | None:
    compact = value.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        parsed = Decimal(compact)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed <= 0 or parsed > MAX_MONEY_AMOUNT:
        return None
    return parsed.normalize()


def _decimal_json_value(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@dataclass(frozen=True, slots=True)
class MoneyTerms:
    min_amount: Decimal
    max_amount: Decimal
    currency: Currency
    pricing_mode: PricingMode
    milestone_count: int | None
    rationale_id: str = SAFE_RATIONALE_ID

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_amount": _decimal_json_value(self.min_amount),
            "max_amount": _decimal_json_value(self.max_amount),
            "currency": self.currency.value,
            "pricing_mode": self.pricing_mode.value,
            "milestone_count": self.milestone_count,
            "rationale_id": self.rationale_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def canonical_model_text(self) -> str:
        amount = _decimal_text(self.min_amount)
        if self.max_amount != self.min_amount:
            amount += f"–{_decimal_text(self.max_amount)}"
        value = f"{amount} {self.currency.value}"
        if self.pricing_mode == PricingMode.MILESTONE:
            words = {1: "one", 2: "two", 3: "three"}
            count = int(self.milestone_count or 0)
            value += f" as {words[count]} milestone{'s' if count != 1 else ''}"
        return value


@dataclass(frozen=True, slots=True)
class TimelineTerms:
    min_value: int
    max_value: int
    unit: TimelineUnit

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"unit": self.unit.value}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def canonical_model_text(self) -> str:
        amount = str(self.min_value)
        if self.max_value != self.min_value:
            amount += f"–{self.max_value}"
        singular = {
            TimelineUnit.HOURS: "hour",
            TimelineUnit.DAYS: "day",
            TimelineUnit.WEEKS: "week",
            TimelineUnit.MONTHS: "month",
        }[self.unit]
        plural = self.max_value != 1 or self.min_value != 1
        return f"{amount} {singular}{'s' if plural else ''}"


def parse_money_terms(value: str) -> MoneyTerms | None:
    """Parse the entire string or reject it; no suffix is ignored."""

    match = _MONEY_RE.fullmatch(str(value or ""))
    if match is None:
        return None
    minimum = _decimal_from_token(match.group("minimum"))
    maximum = _decimal_from_token(match.group("maximum") or match.group("minimum"))
    if minimum is None or maximum is None or maximum < minimum:
        return None
    currency = _CURRENCY_ALIASES.get(match.group("currency").upper())
    if currency is None:
        return None
    milestone_text = (match.group("milestone") or "").casefold()
    milestone_count = None
    if milestone_text:
        milestone_count = next(
            (count for token, count in _MILESTONE_COUNTS.items() if re.search(rf"\b{re.escape(token)}\b", milestone_text)),
            None,
        )
        if milestone_count is None:
            return None
    mode = (
        PricingMode.MILESTONE
        if milestone_count is not None
        else PricingMode.RANGE
        if minimum != maximum
        else PricingMode.FIXED
    )
    return MoneyTerms(minimum, maximum, currency, mode, milestone_count)


def _timeline_unit(token: str) -> TimelineUnit | None:
    value = token.casefold()
    if value.startswith(("hour", "годин", "час", "godzin")):
        return TimelineUnit.HOURS
    if value.startswith(("day", "calendar", "день", "дні", "днів", "дня", "дней", "dzień", "dni")):
        return TimelineUnit.DAYS
    if value.startswith(("week", "тиж", "недел", "tygod")):
        return TimelineUnit.WEEKS
    if value.startswith(("month", "міся", "меся", "miesi")):
        return TimelineUnit.MONTHS
    return None


def parse_timeline_terms(value: str) -> TimelineTerms | None:
    """Parse the entire timeline string or reject it."""

    match = _TIMELINE_RE.fullmatch(str(value or ""))
    if match is None:
        return None
    minimum = int(match.group("minimum"))
    maximum = int(match.group("maximum") or match.group("minimum"))
    unit = _timeline_unit(match.group("unit"))
    if (
        unit is None
        or minimum <= 0
        or maximum < minimum
        or maximum > MAX_TIMELINE_VALUE
    ):
        return None
    return TimelineTerms(minimum, maximum, unit)


def _mapping_from_json(value: str) -> Mapping[str, Any] | None:
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


def money_terms_from_json(value: str) -> MoneyTerms | None:
    data = _mapping_from_json(value)
    if data is None or set(data) != {
        "min_amount", "max_amount", "currency", "pricing_mode",
        "milestone_count", "rationale_id",
    }:
        return None
    try:
        result = MoneyTerms(
            min_amount=Decimal(str(data["min_amount"])),
            max_amount=Decimal(str(data["max_amount"])),
            currency=Currency(str(data["currency"])),
            pricing_mode=PricingMode(str(data["pricing_mode"])),
            milestone_count=(
                None if data["milestone_count"] is None else int(data["milestone_count"])
            ),
            rationale_id=str(data["rationale_id"]),
        )
    except (InvalidOperation, TypeError, ValueError):
        return None
    if (
        not result.min_amount.is_finite()
        or not result.max_amount.is_finite()
        or result.min_amount <= 0
        or result.max_amount < result.min_amount
        or result.max_amount > MAX_MONEY_AMOUNT
        or result.rationale_id != SAFE_RATIONALE_ID
        or (result.pricing_mode == PricingMode.MILESTONE) != (result.milestone_count is not None)
        or result.milestone_count not in {None, 1, 2, 3}
        or (result.pricing_mode == PricingMode.FIXED and result.min_amount != result.max_amount)
        or (result.pricing_mode == PricingMode.RANGE and result.min_amount == result.max_amount)
    ):
        return None
    return result


def timeline_terms_from_json(value: str) -> TimelineTerms | None:
    data = _mapping_from_json(value)
    if data is None or set(data) != {"min_value", "max_value", "unit"}:
        return None
    if (
        not isinstance(data["min_value"], int)
        or isinstance(data["min_value"], bool)
        or not isinstance(data["max_value"], int)
        or isinstance(data["max_value"], bool)
    ):
        return None
    try:
        result = TimelineTerms(
            min_value=data["min_value"],
            max_value=data["max_value"],
            unit=TimelineUnit(str(data["unit"])),
        )
    except (TypeError, ValueError):
        return None
    if result.min_value <= 0 or result.max_value < result.min_value or result.max_value > MAX_TIMELINE_VALUE:
        return None
    return result
