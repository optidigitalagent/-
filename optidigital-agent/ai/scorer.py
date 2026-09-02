import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging

from config import settings

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ти — AI-асистент для оцінки фріланс-замовлень Antonov Digital. \
Оціни замовлення за шкалою 0–10 і поверни JSON.

Критерії оцінки:

1. Відповідність спеціалізації (0–3 бали):
   - Сайти, боти, AI/ML, CRM, мобільні додатки, автоматизація, парсинг, інтеграції → підходить.
   - SEO-тексти, переклад, дизайн без розробки, поліграфія тощо → 0 балів за цей пункт.

2. Бюджет (0–3 бали):
   - Низький бюджет не є причиною відхилення; оцінюй контроль обсягу та режим CASH/REPUTATION/STRATEGIC.
   - 500–2000 грн → 1 бал, але проєкт може бути стратегічно або репутаційно корисним.
   - 2000–10000 грн → 2 бали.
   - Більше 10000 грн → 3 бали.
   - Бюджет не вказано → 1 бал (можна уточнити на зустрічі).

3. Якість ТЗ (0–2 бали):
   - Детальний опис: вимоги, стек, дедлайн, приклади → 2 бали.
   - Середній опис із деякими деталями → 1 бал.
   - "Зроби сайт" без пояснень → 0 балів.

4. Конкуренція:
   - bid_count > 10 → -2 бали.

5. Пріоритет:
   - Не надавай автоматичного пріоритету окремим service lanes; спирайся на реальний fit, ризик і комерційний ефект.
   - score >= 7 → priority = "high".
   - score 4–6.9 → priority = "medium".
   - score < 4 → priority = "low".

Поверни ТІЛЬКИ валідний JSON без markdown-блоків:
{
  "score": <число 0–10, один десятковий знак>,
  "reason": "<1–2 речення: чому підходить або ні>",
  "red_flags": ["<проблема 1>", "<проблема 2>"],
  "priority": "high" | "medium" | "low"
}

Якщо red_flags відсутні — поверни порожній масив [].
"""


def _format_order(order: dict) -> str:
    budget_from = order.get("budget_from")
    budget_to = order.get("budget_to")
    currency = order.get("currency", "UAH")

    if budget_from and budget_to:
        budget_str = f"{budget_from}–{budget_to} {currency}"
    elif budget_from:
        budget_str = f"від {budget_from} {currency}"
    elif budget_to:
        budget_str = f"до {budget_to} {currency}"
    else:
        budget_str = "не вказано"

    return (
        f"Назва: {order.get('title', '')}\n"
        f"Опис: {order.get('description', '')}\n"
        f"Бюджет: {budget_str}\n"
        f"Кількість відгуків (bid_count): {order.get('bid_count', 0)}\n"
    )


async def score_order(order: dict) -> dict:
    try:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _format_order(order)},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        logger.exception("score_order failed for: %s", order.get("url"))
        return {
            "score": 0.0,
            "reason": "Помилка під час оцінки",
            "red_flags": ["openai_error"],
            "priority": "low",
        }
