"""AI analyzer — extracts job data from email and scores it 0–10."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import AsyncOpenAI

    from gmail_agent.digest_parser import DigestJobCandidate

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ти — AI-асистент агентства OptiDigital. Отримуєш текст email-сповіщення про нову вакансію/замовлення.

Твоє завдання:
1. Визначити чи це справді оголошення про роботу/замовлення.
2. Якщо так — оцінити наскільки воно підходить для AI/web/bot агентства.
3. Повернути структурований JSON.

Критерії оцінки (score 0–10):

Відповідність спеціалізації (0–3 бали):
- AI, GPT, Claude, LLM, chatbot, автоматизація → 3 бали
- Сайт, landing page, веб-розробка, API, SaaS, MVP → 2 бали
- CRM, ERP, інтеграції, парсинг, Python, React, Node.js → 2 бали
- Telegram-бот, voice AI → 3 бали
- Дизайн без розробки, SEO-тексти, переклад → 0 балів

Бюджет (0–3 бали):
- Менше 500 UAH / 20 USD → 0 балів
- 500–2000 UAH / 20–80 USD → 1 бал
- 2000–10000 UAH / 80–400 USD → 2 бали
- Більше 10000 UAH / 400 USD+ → 3 бали
- Не вказано → 1 бал

Якість опису (0–2 бали):
- Деталі, вимоги, стек → 2 бали
- Середній опис → 1 бал
- "Зроби сайт" → 0 балів

Конкуренція:
- Якщо видно що багато відгуків (>10) → -1 бал

Поверни ТІЛЬКИ валідний JSON (без markdown-блоків):
{
  "is_relevant": true|false,
  "title": "<назва замовлення або вакансії>",
  "platform": "<Freelancehunt|Work.ua|Robota.ua|Upwork|Unknown>",
  "score": <0.0–10.0>,
  "reason": "<1–2 речення чому підходить або ні>",
  "budget": "<бюджет як рядок або 'не вказано'>",
  "url": "<пряме посилання на замовлення або порожній рядок>",
  "urgency": "high|medium|low",
  "why_relevant": "<коротко: що саме в цьому замовленні відповідає спеціалізації>",
  "red_flags": ["<проблема 1>", "<проблема 2>"]
}

Якщо email НЕ є оголошенням про роботу (спам, розсилка без вакансій, системні листи):
  "is_relevant": false, score: 0, решта — порожні рядки.
"""


@dataclass
class JobAnalysis:
    email_id: str
    is_relevant: bool
    title: str
    platform: str
    score: float
    reason: str
    budget: str
    url: str
    urgency: str
    why_relevant: str
    red_flags: list[str] = field(default_factory=list)

    @property
    def score_display(self) -> str:
        return f"{self.score:.1f}/10"


def _format_email(subject: str, sender: str, body: str) -> str:
    # Trim body to avoid huge prompts
    trimmed = body[:3000] if len(body) > 3000 else body
    return (
        f"From: {sender}\n"
        f"Subject: {subject}\n"
        f"Body:\n{trimmed}"
    )


def _extract_json(raw: str) -> dict:
    """Extract JSON from model output, handling potential markdown wrapping."""
    raw = raw.strip()
    # Strip markdown code blocks if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def analyze_email(
    email_id: str,
    subject: str,
    sender: str,
    body: str,
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> JobAnalysis:
    if client is None:
        from openai import AsyncOpenAI
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import settings
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _format_email(subject, sender, body)},
            ],
            temperature=0.1,
            max_tokens=400,
        )
        data = _extract_json(response.choices[0].message.content)
    except Exception:
        logger.exception("analyze_email failed for email_id=%s", email_id)
        data = {}

    return JobAnalysis(
        email_id=email_id,
        is_relevant=bool(data.get("is_relevant", False)),
        title=str(data.get("title", subject)),
        platform=str(data.get("platform", _detect_platform(sender))),
        score=float(data.get("score", 0.0)),
        reason=str(data.get("reason", "")),
        budget=str(data.get("budget", "не вказано")),
        url=str(data.get("url", "")),
        urgency=str(data.get("urgency", "medium")),
        why_relevant=str(data.get("why_relevant", "")),
        red_flags=list(data.get("red_flags", [])),
    )


async def analyze_candidate(
    candidate: "DigestJobCandidate",
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> JobAnalysis:
    """Analyze one parsed digest candidate through the existing scoring flow.

    Only normalized plain-text candidate fields are passed onward; digest HTML
    and unrelated sibling vacancies never enter the model prompt.
    """

    body_lines = [f"Description: {candidate.description}"]
    if candidate.budget:
        body_lines.append(f"Budget: {candidate.budget}")
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
    )

    # The parser's platform and direct URL are deterministic and must not be
    # replaced by a model-generated digest-level or tracking URL.
    analysis.platform = candidate.platform
    analysis.url = candidate.url
    if not analysis.title:
        analysis.title = candidate.title
    if not analysis.budget and candidate.budget:
        analysis.budget = candidate.budget
    return analysis


def _detect_platform(sender: str) -> str:
    s = sender.lower()
    if "freelancehunt" in s:
        return "Freelancehunt"
    if "work.ua" in s:
        return "Work.ua"
    if "robota.ua" in s:
        return "Robota.ua"
    if "upwork" in s:
        return "Upwork"
    return "Unknown"
