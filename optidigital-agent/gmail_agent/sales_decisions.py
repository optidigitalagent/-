"""Turn-scoped human decisions and application-owned commitment clauses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from .commercial_terms import (
    MoneyTerms,
    TimelineTerms,
    money_terms_from_json,
    parse_money_terms,
    parse_timeline_terms,
    timeline_terms_from_json,
)
from .quality_gate import (
    EVIDENCE_REGISTRY,
    approved_evidence_text,
    contains_external_contact,
)
from .sales_storage import HumanInformationRequest, SalesOpportunity


@dataclass(frozen=True, slots=True)
class HumanDecision:
    request_id: str
    source_turn_id: str
    intent: str
    subject_fingerprint: str
    code: str
    text: str = ""
    canonical_money_json: str = ""
    canonical_timeline_json: str = ""
    approved_availability_json: str = ""
    approved_evidence_case_id: str = ""


class HumanDecisionError(ValueError):
    pass


def parse_human_decision(
    request: HumanInformationRequest, raw_answer: str
) -> HumanDecision:
    raw = str(raw_answer or "").strip()
    code, separator, detail = raw.partition("|")
    code = code.strip().upper()
    detail = detail.strip() if separator else ""
    allowed: dict[str, set[str]] = {
        "TECHNICAL_QUESTION": {"YES", "NO", "NEED_DOCS"},
        "SCOPE_CHANGE": {
            "INCLUDE_IN_CURRENT_SCOPE",
            "SEPARATE_PAID_ESTIMATE",
            "DECLINE",
        },
        "PRICE_OBJECTION": {"KEEP_CURRENT_PRICE", "COUNTER_PRICE"},
        "TIMELINE_OBJECTION": {"KEEP_CURRENT_TIMELINE", "EARLIEST_TIMELINE"},
        "CALL_REQUEST": {"APPROVED_WINDOWS", "NOT_AVAILABLE", "NEED_CLIENT_OPTIONS"},
        "PORTFOLIO_OR_PROOF_REQUEST": set(EVIDENCE_REGISTRY) | {
            "NO_DIRECT_CASE", "DEMO_REQUIRED"
        },
    }
    if code not in allowed.get(request.intent, set()):
        choices = ", ".join(sorted(allowed.get(request.intent, set())))
        raise HumanDecisionError(f"invalid answer code; allowed: {choices}")

    money_json = ""
    timeline_json = ""
    availability_json = ""
    evidence_case_id = ""
    if code == "COUNTER_PRICE":
        terms = parse_money_terms(detail)
        if terms is None:
            raise HumanDecisionError("COUNTER_PRICE requires canonical MoneyTerms after |")
        money_json = terms.to_json()
        detail = terms.canonical_model_text()
    elif code == "EARLIEST_TIMELINE":
        terms = parse_timeline_terms(detail)
        if terms is None:
            raise HumanDecisionError(
                "EARLIEST_TIMELINE requires canonical TimelineTerms after |"
            )
        timeline_json = terms.to_json()
        detail = terms.canonical_model_text()
    elif code == "APPROVED_WINDOWS":
        if not detail or len(detail) > 500:
            raise HumanDecisionError("APPROVED_WINDOWS requires exact windows after |")
        contact_check = re.sub(
            r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}:\d{2}\b", " ", detail
        )
        if contains_external_contact(contact_check):
            raise HumanDecisionError(
                "APPROVED_WINDOWS cannot contain contact coordinates or external links"
            )
        availability_json = json.dumps([detail], ensure_ascii=False)
    elif request.intent == "PORTFOLIO_OR_PROOF_REQUEST":
        evidence_case_id = code
        if code not in {"NO_DIRECT_CASE", "DEMO_REQUIRED"} and not approved_evidence_text(
            evidence_case_id, "en"
        ):
            raise HumanDecisionError("approved evidence case is not in the Stage 4 registry")

    return HumanDecision(
        request_id=request.id,
        source_turn_id=request.source_turn_id,
        intent=request.intent,
        subject_fingerprint=request.subject_fingerprint,
        code=code,
        text=detail,
        canonical_money_json=money_json,
        canonical_timeline_json=timeline_json,
        approved_availability_json=availability_json,
        approved_evidence_case_id=evidence_case_id,
    )


def decision_from_request(request: HumanInformationRequest) -> HumanDecision | None:
    if request.status != "ANSWERED" or not request.answer_code:
        return None
    return HumanDecision(
        request_id=request.id,
        source_turn_id=request.source_turn_id,
        intent=request.intent,
        subject_fingerprint=request.subject_fingerprint,
        code=request.answer_code,
        text=request.answer_text,
        canonical_money_json=request.canonical_money_json,
        canonical_timeline_json=request.canonical_timeline_json,
        approved_availability_json=request.approved_availability_json,
        approved_evidence_case_id=request.approved_evidence_case_id,
    )


def application_owned_decision_reply(
    decision: HumanDecision,
    language: str,
    opportunity: SalesOpportunity,
) -> str:
    lang = language if language in {"uk", "ru", "en", "pl"} else "en"
    code = decision.code
    if decision.intent == "TECHNICAL_QUESTION":
        messages = {
            "YES": {
                "uk": "Можемо підтвердити підтримку саме цієї запитаної інтеграції в погодженому обсязі.",
                "ru": "Можем подтвердить поддержку именно этой запрошенной интеграции в согласованном объёме.",
                "en": "We can confirm support for this specific requested integration within the agreed scope.",
                "pl": "Możemy potwierdzić obsługę dokładnie tej integracji w uzgodnionym zakresie.",
            },
            "NO": {
                "uk": "Не можемо підтвердити реалізацію саме цієї запитаної інтеграції в поточному обсязі.",
                "ru": "Не можем подтвердить реализацию именно этой запрошенной интеграции в текущем объёме.",
                "en": "We cannot confirm implementation of this specific requested integration within the current scope.",
                "pl": "Nie możemy potwierdzić realizacji dokładnie tej integracji w obecnym zakresie.",
            },
            "NEED_DOCS": {
                "uk": "Потрібна документація саме цієї інтеграції, перш ніж підтверджувати реалізацію. Чи можете додати її у Freelancehunt Workspace?",
                "ru": "Нужна документация именно этой интеграции, прежде чем подтверждать реализацию. Можете добавить её в Freelancehunt Workspace?",
                "en": "We need the documentation for this specific integration before confirming implementation. Could you add it in the Freelancehunt Workspace?",
                "pl": "Potrzebujemy dokumentacji dokładnie tej integracji przed potwierdzeniem realizacji. Czy możesz dodać ją w obszarze Freelancehunt Workspace?",
            },
        }
        return messages[code][lang]
    if decision.intent == "SCOPE_CHANGE":
        messages = {
            "SEPARATE_PAID_ESTIMATE": {
                "uk": "Ця додаткова вимога не входить до поточного обсягу. Підготуємо для неї окрему платну оцінку як новий етап; поточні ціна і строк її не включають.",
                "ru": "Это дополнительное требование не входит в текущий объём. Подготовим для него отдельную платную оценку как новый этап; текущие цена и срок его не включают.",
                "en": "This additional requirement is outside the current scope. We will prepare a separate paid estimate as a new milestone; the current price and timeline do not include it.",
                "pl": "To dodatkowe wymaganie nie wchodzi w obecny zakres. Przygotujemy osobną płatną wycenę jako nowy etap; obecna cena i termin go nie obejmują.",
            },
            "INCLUDE_IN_CURRENT_SCOPE": {
                "uk": "Підтверджуємо включення саме цієї додаткової вимоги до поточного обсягу згідно з окремим внутрішнім погодженням.",
                "ru": "Подтверждаем включение именно этого дополнительного требования в текущий объём согласно отдельному внутреннему согласованию.",
                "en": "We confirm that this specific additional requirement is included in the current scope under the separate internal approval.",
                "pl": "Potwierdzamy włączenie dokładnie tego dodatkowego wymagania do obecnego zakresu na podstawie osobnej zgody wewnętrznej.",
            },
            "DECLINE": {
                "uk": "Не можемо включити цю додаткову вимогу до проєкту, оскільки вона виходить за погоджений обсяг.",
                "ru": "Не можем включить это дополнительное требование в проект, поскольку оно выходит за согласованный объём.",
                "en": "We cannot include this additional requirement because it is outside the agreed project scope.",
                "pl": "Nie możemy uwzględnić tego dodatkowego wymagania, ponieważ wykracza poza uzgodniony zakres projektu.",
            },
        }
        return messages[code][lang]
    if decision.intent == "PRICE_OBJECTION":
        terms = (
            money_terms_from_json(decision.canonical_money_json)
            if code == "COUNTER_PRICE"
            else parse_money_terms(opportunity.actual_submitted_price)
        )
        if terms is None:
            raise HumanDecisionError("approved canonical price is unavailable")
        price = terms.canonical_model_text()
        templates = {
            "uk": "Підтверджена ціна для погодженого обсягу: {value}.",
            "ru": "Подтверждённая цена для согласованного объёма: {value}.",
            "en": "The approved price for the agreed scope is {value}.",
            "pl": "Zatwierdzona cena za uzgodniony zakres to {value}.",
        }
        return templates[lang].format(value=price)
    if decision.intent == "TIMELINE_OBJECTION":
        terms = (
            timeline_terms_from_json(decision.canonical_timeline_json)
            if code == "EARLIEST_TIMELINE"
            else parse_timeline_terms(opportunity.actual_submitted_timeline)
        )
        if terms is None:
            raise HumanDecisionError("approved canonical timeline is unavailable")
        timeline = terms.canonical_model_text()
        templates = {
            "uk": "Підтверджений строк для погодженого обсягу: {value}.",
            "ru": "Подтверждённый срок для согласованного объёма: {value}.",
            "en": "The approved timeline for the agreed scope is {value}.",
            "pl": "Zatwierdzony termin dla uzgodnionego zakresu to {value}.",
        }
        return templates[lang].format(value=timeline)
    if decision.intent == "CALL_REQUEST":
        if code == "APPROVED_WINDOWS":
            windows = json.loads(decision.approved_availability_json)[0]
            templates = {
                "uk": "Підтверджене доступне вікно для дзвінка: {value}.",
                "ru": "Подтверждённое доступное окно для звонка: {value}.",
                "en": "The approved available call window is: {value}.",
                "pl": "Zatwierdzone dostępne okno rozmowy: {value}.",
            }
            return templates[lang].format(value=windows)
        messages = {
            "NOT_AVAILABLE": {
                "uk": "Наразі не можемо підтвердити доступне вікно для дзвінка; продовжимо письмово у Freelancehunt.",
                "ru": "Сейчас не можем подтвердить доступное окно для звонка; продолжим письменно во Freelancehunt.",
                "en": "We cannot confirm an available call window now; we can continue in writing on Freelancehunt.",
                "pl": "Nie możemy teraz potwierdzić dostępnego terminu rozmowy; możemy kontynuować pisemnie na Freelancehunt.",
            },
            "NEED_CLIENT_OPTIONS": {
                "uk": "Потрібно узгодити час. Будь ласка, запропонуйте одне або два зручні вікна у Freelancehunt.",
                "ru": "Нужно согласовать время. Пожалуйста, предложите одно или два удобных окна во Freelancehunt.",
                "en": "We need to coordinate the time. Please suggest one or two suitable windows on Freelancehunt.",
                "pl": "Musimy uzgodnić termin. Proszę zaproponować jedno lub dwa dogodne okna na Freelancehunt.",
            },
        }
        return messages[code][lang]
    if decision.intent == "PORTFOLIO_OR_PROOF_REQUEST":
        return application_owned_proof_reply(decision.approved_evidence_case_id, lang)
    raise HumanDecisionError("unsupported turn-scoped decision")


def application_owned_proof_reply(case_id: str, language: str) -> str:
    lang = language if language in {"uk", "ru", "en", "pl"} else "en"
    if case_id == "NO_DIRECT_CASE":
        return {
            "uk": "Прямого підтвердженого клієнтського кейсу саме для цього запиту немає; не будемо подавати інший проєкт як еквівалентний.",
            "ru": "Прямого подтверждённого клиентского кейса именно для этого запроса нет; мы не будем выдавать другой проект за эквивалентный.",
            "en": "We do not have a confirmed direct client case for this exact request, and will not present a different project as equivalent.",
            "pl": "Nie mamy potwierdzonego bezpośredniego przypadku klienta dla tego dokładnego zapytania i nie przedstawimy innego projektu jako równoważnego.",
        }[lang]
    if case_id == "DEMO_REQUIRED":
        return {
            "uk": "Для цього запиту потрібна окрема демонстрація; до її підготовки не будемо стверджувати, що існує прямий клієнтський кейс.",
            "ru": "Для этого запроса нужна отдельная демонстрация; до её подготовки мы не будем утверждать, что есть прямой клиентский кейс.",
            "en": "This request needs a separate demonstration; until it is prepared, we will not claim a direct client case exists.",
            "pl": "To zapytanie wymaga osobnej demonstracji; dopóki nie zostanie przygotowana, nie będziemy twierdzić, że istnieje bezpośredni przypadek klienta.",
        }[lang]
    evidence = approved_evidence_text(case_id, lang)
    if not evidence:
        raise HumanDecisionError("approved evidence is unavailable")
    intro = {
        "uk": "Розуміємо запит на релевантне підтвердження.",
        "ru": "Понимаем запрос на релевантное подтверждение.",
        "en": "We understand the request for relevant proof.",
        "pl": "Rozumiemy prośbę o odpowiednie potwierdzenie.",
    }[lang]
    return f"{intro} {evidence}"


def application_owned_sensitive_reply(intent: str, language: str) -> str | None:
    lang = language if language in {"uk", "ru", "en", "pl"} else "en"
    if intent == "ACCESS_REQUEST":
        return {
            "uk": "Паролі, одноразові коди та секретні ключі не можна надсилати в повідомленні. Після перевірки умов Freelancehunt Workspace надайте лише мінімальний доступ за принципом найменших привілеїв безпечним способом, дозволеним платформою.",
            "ru": "Пароли, одноразовые коды и секретные ключи нельзя отправлять в сообщении. После проверки условий Freelancehunt Workspace предоставьте только минимальный доступ по принципу наименьших привилегий безопасным способом, разрешённым платформой.",
            "en": "Passwords, one-time codes, and secret keys must not be sent in a message. After the Freelancehunt Workspace terms are reviewed, grant only the minimum least-privilege access through a secure method allowed by the platform.",
            "pl": "Haseł, kodów jednorazowych ani tajnych kluczy nie wolno wysyłać w wiadomości. Po sprawdzeniu warunków Freelancehunt Workspace przyznaj tylko minimalny dostęp bezpieczną metodą dozwoloną przez platformę.",
        }[lang]
    if intent == "CLIENT_READY_TO_SELECT":
        return {
            "uk": "Дякуємо. Перед підтвердженням початку перевіримо умови проєкту в Робочій області Freelancehunt.",
            "ru": "Спасибо. Перед подтверждением начала проверим условия проекта в Рабочей области Freelancehunt.",
            "en": "Thank you. Before confirming the start, we will review the project terms in the Freelancehunt Workspace.",
            "pl": "Dziękujemy. Przed potwierdzeniem rozpoczęcia sprawdzimy warunki projektu w obszarze Freelancehunt Workspace.",
        }[lang]
    if intent == "SELECTED_OR_CONTRACT_STEP":
        return {
            "uk": "Дякуємо. Перед підтвердженням перевіримо умови договору та Робочої області Freelancehunt.",
            "ru": "Спасибо. Перед подтверждением проверим условия договора и Рабочей области Freelancehunt.",
            "en": "Thank you. Before confirming, we will review the contract and Freelancehunt Workspace terms.",
            "pl": "Dziękujemy. Przed potwierdzeniem sprawdzimy warunki umowy i obszaru Freelancehunt Workspace.",
        }[lang]
    return None


def human_decision_errors(
    reply: str,
    decision: HumanDecision | None,
    opportunity: SalesOpportunity,
) -> list[str]:
    if decision is None:
        return []
    value = " ".join(str(reply or "").casefold().split())
    errors: list[str] = []
    affirmative = re.search(
        r"\b(?:we can|we will|can implement|можем|реализуем|можемо|реалізуємо|możemy|zrealizujemy)\b",
        value,
    )
    if decision.intent == "TECHNICAL_QUESTION":
        if decision.code in {"NO", "NEED_DOCS"} and affirmative:
            errors.append("technical_decision_contradiction")
        if decision.code == "YES" and re.search(
            r"\b(?:all|any|every|любой|все|будь-як|усі|dowoln|wszystk)\w*\s+(?:api|integration|інтеграц|интеграц)",
            value,
        ):
            errors.append("technical_capability_amplified")
    if decision.intent == "SCOPE_CHANGE":
        required = {
            "SEPARATE_PAID_ESTIMATE": (
                "outside the current scope", "separate paid estimate", "не входит в текущий объём",
                "отдельную платную оценку", "не входить до поточного обсягу",
                "окрему платну оцінку", "nie wchodzi w obecny zakres", "osobną płatną wycenę",
            ),
            "INCLUDE_IN_CURRENT_SCOPE": (
                "included in the current scope", "включение именно этого", "включення саме цієї",
                "włączenie dokładnie tego",
            ),
            "DECLINE": ("cannot include", "не можем включить", "не можемо включити", "nie możemy uwzględnić"),
        }[decision.code]
        if not any(marker in value for marker in required):
            errors.append("scope_decision_not_enforced")
    if decision.intent == "PRICE_OBJECTION":
        terms: MoneyTerms | None = (
            money_terms_from_json(decision.canonical_money_json)
            if decision.code == "COUNTER_PRICE"
            else parse_money_terms(opportunity.actual_submitted_price)
        )
        if terms and terms.canonical_model_text().casefold() not in value:
            errors.append("approved_price_missing")
    if decision.intent == "TIMELINE_OBJECTION":
        terms: TimelineTerms | None = (
            timeline_terms_from_json(decision.canonical_timeline_json)
            if decision.code == "EARLIEST_TIMELINE"
            else parse_timeline_terms(opportunity.actual_submitted_timeline)
        )
        if terms and terms.canonical_model_text().casefold() not in value:
            errors.append("approved_timeline_missing")
    if decision.intent == "CALL_REQUEST" and decision.code == "APPROVED_WINDOWS":
        windows = json.loads(decision.approved_availability_json)
        if len(windows) != 1 or windows[0].casefold() not in value:
            errors.append("approved_call_window_missing")
    if decision.intent == "PORTFOLIO_OR_PROOF_REQUEST":
        if decision.code in {"NO_DIRECT_CASE", "DEMO_REQUIRED"}:
            if contains_case_success_claim(reply):
                errors.append("unapproved_direct_case_claim")
            return errors
        exact = approved_evidence_text(
            decision.approved_evidence_case_id,
            _language_from_reply(reply),
        )
        if not exact or exact.casefold() not in value:
            errors.append("approved_evidence_clause_missing")
    return errors


def contains_case_success_claim(reply: str) -> bool:
    return bool(
        re.search(
            r"(?:our client case|we delivered for (?:a|the) client|completed client project|"
            r"наш клиентский кейс|выполнили для клиента|наш клієнтський кейс|"
            r"виконали для клієнта|nasz przypadek klienta|zrealizowaliśmy dla klienta)",
            str(reply or "").casefold(),
        )
    )


def access_or_contract_errors(reply: str, intent: str) -> list[str]:
    value = " ".join(str(reply or "").casefold().split())
    errors: list[str] = []
    if intent == "ACCESS_REQUEST":
        asks_secret = re.search(
            r"(?:send|share|provide|give|переда|пришл|отправ|надішл|prześlij|podaj)"
            r".{0,48}(?:password|otp|one-time|recovery code|api secret|secret key|token|"
            r"парол|одноразов|код восстанов|секрет|токен|hasł|kod jednoraz|tajny klucz)",
            value,
        )
        if asks_secret:
            errors.append("unsafe_secret_request")
        if re.search(
            r"(?:access (?:was|is) received|доступ (?:уже )?получен|доступ (?:вже )?отримано|dostęp (?:już )?otrzyman)",
            value,
        ):
            errors.append("unconfirmed_access_receipt")
    if intent in {"CLIENT_READY_TO_SELECT", "SELECTED_OR_CONTRACT_STEP"}:
        if re.search(
            r"(?:we accept|we agree to (?:the )?terms|confirm (?:the )?payment|reserve (?:the )?funds|"
            r"принимаем договор|согласны с условиями|подтверждаем оплату|можете резервировать|"
            r"приймаємо договір|погоджуємося з умовами|підтверджуємо оплату|"
            r"akceptujemy umowę|zgadzamy się na warunki|potwierdzamy płatność)",
            value,
        ):
            errors.append("contract_or_payment_acceptance")
    return errors


def _language_from_reply(reply: str) -> str:
    value = str(reply or "").casefold()
    if re.search(r"[іїєґ]", value):
        return "uk"
    if re.search(r"[ыэъё]", value):
        return "ru"
    if re.search(r"[ąćęłńóśźż]", value):
        return "pl"
    return "en"
