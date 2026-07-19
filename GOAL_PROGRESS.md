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

### Railway deployment and production proof ✅

- Code commit: `3571967fd4c9fcf3548ca1de0e8675b97361d385` (`Escape dynamic Gmail content in Telegram HTML`), pushed to `main`.
- Railway deployment: `45bc3fc6-0eae-497e-892e-1daf8f5c680b`, status `SUCCESS`, repository `optidigitalagent/-`, branch `main`, Root Directory `/optidigital-agent`, Config File `/optidigital-agent/railway.json`.
- Build completed with Python 3.13.14 and Playwright Chromium/Headless Shell/ffmpeg; image build and push succeeded.
- Startup logs: one container start; bot started; Playwright Chromium binary OK; Gmail job registered at 60 minutes; APScheduler started; Telegram polling connected.
- Current deployment log audit: zero startup tracebacks, zero `invalid_grant`, zero Telegram polling conflicts, zero `can't parse entities`, and zero `Unsupported start tag`.
- Railway SSH imports on Python 3.13.14: `bot.handlers`, `gmail_agent.telegram_notifier`, and `gmail_agent.scheduler` all exit 0.
- Railway SSH suite: 57/57 Gmail tests pass inside the deployed image.
- Production `/status` equivalent: service is running, polling is connected, Gmail is enabled, and the 60-minute scheduler job is registered.
- Production `/gmail_test` + `/gmail_debug` equivalent (real Railway env, header-only): OAuth status OK; enabled=true; mock=false; interval=60; Inbox inspected=10; sender-domain matches=0; subject-keyword matches=0; job-alert matches=0. No bodies, full IDs, tokens, AI, dedup, or job cards were used.
- Production `/gmail_scan` equivalent used the real provider with temporary dedup/job-store and a bot that cannot send: fetched=8, duplicates=0, not_relevant=8, below_threshold=0, sent=0, errors=0, send_attempts=0. Production dedup was not cleared or mutated.
- Real Telegram server parse proof: a clearly-labelled synthetic Gmail HTML verification block containing `Freelancehunt <noreply@freelancehunt.com>`, subject markup, ampersands, and comparison operators was escaped with the shared helper and sent through the production Bot API. Result: HTTP 200, `ok=true`, message ID returned, no parse-entity error.
- A new real platform alert remains pending: the inspected Inbox window contained no sender/subject match, so no legitimate job card or `/reply_job` draft was generated during this verification.

---

## 2026-07-19 Production Gmail account identity verification

### Read-only account and token proof ✅

- The premise that production still used the previous Gmail account was rechecked before changing any secret.
- Railway production env proof via Gmail `users().getProfile(userId="me")`: connected account `tijgadymg@gmail.com`, messages total 613, threads total 584, OAuth refresh/status OK.
- Local `gmail_token_fh.json` proof: despite its legacy filename, the token belongs to `tijgadymg@gmail.com`, contains a refresh token, and refreshes successfully.
- Because both local and production identities already match the required account, no new OAuth flow was started and `GMAIL_TOKEN_JSON` was not replaced.
- No OAuth token, refresh token, client secret, credentials JSON, message ID, or email body was printed.

### Metadata-only mailbox proof ✅

- Gmail searches used `format="metadata"` with only `From`, `Subject`, `Date`, and labels; message bodies were not read and labels were not changed.
- `from:(freelancehunt.com)`: 28 total, 28 Inbox, 0 Archive, 0 Spam.
- `from:(freelancehunt.com) newer_than:90d`: 24 total, 24 Inbox, 0 Archive, 0 Spam.
- `freelancehunt newer_than:90d`: 27 total, 26 Inbox, 1 Archive/All Mail, 0 Spam.
- Other sender counts: Work.ua 52 Inbox; Robota.ua 3 Inbox; Upwork 0.
- The newest 50 Inbox messages contain 4 Freelancehunt messages at positions 16, 38, 46, and 48. This explains why a 10-message `/gmail_debug` window can report zero even though matching alerts exist.

### Safe `/gmail_account` implementation and QA ✅

- Added admin-only `/gmail_account`; the existing `admin_router` chat filter restricts it to `settings.admin_chat_id`.
- Added `RealGmailProvider.get_account_profile()`, which calls only Gmail profile and Inbox label metadata endpoints.
- The command shows only connected Gmail account, Inbox messages count, and OAuth status; errors expose only the exception type.
- Unit proof verifies that the profile and Inbox label endpoints are called and Gmail message list/get endpoints are not called.
- Production-env proof through the new code path: connected account `tijgadymg@gmail.com`, Inbox messages count 611, OAuth status OK.
- QA proof: `python -m unittest discover -s gmail_agent\\tests -v` -> 58/58 OK.
- Compile proof: `python -m py_compile gmail_agent\\gmail_provider.py bot\\handlers.py` -> OK.
- `git diff --check` -> clean apart from existing line-ending notices; credential/token files remain ignored.

### Railway deployment and production pipeline proof ✅

- Code commit `76209b87e2f2d48da8055c5849d4685e80c5c416` (`Add safe Gmail account identity command`) was pushed to `main`.
- Railway deployment `9943e8c3-7dde-4eed-8e0b-35c2662ab762` reached `SUCCESS` with Root Directory `/optidigital-agent`, Config File `/optidigital-agent/railway.json`, and start command `python bot/main.py`.
- Runtime proof: Playwright Chromium binary OK; bot started; scheduler started; Gmail job registered at 60 minutes; Telegram polling connected.
- Filtered startup log review found no traceback, `invalid_grant`, polling conflict, or Telegram HTML parse error.
- Isolated production-env pipeline used the real Gmail provider and OpenAI analyzer with temporary dedup/job-store and a non-sending bot: `fetched=8`, `duplicates=0`, `not_relevant=8`, `below_threshold=0`, `would_send=0`, `errors=0`, `send_attempts=0`.
- The isolated scan did not clear or mutate production dedup and did not send Telegram cards.
- Telegram Desktop already showed previous user-issued `/gmail_test`, `/gmail_debug`, and `/gmail_scan` results. No new command was sent through UI automation because user input was detected in that window and representational UI messages require action-time confirmation.

---

## 2026-07-19 Final Telegram job-card root-cause audit

### Accepted evidence-first plan ✅

- Read `GOAL.md`, `GOAL_PROGRESS.md`, and the user-supplied audit brief before taking action.
- The brief itself supplies the agreed plan: metadata-only Gmail audit, isolated AI audit, root-cause classification, Freelancehunt settings check, then evidence-driven fixes only.
- Existing user worktree deletions of debug PNG files remain untouched and outside this task's scope.
- No production dedup, Gmail labels, Telegram cards, prompt, score threshold, or platform settings have been changed at this stage.

---

## 2026-07-19 Freelancehunt digest production pipeline

### Stage 1 — read-only production Gmail audit ✅

- The production OAuth token is valid, has exactly the Gmail readonly scope, and belongs to the expected mailbox. The refresh was performed in memory; no token file, Gmail label, message state, dedup store, or job store was changed.
- A narrow Gmail search found exactly two target Freelancehunt digest emails. Only `getProfile`, `messages.list`, and `messages.get` with metadata/full read formats were used; no Gmail mutation endpoint was called.
- Both messages are HTML-only: root MIME `text/html`, one HTML part, no `text/plain`, no attachments.
- The two samples contain 7/6 anchors and 5/4 unique normalized destinations. After semantic path classification they contain 2/1 direct vacancy links, 1/1 category links, 2/2 unsubscribe links, and 2/2 platform/root links. Tracking query parameters decorate semantic links and must be removed only after path classification.
- Each vacancy is one nested table: the first row contains the direct vacancy title anchor plus metadata and an optional budget block; the second row contains the description. Three unique vacancy items were confirmed in total (2 + 1); one of the three contains an explicit currency budget.
- Images, linked pages, and tracking destinations were not fetched. No body, personal data, tracking token, OAuth secret, Gmail message ID, or cookie was printed or saved.
- Regression fixtures will be fully synthetic (`example.invalid` content plus Freelancehunt-shaped `/ua/job/{slug}/{id}.html` paths) and will preserve only the audited structure.
- Baseline proof before implementation: `python -m unittest discover -s gmail_agent\\tests -v` → 58/58 OK.

### Agreed implementation plan

1. Add deterministic email-type classification and synthetic digest fixtures/tests.
2. Preserve MIME structure and safely extract/clean plain text, HTML, and links.
3. Parse each Freelancehunt vacancy into a separate stable-key candidate (maximum 20 per digest).
4. Analyze every candidate separately while preserving the existing single-job scoring flow.
5. Persist child decisions, scan history, and reply-job data in PostgreSQL with injectable local/test fallback.
6. Add admin-only preview/backfill commands, a ten-card scan cap, retry-safe parent/child handling, and persistent `/gmail_history`.
7. Run the complete QA gate, deploy only targeted files, wait for Railway SUCCESS, then prove preview/backfill/dedup/restart behavior in production.

### Stages 2–4 — classification, MIME extraction, digest parser ✅

- RED proof before production changes: the focused suite failed with 5 expected errors (`email_classifier` and `digest_parser` missing; `EmailMessage` structured MIME fields missing).
- Added deterministic `EmailType` classification guarded by approved sender domains. Audited Freelancehunt subject variants are `job_digest`; Work.ua market/article mail remains `informational_newsletter`.
- `EmailMessage` remains backward-compatible and now carries decoded `text_body`, cleaned `html_body`, and safe HTTP(S) links. Recursive MIME parsing handles HTML-only and nested multipart messages, ignores attachments, removes script/style/hidden/tracking/footer noise, and never executes JavaScript or opens extracted links.
- Added deterministic `DigestJobCandidate` parsing for the audited nested-table layout. It extracts title, second-row description, optional budget, normalized vacancy URL, received time, and SHA-256 stable key; category/unsubscribe/root/assets are excluded and extraction is capped at 20.
- Fixtures contain only synthetic content and preserve the audited 7/6-anchor, 2/1-vacancy shapes.
- GREEN proof: `python -m unittest gmail_agent.tests.test_email_classifier gmail_agent.tests.test_gmail_mime_extraction gmail_agent.tests.test_digest_parser -v` → 12/12 OK.

### Stage 8 foundation — persistent repository and schema ✅

- Added non-destructive SQLAlchemy models for `gmail_processed_items`, `gmail_scan_runs` (including the required `relevant` counter), and `gmail_jobs`. Existing tables and data are untouched; the only explicit migration is additive `ADD COLUMN IF NOT EXISTS`.
- Added an async repository boundary with PostgreSQL and injectable in-memory implementations for processed decisions, job payload/status, scan history, and an atomic conditional job claim.
- Terminal job statuses cannot be reset to queued by an upsert. Two concurrent claims over the same queued job yield exactly one winner.
- Test/local imports no longer initialize production settings or the DB engine; ORM models are loaded only when the PostgreSQL repository is constructed.
- Restart simulation reopens a second in-memory repository over the same shared state and confirms processed items, job data, and scan history remain available.
- QA RED→GREEN: the first restart test failed because shared state was unsupported; the bug-fixer added the narrow `state=` seam. `python -m unittest gmail_agent.tests.test_storage -v` → 8/8 OK.

### Stages 5–9 — child processing, backfill, and persistent commands ✅

- `GmailJobProcessor` now classifies before AI. Freelancehunt digest children are parsed and analyzed one-by-one; informational Work.ua mail is deterministically rejected without AI; the legacy single-job flow remains covered.
- Child stable keys are the authoritative dedup boundary. Decisions `not_relevant`, `below_threshold`, `queued`, `send_failed`, `sending`, `sent`, and `skipped` are stored explicitly. Telegram failure never creates a processed/sent decision and is retried without repeating AI analysis.
- A scan attempts at most 10 cards. Additional qualifying jobs remain queued for a later scan. Digest parent success is recorded separately only after extraction/child persistence; parser failure leaves the parent retryable.
- Repository-backed production paths do not create or update local Gmail dedup/job JSON. Single jobs, informational rejects, digest parents, child decisions, reply data, and scan history use PostgreSQL; legacy JSON remains only for repository-less mock/local compatibility.
- Added side-effect-free `run_digest_preview(days)` and persistent/idempotent `run_digest_backfill(days)`. Preview does not send, mark parents, mutate dedup/repository, or create scan history. Repeated backfill reports child duplicates and sends nothing twice.
- Added admin-only `/gmail_digest_preview 1..30` and `/gmail_digest_backfill 1..30`; backfill reports the card cap and detailed counters. `GMAIL_DIGEST_ENABLED=false` prevents scheduler rollout and never falls through to whole-digest single-job AI.
- Manual and scheduler scans pass a PostgreSQL repository and persistent trigger (`manual`/`scheduler`). REAL mode fails closed if PostgreSQL cannot be constructed; repository-less fallback is limited to mock/local mode.
- `/gmail_history` reads the latest 20 PostgreSQL scan runs and distinguishes an unavailable DB from an empty history. `/reply_job` loads the persistent job by stable key; `/skip_job` updates status to `skipped` instead of deleting the row.
- Processor RED→GREEN proofs cover separate child AI, cross-digest URL dedup, parser failure, score threshold, retry, queue/cap, preview, repeated backfill, digest-disabled safety, repository single jobs, informational dedup, and no production JSON mutation. Focused processor/backfill regression: 19/19 OK.
- Persistent handler/HTML regression proof: 23/23 OK. Storage proof remains 8/8 OK.

### Stages 10–11 — final QA and failure-recovery hardening ✅

- Final review findings were converted to RED tests before fixes. The parser now accepts strict Freelancehunt `/ua/job/...`, `/project/...`, and `/ua/project/...` direct-item paths while rejecting category/lookalike paths and stripping tracking query/fragment data.
- `gmail_jobs.status_updated_at` is added through `ADD COLUMN IF NOT EXISTS`; a 15-minute sending lease makes interrupted Telegram claims recoverable. Retryable jobs are selected FIFO from queued, send-failed, or stale-sending rows.
- A persistent retry queue is drained without Gmail refetch or repeated AI analysis. The ten-card cap is shared across queued, digest, and single-job sends. Extra relevant jobs remain queued.
- Recognized digests never fall through to whole-email AI, including repository-less mode. `GMAIL_DIGEST_ENABLED=false` also blocks queued digest children while preserving the legacy single-job queue.
- Targeted backfill does not drain unrelated global jobs and processes only Freelancehunt digests returned by its requested date-window search.
- Independent final verifier result: PASS with no remaining findings. It confirmed side-effect-free preview, idempotent backfill, persistent PostgreSQL source of truth, non-destructive migrations, restart/lease behavior, legacy single-job compatibility, and isolation when `GMAIL_ENABLED=false`.
- Full QA proof: `python -m unittest discover -s gmail_agent\\tests -v` → 111/111 OK; `python -m compileall -q .` → OK; Gmail module import checks → OK; `git diff --check` → clean apart from line-ending notices.

### Stage 12 — Railway production proof ✅

- Targeted implementation commit `ec78f4f049c13811165cc1fcce00630e6c82f43c` was pushed to `main`; pre-deploy Railway deployment `7b7f2fb4-2d5e-48ec-8831-ab6d1fda5a9d` reached `SUCCESS` on Python 3.13.14. Startup completed, migrations ran before polling, and the Gmail scheduler registered at 60 minutes.
- Production account proof after deploy: `tijgadymg@gmail.com`, OAuth `OK`, Inbox count 611. No token, credential, Gmail message ID, or body was printed.
- Read-only `/gmail_digest_preview 7` equivalent found exactly two real Freelancehunt digests and extracted 2 + 1 individual jobs. Scores were 0.0, 2.0, and 2.0; no item met the unchanged 6.0 threshold. Preview returned zero errors and changed neither PostgreSQL nor dedup.
- First production backfill: emails=2, candidates=3, relevant=2, not_relevant=1, below_threshold=2, sent=0, duplicates=0, errors=0. No Telegram card was sent because no child met score 6.0.
- Immediate repeated backfill: emails=2, candidates=3, duplicates=3, sent=0, errors=0. It did not repeat AI analysis or Telegram delivery.
- `GMAIL_DIGEST_ENABLED=true` was set only after successful preview/backfill. The resulting restart deployment `c3d5929e-455a-4219-a1ec-d9b4a5fc9607` reached `SUCCESS` on the same code SHA.
- Post-restart PostgreSQL proof: all three tables exist; child decisions remain `not_relevant=1` and `below_threshold=2`; the two latest `gmail_scan_runs` preserve the first and duplicate backfill statistics. `gmail_jobs` is empty by design because no score-qualified child was queued or sent.
- Metadata-only Work.ua production check (50 recent messages) classified 2 as `informational_newsletter`; these are deterministically rejected before AI. No subject, body, or message ID was printed.
- Restart log scan: zero tracebacks, `invalid_grant`, migration errors, Telegram HTML parse errors, or high-confidence secret patterns. One transient Telegram polling conflict during deployment overlap was followed by a successful connection restoration.
- The temporary Railway SSH key created while diagnosing CLI SSH was removed from Railway and both local key files were deleted; it cannot be recovered. Production proof ultimately used Railway environment injection plus the public PostgreSQL endpoint held only in process memory.
