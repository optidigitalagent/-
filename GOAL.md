# GOAL — Gmail-based AI Job Notification Agent

## Мета

Побудувати Gmail-based AI job notification agent, який:

1. Отримує job alerts з Gmail (від Freelancehunt, Work.ua, Robota.ua, Upwork)
2. Аналізує їх за допомогою AI (score 0–10, причина, бюджет, платформа)
3. Відправляє підходящі вакансії в Telegram з карточкою
4. За командою `/reply_job <id>` генерує готовий відгук для перегляду
5. НЕ відправляє відгук автоматично — тільки показує користувачу

## Чому Gmail замість парсингу

Playwright парсинг заблокований Cloudflare на Freelancehunt.
Email-сповіщення від платформ — офіційний, стабільний, безкоштовний канал.

## Джерела email alerts

- Freelancehunt (freelancehunt.com)
- Work.ua (work.ua)
- Robota.ua (robota.ua)
- Upwork (upwork.com)

## Telegram-карточка

```
🔥 New Job Match

Платформа: Freelancehunt
Назва: Розробка Telegram-бота
Score: 8.5/10
Бюджет: 5000–10000 UAH
Опис: ...
Чому підходить: AI/bot проект, гарний бюджет
Посилання: https://...

/reply_job 42   /skip_job 42
```

## Reply flow

1. Користувач: `/reply_job 42`
2. AI генерує короткий, впевнений відгук під конкретне ТЗ
3. Показує користувачу для перевірки
4. Користувач копіює і відправляє вручну

## Критерії завершення (Definition of Done)

- [ ] Mock email читається системою
- [ ] AI оцінює email (score + reason)
- [ ] Telegram отримує карточку
- [ ] `/reply_job` генерує відгук
- [ ] Дублікати не відправляються повторно
- [ ] Нерелевантні email ігноруються
- [ ] Реальний Gmail API підключається через env vars
- [ ] Старий Telegram бот продовжує працювати

## Env vars для нового агента

```
GMAIL_ENABLED=false              # true — включити Gmail агент
GMAIL_USE_MOCK=true              # true — mock провайдер (для тестів)
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=gmail_token.json
GMAIL_MIN_SCORE=6                # мінімальний score для Telegram
GMAIL_CHECK_INTERVAL_MINUTES=30  # інтервал перевірки Gmail
```
