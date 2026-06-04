# AGENTS — Gmail-based AI Job Notification System

## Архітектура агентів

```
Gmail Inbox
    │
    ▼
[gmail-integration-agent]
    │  читає нові листи
    │  фільтрує за sender/subject
    ▼
[ai-analyzer-agent]
    │  score 0–10
    │  reason, budget, platform, urgency
    ▼
[qa-tester] ← перевіряє score >= threshold
    │
    ▼
[telegram-agent]
    │  відправляє картку
    │  /reply_job <id>
    ▼
[reply-generator-agent]
    │  генерує відгук
    │  НЕ відправляє автоматично
    ▼
[final-verifier]
    │  користувач перевіряє
    │  копіює вручну
```

---

## Ролі агентів

### goal-executor
**Файл:** `GOAL.md` + `GOAL_PROGRESS.md`

Відповідальність:
- Читає `GOAL.md` на початку кожного циклу
- Оновлює `GOAL_PROGRESS.md` після кожного кроку
- Визначає чи ціль досягнута
- Зупиняється тільки коли є практичний доказ роботи

---

### planner
**Файл:** `GOAL_PROGRESS.md` → план дій

Відповідальність:
- Розбиває ціль на мінімальні безпечні кроки
- Не пише код поки план не погоджений
- Враховує існуючий код — не ломає старе

---

### backend-implementer
**Файли:** `gmail_agent/*.py`

Відповідальність:
- Реалізує модулі по одному
- Кожен модуль — окремий файл з чіткою відповідальністю
- Не додає зайвих залежностей

---

### gmail-integration-agent
**Файл:** `gmail_agent/gmail_provider.py`

Відповідальність:
- `GmailProvider` — абстрактний інтерфейс
- `MockGmailProvider` — для тестів без credentials
- `RealGmailProvider` — реальний Gmail OAuth2 API
- Повертає список `EmailMessage` об'єктів
- Запам'ятовує прочитані email IDs (через dedup)

Методи:
```python
async def get_new_emails() -> list[EmailMessage]
async def mark_as_processed(email_id: str) -> None
```

---

### ai-analyzer-agent
**Файл:** `gmail_agent/email_analyzer.py`

Відповідальність:
- Отримує `EmailMessage`
- Викликає OpenAI для аналізу
- Повертає `JobAnalysis`:
  - `score: float` (0–10)
  - `reason: str`
  - `platform: str`
  - `title: str`
  - `budget: str`
  - `url: str`
  - `urgency: str` (high/medium/low)
  - `is_relevant: bool`
  - `why_relevant: str`

---

### telegram-agent
**Файл:** `gmail_agent/telegram_notifier.py`

Відповідальність:
- Форматує `JobAnalysis` в Telegram-картку
- Відправляє картку з кнопками `/reply_job` і `/skip_job`
- НЕ відправляє відгук автоматично

Картка:
```
🔥 New Job Match

Платформа: ...
Назва: ...
Score: .../10
Бюджет: ...
Опис: ...
Чому підходить: ...
Посилання: ...

/reply_job <id>   /skip_job <id>
```

---

### reply-generator-agent
**Файл:** `gmail_agent/reply_generator.py`

Відповідальність:
- Отримує `JobAnalysis` по ID
- Генерує короткий впевнений відгук
- НЕ вигадує технології яких немає
- Показує draft користувачу для перевірки

---

### qa-tester
**Файли:** `gmail_agent/tests/*.py`

Відповідальність:
- `test_dedup.py` — тести дедуплікації
- `test_analyzer.py` — тести AI аналізатора
- `test_processor.py` — end-to-end pipeline тест
- Всі тести запускаються без реального Gmail і Telegram

Критерії pass:
- Mock email читається
- Score рахується коректно
- Дублікати не пропускаються
- Нерелевантні email відхиляються

---

### bug-fixer
Відповідальність:
- Аналізує логи при падінні тестів
- Знаходить root cause
- Мінімальний fix — не рефакторинг
- Після fix — повторно запускає тести

---

### final-verifier
Відповідальність:
- Перевіряє що старий бот не зламаний
- Перевіряє що нова Gmail-архітектура ізольована
- Підтверджує що `GMAIL_ENABLED=false` вимикає нову функцію
- Документує як запустити реальне тестування

---

## Правила взаємодії агентів

1. Кожен агент пише тільки свій модуль
2. Агенти не змінюють чужий код без погодження
3. Всі зміни в `GOAL_PROGRESS.md`
4. Тест падає → bug-fixer → тест повторно
5. Не вважати "готово" без proof of work
