# GOAL PROGRESS — Gmail-based AI Job Notification Agent

## Статус: PHASE 1-4 PARTIAL ✅ | Real Gmail Verification Pending

Дата початку: 2026-06-04

---

## Що зроблено

### Фаза 1 — Аналіз та документація ✅

- [x] Проаналізовано існуючий проект (`optidigital-agent/`)
- [x] Підтверджено проблему: Playwright блокується Cloudflare на Freelancehunt
- [x] Написано `GOAL.md`, `AGENTS.md`, `GOAL_PROGRESS.md`
- [x] Стара архітектура НЕ зламана (парсери залишені)

### Фаза 2 — Gmail агент (ізольований модуль) ✅

| Файл | Статус | Призначення |
|------|--------|-------------|
| `gmail_agent/__init__.py` | ✅ | Модуль |
| `gmail_agent/gmail_provider.py` | ✅ | MockGmailProvider + RealGmailProvider (OAuth2) |
| `gmail_agent/dedup.py` | ✅ | Дедуплікація через JSON файл |
| `gmail_agent/email_analyzer.py` | ✅ | AI аналіз email (OpenAI, lazy import) |
| `gmail_agent/reply_generator.py` | ✅ | Генерація відгуків (OpenAI, lazy import) |
| `gmail_agent/telegram_notifier.py` | ✅ | Telegram картки |
| `gmail_agent/processor.py` | ✅ | Головний pipeline |
| `gmail_agent/scheduler.py` | ✅ | APScheduler hook |
| `gmail_agent/tests/mock_emails.py` | ✅ | 5 mock email fixtures |
| `gmail_agent/tests/test_dedup.py` | ✅ 6/6 | Тести дедуплікації |
| `gmail_agent/tests/test_analyzer.py` | ✅ 7/7 | Тести AI аналізатора |
| `gmail_agent/tests/test_processor.py` | ✅ 5/5 | Інтеграційні тести pipeline |

### Фаза 3 — Інтеграція в існуючий бот ✅

- [x] `bot/handlers.py` — додано `/reply_job <id>` та `/skip_job <id>`
- [x] `bot/main.py` — підключено `register_gmail_job()` в `on_startup()`
- [x] `config.py` — додано Gmail env vars (`GMAIL_ENABLED`, etc.)
- [x] `requirements.txt` — додано Google API бібліотеки
- [x] `.env.example` — оновлено з новими змінними

### Фаза 4 — Діагностика та підготовка до Real Gmail ✅ Partial

- [x] **Аудит RealGmailProvider** — env vars, файли, залежності, ризики задокументовані
- [x] `/gmail_test` — додано до `bot/handlers.py` (admin_router)
  - Показує GMAIL_ENABLED, GMAIL_USE_MOCK, GMAIL_MIN_SCORE
  - Перевіряє наявність credentials.json та token.json
  - Якщо real mode і token є → підключається до Gmail (без browser flow!), показує 5 листів + кількість job alerts
  - Safe mode: при відсутності файлів — інструкція, без падіння
- [x] `/gmail_scan` — додано до `bot/handlers.py` (admin_router)
  - При GMAIL_ENABLED=false → повідомлення без помилок
  - При GMAIL_ENABLED=true → запускає GmailJobProcessor, показує статистику
  - Відправляє картки в Telegram якщо знайдено підходящі листи
- [x] **Safe mode підтверджено**: GMAIL_ENABLED=false → жодних OAuth викликів, жодних падінь

### Фаза 4 — Реальна верифікація ⬜ Pending (потрібен credentials.json)

- [ ] Отримати `credentials.json` з Google Cloud Console
- [ ] Авторизуватися локально (браузер), отримати `gmail_token.json`
- [ ] Встановити `GMAIL_ENABLED=true`, `GMAIL_USE_MOCK=false`
- [ ] Запустити `/gmail_test` — перевірити підключення
- [ ] Отримати реальний job alert email від Freelancehunt/Work.ua
- [ ] Запустити `/gmail_scan` — підтвердити картку в Telegram
- [ ] Підтвердити `/reply_job` генерацію відгуку
- [ ] Підтвердити deduplication (повторний scan не надсилає дублікат)

---

## Тести — PROOF OF WORK

```
Ran 18 tests in 0.157s — OK

test_dedup.py         6/6  ✅
test_analyzer.py      7/7  ✅  
test_processor.py     5/5  ✅
```

### Що перевірено тестами:

1. ✅ Mock email читається системою (`test_relevant_email_sent_to_telegram`)
2. ✅ AI оцінює email — score + reason (`test_relevant_ai_email`)
3. ✅ Telegram отримує картку (`bot.send_message.assert_called_once()`)
4. ✅ Дублікати НЕ відправляються повторно (`test_duplicate_not_sent_twice`)
5. ✅ Спам/нерелевантні email ігноруються (`test_spam_email_not_sent`)
6. ✅ Email нижче порогу не відправляються (`test_below_threshold_not_sent`)
7. ✅ Порожній inbox — без помилок (`test_empty_inbox_no_errors`)
8. ✅ OpenAI помилка — graceful fallback (`test_openai_error_returns_default`)
9. ✅ Дедуплікація зберігається між запусками (`test_persistence_across_instances`)

---

## Що зламалось та виправлено

| Проблема | Root Cause | Фікс |
|----------|------------|------|
| `JSONDecodeError` при старті | `NamedTemporaryFile` створює пустий файл | `_load()` тепер перевіряє чи рядок не пустий |
| `ModuleNotFoundError: openai` | import на рівні модуля, пакет не встановлений | Lazy import через `TYPE_CHECKING` + import в функції |
| `ModuleNotFoundError: aiogram` | те саме | Замінено на `Any` type hints |
| `test_duplicate_not_sent_twice` FAIL | `MockGmailProvider` фільтрував за своїм `_processed` | Видалено фільтрацію з Mock — dedup відповідальність `EmailDedup` |

---

## Як запустити

### Mock режим (для тестування без Gmail)

```bash
cd optidigital-agent
# .env
GMAIL_ENABLED=true
GMAIL_USE_MOCK=true

python bot/main.py
```

### Реальний Gmail

```bash
# 1. Отримати credentials.json з Google Cloud Console
#    (Gmail API → OAuth2 → Desktop app)

# 2. .env
GMAIL_ENABLED=true
GMAIL_USE_MOCK=false
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=gmail_token.json
GMAIL_MIN_SCORE=6
GMAIL_CHECK_INTERVAL_MINUTES=30

# 3. Запустити — при першому запуску відкриється браузер для авторизації
python bot/main.py
```

### Запуск тестів

```bash
cd optidigital-agent
python -m unittest gmail_agent/tests/test_dedup.py gmail_agent/tests/test_analyzer.py gmail_agent/tests/test_processor.py -v
```

---

## Нові Telegram команди

| Команда | Дія |
|---------|-----|
| `/reply_job <email_id>` | Генерує відгук для job alert. НЕ відправляє автоматично |
| `/skip_job <email_id>` | Відмічає замовлення як пропущене |

---

## Що далі — Покроковий план реальної верифікації

### Крок 1 — Отримати credentials.json

1. Відкрий [Google Cloud Console](https://console.cloud.google.com)
2. Створи або обери проект
3. APIs & Services → Library → Gmail API → Enable
4. APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID
5. Application type: **Desktop app**
6. Download JSON → зберегти як `credentials.json` в папці `optidigital-agent/`

### Крок 2 — Перша авторизація (локально!)

```bash
# .env локально:
GMAIL_ENABLED=true
GMAIL_USE_MOCK=false
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=gmail_token.json

# Запусти бот — відкриється браузер Google
python bot/main.py
```
Після авторизації з'явиться `gmail_token.json`. Зупини бот.

### Крок 3 — Gmail test

Відправ `/gmail_test` в Telegram (як адмін).

Очікуваний результат:
```
GMAIL_ENABLED: true
GMAIL_USE_MOCK: false
credentials.json: ✅ знайдено
token.json: ✅ знайдено

✅ Gmail підключено!
📧 Останні листи в Inbox:
1. [subject]
   Від: [from]
   Дата: [date]
...
🎯 Потенційних job alerts (з 10 нових): N
```

### Крок 4 — Отримати тестовий job alert

1. Зайди на Freelancehunt → Налаштування → Сповіщення → Email
2. Включи сповіщення про нові проекти за твоїми категоріями
3. Дочекайся або знайди проект вручну → він надішле email

### Крок 5 — Gmail scan

Відправ `/gmail_scan` в Telegram.

Очікуваний результат:
```
✅ Gmail scan завершено
📬 Знайдено листів: 5
♻️ Дублікатів: 0
🚫 Нерелевантних: 3
⬇️ Нижче порогу: 1
📨 Відправлено в Telegram: 1
```

І в каналі з'явиться картка:
```
🔥 New Job Match
Платформа: Freelancehunt
...
/reply_job <id>   /skip_job <id>
```

### Крок 6 — Перевірка deduplication

Відправ `/gmail_scan` ще раз.

Очікуваний результат: `♻️ Дублікатів: 1` — картка НЕ надсилається повторно.

### Крок 7 — Перевірка /reply_job

Відправ `/reply_job <id>` з картки.

Очікуваний результат: AI-згенерований відгук у Telegram.

### Критерій успіху (DoD)

- [ ] REAL EMAIL → Gmail → AI → Telegram підтверджено на практиці
- [ ] Лог: `fetched=N sent=1 errors=0`
- [ ] Дублікат не надсилається повторно
- [ ] /reply_job генерує відгук
