import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from config import settings

logger = logging.getLogger(__name__)

_MAX_CHARS = 800

_SYSTEM_PROMPT = """\
Ти пишеш відгуки на фріланс-замовлення від імені агентства OptiDigital.

Про агентство:
- Команда 4 людини: Founder + AI-розробник, AI Architect, 2 Full-stack розробники.
- Портфоліо: сайти для піцерії, ресторану, IT-школи; CRM-система для мережі салонів краси; \
AI-стартап (MVP із нуля до продакшну).
- Спеціалізація: AI-рішення, Telegram-боти, автоматизація бізнес-процесів, CRM, \
веб-сайти під ключ, парсинг та інтеграції.

Правила написання відгуку:
- Жорсткий ліміт — 800 символів. Вкладись у ліміт.
- Стиль: впевнено, конкретно, без води, без шаблонних фраз і кліше.
- НЕ починай з "Привіт!", "Доброго дня!", "Ми готові допомогти" та подібного.
- Одразу з місця: перший рядок — цінність або конкретний досвід.
- Згадай 1–2 релевантних кейси з портфоліо якщо вони справді підходять до замовлення.
- Назви конкретні технології або підхід для цього проекту.
- Завершуй закликом до дії: "Напишіть — обговоримо деталі та стартуємо."
- Пиши виключно українською мовою.
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
        f"Замовлення: {order.get('title', '')}\n"
        f"Опис: {order.get('description', '')}\n"
        f"Бюджет: {budget_str}\n"
    )


async def generate_response(order: dict) -> str:
    try:
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _format_order(order)},
            ],
            temperature=0.7,
            max_tokens=400,
        )
        text = response.choices[0].message.content.strip()
        return text[:_MAX_CHARS] if len(text) > _MAX_CHARS else text
    except Exception:
        logger.exception("generate_response failed for: %s", order.get("url"))
        return ""
