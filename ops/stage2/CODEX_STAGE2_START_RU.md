# Codex Start — Stage 2 Gmail → Railway → Telegram

Use this file as the execution instruction for the Stage 2 implementation cycle.

## Mission

The genuine adult-owned Freelancehunt profile is verified. Convert the existing `optidigital-agent/` implementation into a production-ready Antonov Digital revenue-alert flow for the new adult-owned Gmail mailbox.

Do not work in the standalone profile-setup package. Work in the canonical Git repository `https://github.com/optidigitalagent/-`.

## Workspace bootstrap

Perform workspace setup autonomously:

1. Locate an existing local clone of `optidigitalagent/-`.
2. If no valid clone exists, clone it to a clean, descriptive local folder.
3. Fetch all remote refs.
4. Inspect `main`, `setup/project-brain-v1`, the current Railway-linked branch and their HEADs.
5. Do not modify `main` or the Railway-linked production branch.
6. Create an isolated worktree/branch from `setup/project-brain-v1` unless inspection proves a different base is required to preserve the actual production baseline.
7. Recommended feature branch: `feature/freelancehunt-gmail-telegram-v1`.
8. Open a Draft PR against `setup/project-brain-v1` after the first coherent tested implementation commit.

Do not ask the user to run Git commands. Handle clone, branch, worktree and commits yourself. Stop only if GitHub authentication genuinely requires owner action.

## Required reading

Read in order:

1. `AGENTS.md`
2. `.codex/project_brain/PROJECT_BRAIN.md`
3. `.codex/project_brain/BUSINESS_RULES.md`
4. `.codex/project_brain/PLATFORM_RULES.md`
5. `.codex/project_brain/DECISIONS.md`
6. `.codex/project_brain/GOAL_PROGRESS.md`
7. `.codex/project_brain/NEXT_ACTION.md`
8. `docs/CODEX_EXECUTION_REPORTING_STANDARD.md`
9. `docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`
10. `docs/LEGACY_AGENT_ARCHITECTURE.md`
11. the complete `optidigital-agent/` implementation and tests

## Preserve and fix

Preserve the existing working Gmail OAuth, parsing, PostgreSQL dedup, retry queue, Telegram and Railway architecture. Do not rewrite the service from scratch.

Implement every acceptance requirement in `docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`, including:

- detection latency no worse than 2 minutes under normal operation
- explicit multilingual event classification
- high-priority private-message handling
- full task/message context persisted durably
- project opportunity enrichment through permitted read-only sources
- revenue-oriented analysis across all supported service lanes
- recommended project/milestone price, realistic delivery time, evidence and risk
- copy-paste proposal/reply draft in the client's language
- complete Telegram action cards
- `/reply_job` based on full persisted context
- Antonov Digital branding throughout the active Gmail path
- safe security-event redaction
- restart-safe deduplication and retry
- no automatic bid or platform-message submission

## Real mailbox OAuth

The Gmail account connected to ChatGPT is not automatically available to Railway.

Create a separate local Gmail API OAuth authorization for the adult-owned operational mailbox using read-only scope.

Rules:

- never request the Gmail password in chat
- never print or commit token JSON
- never place the token in source files
- verify the authenticated Gmail profile is the intended adult-owned operational mailbox
- store local token files only in ignored paths
- represent Railway secret values as placeholders in reports

When Google login/consent is required, stop with exactly:

`GMAIL_OAUTH_OWNER_ACTION_REQUIRED`

Open the authorization URL or browser window, state only the account that must be selected, and wait. After the adult owner completes login and read-only consent, resume automatically.

## Real-mail validation

Use the adult-owned mailbox only in read-only mode.

The mailbox already contains Freelancehunt support/private-message email patterns. Use a sanitized real-message dry run to prove classification and Telegram rendering. Do not mark, archive, delete or reply to Gmail messages.

A fresh project digest may not exist yet. This must not block implementation. Use fixtures for project/digest tests and a sanitized real private-message email for the controlled real-mail path. Keep the final live project-digest acceptance item explicitly pending until a real digest arrives.

## Telegram controlled test

Send only a clearly labelled test card to the already approved Telegram test/admin chat. Do not send any message to a Freelancehunt client or platform thread.

The test must prove:

- no sensitive token/reset data leaks
- correct event type
- correct source link handling
- correct full-context or `NEEDS_CONTEXT` behavior
- correct language
- copy-paste draft
- stable dedup key

## Validation

Run all relevant existing and new tests. Add tests for:

- Ukrainian, Polish, Russian and English subject patterns
- digest with multiple jobs
- private messages
- project/status events
- account/security redaction
- repeat scan and restart deduplication
- storage migration/backward compatibility
- full-description proposal generation
- no active `OptiDigital` branding in Gmail/Telegram output
- Telegram length/HTML safety
- wrong OAuth mailbox fail-closed behavior

Do not weaken tests to make them pass.

## Deployment gate

Do not deploy, merge or change Railway variables.

Stop only after tested implementation and return:

`READY_FOR_RAILWAY_DEPLOY`

The report must include:

- objective and commercial effect
- production baseline branch and HEAD
- feature branch and HEAD
- Draft PR URL
- exact files changed
- schema migration details
- exact tests and results
- OAuth identity check without secrets
- real-mail dry-run counts by event type
- controlled Telegram result
- sanitized project-card example
- sanitized private-message-card example
- exact Railway variables with placeholder values
- expected detection latency
- rollback plan
- unresolved risks
- one next action

If any part cannot be completed, continue all safe work and report one precise blocker plus the completed evidence. Never return only a short blocker code.