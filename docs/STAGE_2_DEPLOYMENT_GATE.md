# Stage 2 Deployment Gate

Status: `READY_FOR_RAILWAY_DEPLOY`

This document contains public-safe evidence only. Exact mailbox addresses,
OAuth credentials, token JSON, Telegram identifiers, message IDs and message
content are not recorded in the repository.

## 1. Objective

Extend the existing Gmail/PostgreSQL/Telegram agent so every commercially
important Freelancehunt email is classified, persisted once and converted into
a complete owner-action card, with a normal detection target of at most two
minutes and no automatic platform action.

## 2. Commercial impact

The pipeline now turns project alerts, digests, private client messages,
project status changes, workspace/contract events and account/security notices
into actionable information. Private messages bypass project-score filtering;
project cards include the full available specification, commercial analysis,
one truthful evidence item, price/time guidance and a ready draft. The adult
owner still personally decides and performs every bid, reply, contract and
payment action.

## 3. Production baseline

- Git production branch: `main`
- Production HEAD audited before implementation:
  `dd66513c0ba8a457c57af6feedf456b9a9cbf661`
- Railway-linked branch: `main`
- Railway project: `optidigital-agent`
- Railway service: `optidigital-agent`
- Railway environment: `production`
- Deployed source root: `/optidigital-agent`
- Railway config: `/optidigital-agent/railway.json`
- No production branch, deployment or variable was changed.

## 4. Feature branch

- Branch: `feature/freelancehunt-gmail-telegram-v1`
- Base: `setup/project-brain-v1`
- Base HEAD: `90b083593a8229e2c5e5f585006701b57915c2e6`
- First complete implementation commit: `341e200`
- Exact final validation HEAD is reported by the pull request and final Codex
  deployment-gate response.

## 5. Draft pull request

- Draft PR: <https://github.com/optidigitalagent/-/pull/2>
- Base: `setup/project-brain-v1`
- No merge performed.

## 6. Changed repository files

Production implementation:

- `optidigital-agent/.env.example`
- `optidigital-agent/README.md`
- `optidigital-agent/ai/scorer.py`
- `optidigital-agent/ai/writer.py`
- `optidigital-agent/bot/handlers.py`
- `optidigital-agent/bot/main.py`
- `optidigital-agent/config.py`
- `optidigital-agent/db/models.py`
- `optidigital-agent/gmail_agent/digest_parser.py`
- `optidigital-agent/gmail_agent/email_analyzer.py`
- `optidigital-agent/gmail_agent/email_classifier.py`
- `optidigital-agent/gmail_agent/gmail_provider.py`
- `optidigital-agent/gmail_agent/oauth_local.py`
- `optidigital-agent/gmail_agent/processor.py`
- `optidigital-agent/gmail_agent/reply_generator.py`
- `optidigital-agent/gmail_agent/scheduler.py`
- `optidigital-agent/gmail_agent/security.py`
- `optidigital-agent/gmail_agent/storage.py`
- `optidigital-agent/gmail_agent/telegram_notifier.py`
- `optidigital-agent/gmail_agent/tests/test_gmail_account.py`
- `optidigital-agent/gmail_agent/tests/test_stage2_revenue_flow.py`
- `optidigital-agent/scheduler.py`

Project state and evidence:

- `.codex/project_brain/DECISIONS.md`
- `.codex/project_brain/GOAL_PROGRESS.md`
- `.codex/project_brain/NEXT_ACTION.md`
- `GOAL_PROGRESS.md`
- `docs/STAGE_2_DEPLOYMENT_GATE.md`

## 7. Database migration

The existing startup migration mechanism is retained. Stage 2 adds only
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements. No table or row is
dropped, deleted or rewritten.

New `gmail_jobs` fields cover event type, full description, completeness,
language, category, skills, deadline, bid count, client name/profile/context,
project/thread IDs, service lane, executability, fit/win/scope/effort signals,
delivery and payment risks, CASH/REPUTATION/STRATEGIC mode, price, timeline,
selected evidence, analysis evidence, saved proposal, context flag, next
action, masked mailbox alias, received timestamp and security-redaction flag.

New `gmail_scan_runs` fields store per-event counts, masked mailbox alias and
maximum detection latency. Existing rows receive compatible defaults.

## 8. Tests and exact results

- Pre-change baseline: 122 tests; 120 passed and 2 failed because historical
  mock digest timestamps were tied to wall-clock time.
- The mock harness was made deterministic without weakening real Gmail
  lookback behavior.
- Stage 2 focused suite before final OAuth test: 17/17 passed.
- OAuth identity tests, including mismatch/no-token and forced account chooser:
  3/3 passed.
- Final full suite: 140/140 passed.
- Python compile check for `gmail_agent`, `bot`, `ai`, `db`, `config.py` and
  `scheduler.py`: passed.
- `git diff --check`: passed.

Coverage includes Ukrainian/Russian/English/Polish subjects, multi-project
digest, single project, private message, project status, account/security
redaction, repeat scan, restart dedup, additive migration, full-description
proposal generation, active-brand check, Telegram HTML safety, Telegram size
limits and wrong-mailbox fail closed.

## 9. OAuth identity check

- Scope: `https://www.googleapis.com/auth/gmail.readonly`
- Verified with Gmail `users.getProfile(userId="me")` before token persistence.
- Verified mailbox alias: `ur***@gmail.com`
- Two mismatched attempts failed closed and wrote no token.
- The verified token exists only in an ignored local path; it is not committed
  or printed.

## 10. Real-mail dry run

Historical read-only lookback was used because a fresh project digest is not
required for this gate.

- OAuth identity verified: yes
- Messages returned by the narrow platform-sender query: 8
- `CLIENT_PRIVATE_MESSAGE`: 4
- `MARKETING`: 1
- `UNKNOWN`: 3
- Other event types in this mailbox sample: 0
- One existing private-message email was represented only by a sanitized
  surrogate; no subject, sender, Gmail ID, URL or body was output.
- Sanitized rendering: 1 part, maximum length 772 characters
- Gmail label changes: 0
- Archive/delete/send operations: 0
- Telegram messages during dry run: 0

## 11. Controlled Telegram test

- Explicit `[TEST]` marker: yes
- Synthetic event: `CLIENT_PRIVATE_MESSAGE`
- Real client/project data: none
- Logical cards: 1
- Telegram `sendMessage` calls: 1
- Message length: 709 characters
- Telegram API accepted the message: yes
- Freelancehunt messages or bids: 0

## 12. Sanitized project card

```text
🔥 New Job Match 🔴
Event: PROJECT_SINGLE
Received: [UTC timestamp]
Platform: Freelancehunt
Title: [SANITIZED] CRM and Telegram integration
Clean URL: [SANITIZED FREELANCEHUNT PROJECT URL]
Full specification: FULL — integrate CRM events, Telegram notifications,
PostgreSQL audit history and acceptance tests.
Client language: uk
Budget: 20,000 UAH
Deadline: 14 days
Category: Web programming
Bids: 4
Client: [PUBLIC DATA REDACTED]
Service lane: CRM and internal systems
Executable: yes
Fit: 8.2/10
Win signal: medium — clear fit with existing competition
Scope clarity: high
Effort: 30–40 hours
Delivery risk: CRM API access must be confirmed
Client/payment risk: use one funded milestone
Mode: CASH
Recommended price: 20,000 UAH as one milestone
Realistic timeline: 14 calendar days
Evidence: Gmail Job Agent — Gmail, Telegram, Railway, PostgreSQL
Proposal: [SANITIZED UKRAINIAN COPY-PASTE DRAFT]
Next owner action: open the project and personally submit the reviewed draft.
```

## 13. Sanitized private-message card

```text
🔴 HIGH PRIORITY — Private message
Event: CLIENT_PRIVATE_MESSAGE
Received: [UTC timestamp]
Sender: [REDACTED]
Context: delivery-date question
Language: en
NEEDS_CONTEXT
Full safe text: Can you confirm the delivery date?
Ready reply: I can confirm the scoped delivery date after reviewing the full
project thread.
Next owner action: open the Freelancehunt thread, verify prior context and
personally send the reviewed reply.
```

## 14. Railway variables (placeholders only)

Variables to add or change after explicit authorization:

```dotenv
GMAIL_EXPECTED_ACCOUNT=<EXACT_APPROVED_ADULT_OPERATIONAL_GMAIL>
GMAIL_TOKEN_JSON=<VERIFIED_GMAIL_READONLY_TOKEN_JSON>
GMAIL_CHECK_INTERVAL_MINUTES=1
GMAIL_LOOKBACK_DAYS=7
```

Existing variables to retain or verify:

```dotenv
DATABASE_URL=<RAILWAY_POSTGRES_REFERENCE>
GMAIL_CREDENTIALS_JSON=<EXISTING_GOOGLE_OAUTH_CLIENT_JSON>
GMAIL_DIGEST_ENABLED=true
GMAIL_ENABLED=true
GMAIL_MIN_SCORE=6
GMAIL_USE_MOCK=false
OPENAI_API_KEY=<EXISTING_SECRET>
PLAYWRIGHT_BROWSERS_PATH=<EXISTING_PATH>
TELEGRAM_CHAT_ID=<EXISTING_ADMIN_TEST_CHAT_ID>
TELEGRAM_TOKEN=<EXISTING_BOT_TOKEN>
RAILWAY_ENVIRONMENT=<RAILWAY_INJECTED>
RAILWAY_ENVIRONMENT_ID=<RAILWAY_INJECTED>
RAILWAY_ENVIRONMENT_NAME=<RAILWAY_INJECTED>
RAILWAY_PRIVATE_DOMAIN=<RAILWAY_INJECTED>
RAILWAY_PROJECT_ID=<RAILWAY_INJECTED>
RAILWAY_PROJECT_NAME=<RAILWAY_INJECTED>
RAILWAY_SERVICE_ID=<RAILWAY_INJECTED>
RAILWAY_SERVICE_NAME=<RAILWAY_INJECTED>
```

No Railway variable was changed during local validation.

## 15. Expected latency

The scheduler runs every 60 seconds with `max_instances=1` and `coalesce=true`.
The expected normal detection time is the next poll (0–60 seconds) plus Gmail,
AI and Telegram processing. For ordinary low-volume mail this is expected to
remain within 120 seconds. Backlog, upstream rate limits or outages are
reported through scan telemetry and retry state rather than silently deduped.

## 16. Rollback plan

1. Do not merge the feature branch if deployment validation fails.
2. Restore the prior Railway Gmail token and interval values from the platform
   secret history, then redeploy production HEAD
   `dd66513c0ba8a457c57af6feedf456b9a9cbf661`.
3. Set `GMAIL_ENABLED=false` for an immediate ingestion stop if needed.
4. Additive database columns may remain safely; rollback requires no data
   deletion.

## 17. Unresolved risks

- Production has not been deployed or tested with the new variables.
- The additive migration has unit/schema coverage but has not yet executed on
  the live production database.
- No fresh project/digest email existed in the adult mailbox sample; project
  paths were validated with deterministic fixtures.
- Three historical platform emails classified as `UNKNOWN`; telemetry should
  be reviewed after deployment before adding patterns.
- The repository is still public, so exact mailbox values and token material
  must remain exclusively in Railway secrets and ignored local files.
- Upstream Gmail, model and Telegram latency can temporarily exceed the normal
  two-minute target; retry and durable dedup mitigate loss, not outage delay.

## 18. Exactly one next action

Reply `AUTHORIZE_RAILWAY_DEPLOY` to authorize the prepared Railway variable
update and deployment workflow.
