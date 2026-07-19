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

---

## 2026-07-09 Gmail auto-scan incident

- Symptom: Telegram reported `Gmail Auto Scan errors` with `fetched=0 sent=0 errors=1` every hour.
- Reproduced locally with the real Gmail provider: `RefreshError invalid_grant`.
- Root cause: the Gmail OAuth refresh token is no longer accepted by Google. The local `gmail_token.json` access token expired on 2026-06-04, and refresh now fails.
- Code fix: `RealGmailProvider` now converts `invalid_grant` into clear reauthorization instructions.
- Code fix: `ProcessorStats` now carries `error_details`.
- Code fix: auto scan and `/gmail_scan` now show error details instead of only `errors=1`.
- Code fix: Gmail scheduler now reads config from `config.settings`, keeping `.env` and Railway env parsing consistent.
- Proof: `python -m unittest gmail_agent.tests.test_dedup gmail_agent.tests.test_analyzer gmail_agent.tests.test_processor gmail_agent.tests.test_diagnostics -v` -> 34 tests OK.
- Proof: `python -m py_compile gmail_agent\gmail_provider.py gmail_agent\processor.py gmail_agent\scheduler.py bot\handlers.py` -> OK.
- Remaining manual action: run OAuth login and update Railway `GMAIL_TOKEN_JSON` with the new `gmail_token.json` content.

---

## 2026-07-11 Codex migration hardening

- Verified local real Gmail API path with `gmail_token.json`: provider connected successfully and returned `fetched_job_alerts=0` from the checked inbox window, with no OAuth/API error.
- Code fix: `send_job_card()` now returns success/failure instead of silently swallowing Telegram errors.
- Code fix: `GmailJobProcessor` no longer marks a high-score relevant email as processed until the Telegram card is actually sent. If Telegram is down, the email remains retryable on the next scan.
- Code fix: Gmail job analyses are persisted in `gmail_agent/gmail_jobs.json` via `gmail_agent/job_store.py`, so `/reply_job <email_id>` can recover after a normal process restart instead of relying only on in-memory `_gmail_job_store`.
- Code fix: `gmail_jobs.json` is ignored by git as runtime state.
- Test coverage added: Telegram send failure is not deduped, and persistent job store save/get/delete behavior is covered.
- Proof: `python -m unittest gmail_agent.tests.test_dedup gmail_agent.tests.test_analyzer gmail_agent.tests.test_processor gmail_agent.tests.test_diagnostics gmail_agent.tests.test_job_store -v` -> 37 tests OK.
- Proof: `python -m py_compile gmail_agent\gmail_provider.py gmail_agent\processor.py gmail_agent\scheduler.py gmail_agent\telegram_notifier.py gmail_agent\job_store.py bot\handlers.py gmail_agent\oauth_local.py bot\main.py config.py` -> OK.

---

## 2026-07-19 Gmail prefilter audit

- Read-only audit completed before code changes.
- Root cause of `Inbox: 10` / `Potential job alerts: 0`: `RealGmailProvider.get_new_emails()` downloads the Inbox window but returns only messages for which parsing succeeds and `_is_job_alert()` matches a configured sender substring or subject keyword.
- Current sender filtering recognizes only nine literal address substrings. A Freelancehunt display name works when it wraps one of those addresses, but alternate local parts and subdomains can be rejected before AI analysis.
- Current subject fallback recognizes 14 literal substrings and can miss wording variants.
- Safety finding: the existing `/gmail_debug` runs after provider filtering and invokes AI with message bodies, so it does not meet the requested header-only dry-run contract.
- Next safe step: parse `From` with `email.utils.parseaddr()`, match approved domains and subdomains, expose shared match diagnostics, and make `/gmail_debug` read only sender/subject/date metadata without updating dedup or sending Telegram cards.

## 2026-07-19 Gmail prefilter hardening

- `From` is now decoded and parsed with `email.utils.parseaddr()`; matching uses approved sender domains and their subdomains: `freelancehunt.com`, `work.ua`, `robota.ua`, and `upwork.com`.
- Platform detection is shared with the prefilter and reports Freelancehunt, Work.ua, Robota.ua, Upwork, or Unknown.
- Subject keywords remain a fallback; Ukrainian `проєкт/проєкти` variants were added. A personal Gmail subject containing only `робота` is rejected.
- `RealGmailProvider.get_new_emails()` now fetches header metadata first and downloads a full body only after the platform/job-subject prefilter passes.
- Provider logs the requested zero-result statistics: Inbox inspected, sender-domain matches, subject-keyword matches, and returned alerts.
- `/gmail_debug` now inspects at most 10 recent messages using only `From`, `Subject`, and `Date`. It does not expose message IDs or bodies and does not invoke OpenAI, dedup mutation, or Telegram job-card delivery.
- `/gmail_test` now uses the same domain/subject matching logic and reports sender and subject match counts.
- Tests added in `gmail_agent/tests/test_gmail_prefilter.py` for all required platform, rejection, dry-run, privacy, and metadata-only cases.
- Proof: `python -m unittest discover -s gmail_agent\tests -v` -> 45 tests OK.
- Proof: `python -m py_compile gmail_agent\gmail_provider.py bot\handlers.py` -> OK.
- Real header-only Gmail proof: Inbox inspected 10; matched sender domain 0; matched subject keyword 0; returned job alerts 0; no OAuth/API error.
- Production status: code path is verified, but real Freelancehunt → AI → Telegram end-to-end proof is still pending because no real platform alert was present in the inspected Inbox window.

---

## 2026-07-19 Railway production recovery

- Git audit: local `main`, `origin/main`, and GitHub `main` all point to `cf1acbf07869d6625c613943be7d1ac8cc7b7ed6`; divergence is `0/0`.
- Existing dirty-worktree items were identified and left untouched: deleted debug PNG files and an untracked root `credentials.json`.
- Railway project/environment/service: `optidigital-agent` / `production` / `optidigital-agent`.
- Failed deployment: `3fd6aa93-e7fa-497c-8e54-c8cd6c430d2e`, commit `cf1acbf07869d6625c613943be7d1ac8cc7b7ed6`, status `FAILED`.
- Root cause: Railway stored Root Directory as ` /optidigital-agent` with a leading space. The failed deployment therefore had an empty file manifest, no detected `railway.json`, null build/start commands, and stopped immediately after build scheduling.
- Railway service-instance audit also found the Config File setting empty. Correct values are Root Directory `/optidigital-agent` and Config File `/optidigital-agent/railway.json`.
- Local proof before deployment: 45/45 Gmail tests passed; all 37 Python files compiled; key Gmail modules imported successfully.
- Local entrypoint import is blocked only because the host Python environment has not installed the repository requirements (`aiogram` is the first missing package); this is not a repository regression.

### Production proof after Railway settings correction

- Current deployment `8d53e91e-afeb-4b17-ba60-6d286d79db48` is `SUCCESS` on commit `cf1acbf07869d6625c613943be7d1ac8cc7b7ed6`.
- Build proof: Railpack installed Playwright Chromium, Chromium Headless Shell, and ffmpeg; the image built and pushed successfully.
- Startup proof: Python 3.13.14; config, `bot.handlers`, `gmail_agent.gmail_provider`, and `gmail_agent.scheduler` import successfully in the running container.
- Runtime proof: Playwright 1.49.0 Chromium binary OK; bot started; APScheduler started; `check_gmail_jobs` registered at 60 minutes; Telegram polling connected.
- A single Telegram polling overlap conflict occurred during deployment handover and recovered 11 seconds later. There is one container start, no container stop, no startup traceback, and no `invalid_grant` in current deployment logs.
- Production header-only Gmail proof: enabled=true, mock=false, interval=60; Inbox inspected 10; sender-domain matches 0; subject-keyword matches 0; job-alert matches 0; OAuth/API call succeeded.
- Production Gmail pipeline dry-run with temporary dedup/job-store and a non-sending bot: fetched=8, duplicates=0, not_relevant=8, below_threshold=0, sent=0, errors=0.
- Local QA: 45/45 Gmail tests passed and compileall passed. Full local dependency install was blocked by host disk exhaustion while pip built pinned lxml for Python 3.14; the Railway Python 3.13 image has all runtime dependencies and imports successfully.
- Root `.gitignore` now excludes `credentials.json` and `gmail_token*.json`; no credential/token file is staged. Two pre-existing parser cookie JSON files were removed from the Git index with `git rm --cached` while preserving the local files.
- Real platform-alert end-to-end proof remains pending because no matching real platform alert was present in the latest inspected Inbox window.

### Final latest-main deployment

- Pushed commit: `703399cb80700be914274cdebf54701e33f25031` (`Protect credentials after Railway recovery`).
- Railway deployment: `5bd8ee6d-8011-4a0b-ba48-f603f43fb2f7`, status `SUCCESS`, Root Directory `/optidigital-agent`, Config File `/optidigital-agent/railway.json`.
- Latest deployment startup: one container start, zero stops, zero tracebacks, zero `invalid_grant`, zero Telegram polling conflicts.
- Production module checks on the latest deployment: Python 3.13.14; config, handlers, Gmail provider, and Gmail scheduler all exit 0.
- Latest production Gmail checks: OAuth diagnostic status `ok`; enabled=true; mock=false; interval=60; header-only Inbox inspected=10, sender-domain matches=0, subject-keyword matches=0, potential alerts=0.
- Latest isolated production pipeline scan: fetched=8, duplicates=0, not_relevant=8, below_threshold=0, sent=0, errors=0. Temporary dedup/job-store and a non-sending bot were used, so this verification did not mutate production dedup or send job cards.

---

## 2026-07-19 Telegram HTML rendering hardening

### Context and read-only audit ✅

- Goal-driver plan accepted from the user-provided instruction file; no source code was changed before completing the audit.
- Baseline: commit `052dd3c99f68a133904baaed6634a396d5e9784e`; existing Gmail suite passes 45/45.
- Confirmed root cause: `bot/main.py` enables global Telegram HTML parse mode, while `/gmail_scan` inserts the raw Gmail sender into `<code>`. `Freelancehunt <noreply@freelancehunt.com>` is therefore parsed as an unsupported Telegram HTML tag.
- Unsafe Gmail-related dynamic HTML paths found in `/gmail_scan`, `/gmail_test`, `/reply_job`, `/skip_job`, the Gmail job card, Gmail scheduler error alerts, and exception-derived `/status` output.
- `/gmail_debug` already escapes displayed header values and preserves the required header-only/no-AI/no-dedup/no-card privacy contract; `/gmail_history` contains only locally-created timestamps and numeric counters.
- Existing user worktree deletions of debug PNG files were identified and left untouched.

### Agreed implementation plan

1. Add a failing regression test that reproduces the raw sender parse bug without calling Telegram.
2. Add a small shared `bot/html_utils.py` boundary for value escaping and validated HTTP(S) URLs.
3. Escape all external Gmail/platform/AI/user/exception values in the audited Gmail Telegram outputs while preserving static `<b>`, `<code>`, and `<a>` markup.
4. Isolate post-processing diagnostic send failures from the already-completed Gmail processor result without changing scan statistics, dedup, filtering, scoring, or scheduling.
5. Run the full suite, compile/import checks, secret/diff audit, deploy latest `main`, and verify production.

### Red regression proof ✅

- Added an isolated regression test that loads the real `cmd_gmail_scan` function via AST and uses mocks only; no Telegram, Gmail, OpenAI, OAuth, or credential access occurs.
- Pre-fix command: `python -m unittest gmail_agent.tests.test_telegram_html.TestGmailScanHtmlRegression.test_rejected_sender_with_angle_brackets_is_escaped -v`.
- Expected failure reproduced: the captured diagnostic output contains raw `<noreply@freelancehunt.com>` and does not contain `&lt;noreply@freelancehunt.com&gt;`.

### Safe HTML implementation and targeted QA ✅

- Added `bot/html_utils.py` with `escape_html()` (`None` safe; `html.escape(..., quote=True)`) and `safe_http_url()` (only well-formed HTTP(S) URLs with a hostname).
- Escaped audited dynamic fields in `/gmail_scan`, `/gmail_test`, `/reply_job`, `/skip_job`, Gmail job cards, scheduler error alerts, and exception-derived `/status` output.
- Removed the full Gmail message ID from `/gmail_test` output; Gmail/OAuth diagnostics and connection logic were not changed.
- Invalid job-card URLs no longer create `<a href>` and show `Посилання відсутнє`; valid URL attributes are escaped after validation.
- `/gmail_scan` now treats processor execution separately from diagnostic rendering/sending. A rejected/below-score/passed block send failure is logged and cannot change the already-computed stats, rerun email processing, or present the scan as a processor failure.
- Gmail filtering, AI prompt/model/scoring, dedup, `mark_processed`, scheduler interval, OAuth, parser code, and database schema were not changed.
- Added 12 focused regression tests in `gmail_agent/tests/test_telegram_html.py`; targeted suite passes 12/12.

### Full local QA and final-verifier review ✅

- Independent final-verifier review found and fixed malformed URL edge cases: nonnumeric/out-of-range/multiple ports and invalid host labels are now rejected before an `<a href>` is created.
- Job-card QA now verifies every dynamic field, allowed tag/attribute set, balanced nesting, valid HTTPS links, and invalid-URL fallback. All 13 mandatory HTML/privacy/regression cases have explicit proof.
- `python -m unittest discover -s gmail_agent\tests -v` → 57/57 OK (45 existing + 12 HTML regressions).
- `python -m compileall .` and `python -m compileall bot gmail_agent` → OK.
- Local imports: `gmail_agent.telegram_notifier` and `gmail_agent.scheduler` → OK. `bot.handlers` remains blocked only because the host Python 3.14 environment does not have the repository's pinned `aiogram` dependency installed; the same import must be repeated in the dependency-complete Railway Python 3.13 runtime.
- `git diff --check` is clean. Credential/token files remain ignored, and the pre-existing debug PNG deletions remain outside the intended commit scope.
- The root-level `test_parsers.py` is a live external parser smoke script (it executes network/browser parsing at import), not an isolated unit suite; it was not run because parser behavior is explicitly out of scope and unchanged.
