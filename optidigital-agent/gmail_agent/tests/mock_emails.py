"""Mock email fixtures for testing."""

from datetime import datetime

from gmail_agent.gmail_provider import EmailMessage

# ── Relevant emails (should score >= 6) ──────────────────────────────────────

EMAIL_FREELANCEHUNT_AI_BOT = EmailMessage(
    id="mock_fh_001",
    subject="Новий проект: Розробка Telegram-бота з AI-асистентом",
    sender="noreply@freelancehunt.com",
    body="""
Вітаємо!

На Freelancehunt з'явився новий проект, який може вас зацікавити:

Назва: Розробка Telegram-бота з AI-асистентом для магазину
Бюджет: 8000–15000 UAH
Замовник: TechStore UA
Категорія: Боти / Автоматизація

Опис:
Потрібен Telegram-бот для інтернет-магазину електроніки.
Бот повинен:
- Відповідати на запитання клієнтів через ChatGPT API
- Обробляти замовлення
- Інтеграція з CRM системою
- Надсилати push-сповіщення

Стек: Python, aiogram, OpenAI API, PostgreSQL

Переглянути проект: https://freelancehunt.com/project/telegram-bot-ai-assistant/12345.html
""",
    received_at=datetime(2026, 6, 4, 10, 0, 0),
)

EMAIL_WORKUA_REACT_DEVELOPER = EmailEmail = EmailMessage(
    id="mock_wu_002",
    subject="Нові вакансії відповідно до ваших налаштувань — Work.ua",
    sender="notifications@work.ua",
    body="""
Для вас знайшлися нові вакансії:

1. React Developer (Full-stack)
   Компанія: SaaS Startup
   Зарплата: $2000–3500/міс
   Місто: Remote
   Опис: Розробка SaaS-платформи для автоматизації HR-процесів.
   Стек: React, Node.js, PostgreSQL, Docker, AWS
   https://www.work.ua/jobs/react-developer-fullstack/789012/

2. Python Backend Developer
   Компанія: AI Solutions Ltd
   Зарплата: $1500–2500/міс
   Описr: API розробка, мікросервіси, ML pipeline інтеграція
   https://www.work.ua/jobs/python-backend-ai/789013/
""",
    received_at=datetime(2026, 6, 4, 9, 0, 0),
)

EMAIL_UPWORK_AUTOMATION = EmailMessage(
    id="mock_uw_003",
    subject="Jobs matching your profile: AI Agent Developer",
    sender="donotreply@upwork.com",
    body="""
Hi there,

Here are new jobs matching your skills:

Job: Build AI Agent for Customer Support Automation
Budget: $500–1500 Fixed
Client: Verified (5 stars, 47 hires)
Description:
We need an experienced developer to build an AI-powered customer support agent
using Claude or GPT-4. The agent should:
- Handle customer inquiries via API
- Integrate with Zendesk
- Use RAG for knowledge base
- Deploy on AWS Lambda

Skills: Python, LangChain/LlamaIndex, Claude API, AWS
Apply: https://www.upwork.com/jobs/~01abc123def456

---
Job: Telegram Bot for E-commerce Notifications
Budget: $200–400 Fixed
Description: Simple Telegram bot to send order status updates from Shopify.
Apply: https://www.upwork.com/jobs/~01xyz789
""",
    received_at=datetime(2026, 6, 4, 8, 0, 0),
)

# ── Not relevant emails (should be filtered out) ─────────────────────────────

EMAIL_SPAM_NEWSLETTER = EmailMessage(
    id="mock_spam_004",
    subject="Знижки до 50% на всі курси — тільки сьогодні!",
    sender="promo@somecourses.ua",
    body="""
Тільки сьогодні! Знижки до 50% на всі онлайн-курси.
Курс Python — 499 грн (зазвичай 999 грн)
Курс React — 599 грн
Реєструйся зараз: https://somecourses.ua/sale
""",
    received_at=datetime(2026, 6, 4, 7, 0, 0),
)

EMAIL_FREELANCEHUNT_LOW_BUDGET = EmailMessage(
    id="mock_fh_005",
    subject="Новий проект: Написати 10 статей для блогу",
    sender="noreply@freelancehunt.com",
    body="""
Новий проект на Freelancehunt:

Назва: Написати 10 статей для блогу про моду (500 слів кожна)
Бюджет: 300 UAH
Категорія: Копірайтинг / Тексти

Потрібен копірайтер для написання статей про моду та стиль.
Теми надамо. Унікальність 95%+.

Переглянути: https://freelancehunt.com/project/articles-fashion/99999.html
""",
    received_at=datetime(2026, 6, 4, 6, 0, 0),
)


ALL_MOCK_EMAILS = [
    EMAIL_FREELANCEHUNT_AI_BOT,
    EMAIL_WORKUA_REACT_DEVELOPER,
    EMAIL_UPWORK_AUTOMATION,
    EMAIL_SPAM_NEWSLETTER,
    EMAIL_FREELANCEHUNT_LOW_BUDGET,
]

RELEVANT_EMAIL_IDS = {"mock_fh_001", "mock_wu_002", "mock_uw_003"}
NOT_RELEVANT_EMAIL_IDS = {"mock_spam_004", "mock_fh_005"}
