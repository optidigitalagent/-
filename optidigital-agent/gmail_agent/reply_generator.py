"""Generates a draft reply for a job based on JobAnalysis."""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
Ти — досвідчений фрілансер з агентства OptiDigital. \
Пишеш відгук на фріланс-замовлення.

Правила:
- Короткий (5–8 речень максимум)
- Впевнений, але не зарозумілий
- Не вигадуй технології або досвід якого немає
- Показуй розуміння задачі
- Пропонуй обговорити деталі
- Мова відповіді: якщо замовлення українською → відповідь українською, якщо російською → українською (ми не пишемо по-російськи), якщо англійською → англійською
- Без шаблонних фраз типу "Готовий до роботи!"
- Без зайвих емодзі

Формат: просто текст відгуку, нічого більше.
"""


async def generate_reply(
    title: str,
    description: str,
    platform: str,
    budget: str,
    url: str,
    client: "Any | None" = None,
    model: str = "gpt-4o-mini",
) -> str:
    if client is None:
        from openai import AsyncOpenAI
        import sys, os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from config import settings
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    user_content = (
        f"Замовлення: {title}\n"
        f"Платформа: {platform}\n"
        f"Бюджет: {budget}\n"
        f"Опис: {description[:1500] if description else '(не вказано)'}\n"
        f"Посилання: {url or '(не вказано)'}"
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.4,
            max_tokens=500,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.exception("generate_reply failed for: %s", title)
        return ""
