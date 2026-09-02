# Stage 2 — Gmail → Railway → Telegram Revenue Flow

## Objective

Turn every actionable Freelancehunt email received by the genuine adult-owned operational mailbox into a fast, deduplicated Telegram action card with a tailored proposal draft, without performing any platform action automatically.

## Entry state

- Adult-owned profile: `https://freelancehunt.com/freelancer/AntonovDigital.html`
- Commercial profile core: complete
- Adult-owned phone: confirmed
- Дія.Підпис verification: reported completed by the user
- Operational Gmail connection to ChatGPT: confirmed
- Fresh support/private-message emails from Freelancehunt: visible in the mailbox
- Fresh project digest on the new adult mailbox: not yet observed
- Portfolio cards: prepared but deferred where evidence/media is incomplete

The minor-owned account remains excluded from every operational and ingestion path.

## Existing implementation baseline

The implementation under `optidigital-agent/` already includes:

- Gmail OAuth read-only provider
- Gmail email parsing and sanitization
- deterministic email classification
- Freelancehunt digest parsing
- AI job scoring
- PostgreSQL persistence and deduplication
- Telegram notification cards
- retry queue
- `/reply_job` and `/skip_job`
- Railway-oriented environment configuration

Do not rewrite the system from scratch.

## Known gaps that must be fixed

1. Gmail is disabled by default and mock mode is enabled by default.
2. The configured polling interval is too slow for competitive freelance work.
3. The current classifier does not explicitly model Freelancehunt private-message email patterns in Ukrainian, Polish, Russian and English.
4. The current Telegram card is too thin for immediate decision-making.
5. Stored Gmail jobs do not preserve the full available description and other commercial fields required for a strong proposal.
6. `/reply_job` currently generates from analysis reason plus relevance text instead of the full task description.
7. AI prompts and some Telegram/reporting text still use the old `OptiDigital` brand.
8. Current scoring deprioritizes entire service lanes that Antonov Digital intends to test and does not estimate delivery effort, strategic value or expected margin.
9. The pipeline needs a clear distinction between project opportunities, client/private messages, account/security notices, marketing and non-actionable newsletters.
10. The production mailbox identity must be verified before deployment without logging token material.

## Required event types

Add explicit types at minimum:

- `PROJECT_SINGLE`
- `PROJECT_DIGEST`
- `CLIENT_PRIVATE_MESSAGE`
- `PROJECT_STATUS_EVENT`
- `WORKSPACE_OR_CONTRACT_EVENT`
- `ACCOUNT_OR_SECURITY_EVENT`
- `MARKETING`
- `UNKNOWN`

Support subject patterns in Ukrainian, Polish, Russian and English. Classify from trusted sender domain plus subject/body evidence. Do not treat every Freelancehunt email as a project.

## Polling and reliability target

Use the smallest robust implementation that meets:

- target detection latency: at most 2 minutes under normal operation
- recommended initial poll interval: 60 seconds
- one active scan per worker
- coalescing enabled
- durable deduplication in PostgreSQL
- retry after transient Gmail, OpenAI, database or Telegram failures
- no duplicate Telegram cards after restart or overlapping scans
- no Gmail label mutation required
- OAuth scope remains read-only

If a Gmail history-based cursor can be added safely and quickly, use it. Otherwise use a narrow trusted-sender query plus durable message-ID deduplication. Do not delay launch for unnecessary infrastructure.

## Mailbox and secret handling

The exact adult-owned mailbox address, OAuth client data and refresh token are private runtime values.

- Generate OAuth authorization locally with the adult owner.
- Use Gmail read-only scope.
- Confirm the OAuth profile address equals the selected adult-owned operational mailbox.
- Store the resulting token JSON only in local ignored files and Railway secrets.
- Never commit credentials, token JSON, cookies, OTPs or recovery data.
- Reject startup when production mode points to the wrong Gmail identity.

## Opportunity enrichment

For each project email:

1. Extract every job from the email.
2. Preserve the full description available in the email.
3. Resolve the clean project URL and stable project identifier.
4. When a permitted read-only Freelancehunt API/public endpoint is already available, enrich the project with the full current public task data.
5. Never use write endpoints, browser bidding or message submission.
6. When enrichment fails, continue with email data and mark `description_completeness=partial`.

Capture when available:

- title
- full description
- source email ID
- platform project ID
- project URL
- language
- budget and currency
- deadline
- category and skills
- bid/competition count
- client name/profile URL
- client history signals available publicly
- received time
- source event type

## Commercial analysis

Replace prestige-based filtering with revenue-oriented analysis across all supported service lanes.

Produce:

- executable: yes/no/uncertain
- service lane
- fit score
- win-probability signal
- scope clarity
- estimated hours/range
- delivery risk
- client/payment risk
- strategic/reputation value
- recommended project or milestone price
- realistic delivery time
- best matching evidence or clearly labelled demo
- one key clarification only when required
- one selected proposal draft

No fixed minimum budget. Low-price projects may qualify for cash, reputation or strategic reasons when scope is controlled.

## Proposal requirements

- Use brand `Antonov Digital`, never `OptiDigital`.
- Match the client's language: Ukrainian, Russian, English or Polish as appropriate.
- Use the full task description, not only score/reason summaries.
- Show direct understanding of the desired output.
- Give a concrete short implementation plan.
- Reference only real evidence or a clearly labelled demo.
- Recommend a realistic project/milestone price and delivery time.
- Do not invent years, project counts, clients, reviews, revenue or measured outcomes.
- Keep the final proposal copy-paste ready for the adult owner.
- Do not send it to Freelancehunt automatically.

## Telegram cards

### Project opportunity card

Must contain:

- clear event header and freshness
- title and clean link
- budget, deadline, category and competition when available
- full or clearly marked partial task summary
- service lane
- fit and win signals
- estimated effort and risks
- recommended price and timeline
- selected evidence
- copy-paste proposal draft
- exactly one adult-owner next action
- buttons/commands for open, regenerate, skip and status where supported

### Client/private-message card

Must bypass project-score filtering and arrive as high priority. Include:

- sender/display name
- subject/thread context
- full safe message body or useful excerpt
- direct platform thread link
- language
- AI-prepared reply draft when enough context exists
- `NEEDS_CONTEXT` when the email does not contain the previous conversation
- exactly one adult-owner next action

Do not auto-send the reply.

### Account/security card

Send only actionable security/account events. Never include OTPs, password-reset tokens or sensitive links in Telegram. Redact them and instruct the adult owner to open Gmail/Freelancehunt directly.

## Storage changes

Extend storage backward-compatibly so every opportunity/message can preserve the data required for later drafts and metrics. At minimum consider:

- event type
- full description/body
- description completeness
- language
- category/skills
- deadline
- bid count
- client fields
- recommended price/timeline
- estimated effort
- risks
- selected evidence
- proposal/reply draft
- thread/project URL
- source mailbox alias
- timestamps and processing state

Use a migration or idempotent schema upgrade. Do not destroy existing rows.

## Telegram command behavior

- `/reply_job` must use the persisted full description and/or return the already selected proposal.
- A rewrite action may generate a new version but must retain the original task data.
- `/skip_job` remains durable.
- Add or preserve a manual `/check` or `/gmail_check` command for immediate scans.
- Add a status command that reports OAuth identity alias, last successful scan, latency, fetched/actionable/duplicate/error counts, without exposing secrets.

## Tests and proof

Before deployment, require:

1. Unit tests for multilingual email classification.
2. Digest tests with multiple jobs.
3. Private-message tests.
4. Account/security redaction tests.
5. Dedup tests across repeated scans and restart simulation.
6. Proposal tests proving full description is used.
7. Brand/language tests proving no `OptiDigital` output remains in the active Gmail path.
8. Storage migration tests.
9. Telegram formatting tests within message limits.
10. Local read-only OAuth identity check against the adult-owned mailbox.
11. Real-mail dry run that performs no Gmail mutation and no platform action.
12. One controlled Telegram delivery from a sanitized fixture or explicitly selected existing email.

## Deployment gate

Codex must stop at:

`READY_FOR_RAILWAY_DEPLOY`

and report:

- branch and HEAD
- files changed
- tests run and results
- local OAuth account identity check result without exposing the address if the repository/report is public
- real-mail dry-run statistics
- sample Telegram card result
- exact Railway variables to add/change, with secret values represented only by placeholders
- rollback plan
- remaining risks

Do not deploy, merge, alter Railway variables or send a live platform message before explicit authorization.

## End-to-end acceptance test

The stage passes when:

```text
fresh Freelancehunt project/private-message email
→ detected within 2 minutes
→ classified correctly
→ persisted once
→ complete Telegram action card delivered
→ tailored proposal/reply draft available
→ adult owner can perform the final platform action with minimal editing
```

Record detection latency, duplicates, errors and the exact event type. No automatic Freelancehunt bid or message is part of acceptance.