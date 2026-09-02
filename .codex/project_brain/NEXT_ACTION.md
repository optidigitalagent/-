# Next Action

## Immediate objective

Activate the verified adult-owned Freelancehunt account as a revenue channel by adapting the existing Gmail/Railway/Telegram agent to the new operational mailbox and producing complete proposal-ready Telegram cards.

## Completed state

- Adult-owned profile: `https://freelancehunt.com/freelancer/AntonovDigital.html`
- Commercial profile core: complete
- Adult phone: confirmed
- Дія.Підпис verification: completed, reported by the user
- Operational Gmail connection to ChatGPT: confirmed
- Freelancehunt support/private-message delivery to the operational mailbox: confirmed
- Portfolio remains deferred without blocking launch

Do not return to profile copy, owner-source repair or profile regeneration unless a real live defect is discovered.

## Single next action

Run a Codex implementation cycle against the canonical repository using:

`docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`

Codex must inspect and extend the existing implementation under `optidigital-agent/`; it must not rewrite the system from scratch.

## Required Codex sequence

1. Read, in order:
   - `AGENTS.md`
   - `.codex/project_brain/PROJECT_BRAIN.md`
   - `.codex/project_brain/BUSINESS_RULES.md`
   - `.codex/project_brain/PLATFORM_RULES.md`
   - `.codex/project_brain/DECISIONS.md`
   - `.codex/project_brain/GOAL_PROGRESS.md`
   - `.codex/project_brain/NEXT_ACTION.md`
   - `docs/CODEX_EXECUTION_REPORTING_STANDARD.md`
   - `docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`
   - `docs/LEGACY_AGENT_ARCHITECTURE.md`
2. Record the current production branch, HEAD, Railway service linkage and existing runtime variable names before changing code.
3. Create a new isolated feature branch from the confirmed production baseline. Recommended name:
   `feature/freelancehunt-gmail-telegram-v1`.
4. Audit the full `optidigital-agent/` Gmail, classifier, parser, analyzer, storage, Telegram, command, scheduler and test paths.
5. Preserve working behavior outside the Stage 2 scope.
6. Implement the smallest complete solution in `docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`.
7. Keep Gmail OAuth read-only and keep every Freelancehunt platform action manual for the adult owner.
8. Generate the new adult-owned Gmail OAuth token locally. Confirm the OAuth profile identity without exposing the address in public logs or committing token material.
9. Run unit/integration tests, a read-only real-mail dry run and one controlled Telegram delivery.
10. Do not deploy or change Railway variables yet.
11. Stop at:

```text
READY_FOR_RAILWAY_DEPLOY
```

## Minimum implementation requirements

- normal detection latency at most 2 minutes
- explicit multilingual classification for project digests, single projects, private messages, project/status events, account/security events, marketing and unknown mail
- private/client messages bypass project-score filtering and arrive as high priority
- complete durable task/message context
- Telegram project card with budget, deadline, category, fit, risk, estimated effort, recommended price/time, evidence and a copy-paste proposal
- Telegram private-message card with the message context, thread link and reply draft or `NEEDS_CONTEXT`
- `/reply_job` uses the full persisted task description or saved proposal, not analysis summaries
- all active Gmail-path branding changed from `OptiDigital` to `Antonov Digital`
- client language matched across Ukrainian, Russian, English and Polish
- no fixed minimum budget and no pre-prioritization of service lanes
- no invented experience, clients, reviews, metrics or results
- durable deduplication and retry after restart
- safe redaction of OTPs, reset tokens and sensitive security links

## Required deployment-gate report

The `READY_FOR_RAILWAY_DEPLOY` response must include:

- objective and commercial impact
- branch and exact HEAD
- production baseline branch and HEAD
- exact files changed
- database/schema migration details
- tests run with exact results
- OAuth mailbox-identity check result without secrets
- real-mail dry-run statistics by event type
- controlled Telegram test result
- sample sanitized project card
- sample sanitized private-message card
- exact Railway variables to add/change with placeholder values only
- expected polling latency
- rollback plan
- unresolved risks
- exactly one next action

## Constraints

- Do not use or reactivate the minor-owned account.
- Do not submit bids or send Freelancehunt messages automatically.
- Do not alter profile, identity, documents, verification, contracts or payments.
- Do not commit Gmail credentials, token JSON, passwords, cookies, OTPs or recovery data.
- Do not deploy, merge or modify Railway before explicit authorization.
- Do not regenerate the completed profile or portfolio strategy.

## Stop condition

This action is complete only when the implementation has been tested and Codex returns `READY_FOR_RAILWAY_DEPLOY` with the required evidence. The following action will be explicit Railway variable configuration, deployment and a live end-to-end test.