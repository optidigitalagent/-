# AGENTS.md — Antonov Digital Freelance Revenue Engine

## Required reading

Before any work, read in this order:

1. `.codex/project_brain/PROJECT_BRAIN.md`
2. `.codex/project_brain/BUSINESS_RULES.md`
3. `.codex/project_brain/PLATFORM_RULES.md`
4. `.codex/project_brain/DECISIONS.md`
5. `.codex/project_brain/GOAL_PROGRESS.md`
6. `.codex/project_brain/NEXT_ACTION.md`
7. Existing `GOAL.md` and root `GOAL_PROGRESS.md` when work touches the legacy agent.

## Primary objective

Maximize legitimate net funded revenue for Antonov Digital through:

`opportunity -> qualification -> proposal -> reply -> negotiation -> funded project -> delivery -> payout -> review/repeat work`

Do not optimize for feature count, technical novelty, message volume or activity without a measurable commercial purpose.

## Existing implementation baseline

The current production-oriented agent lives under `optidigital-agent/` and already contains Gmail ingestion, AI analysis, Telegram notifications, reply drafting, persistence and Railway-related runtime logic. Preserve existing working behavior unless a task explicitly replaces it.

The current baseline is a job-notification and proposal-draft system, not yet a complete revenue engine. Production development is out of scope during Stage 0.

## Non-negotiable rules

- Use only truthful identities, team structure, experience, portfolio evidence and metrics.
- Use one legitimate Freelancehunt freelancer account in an approved format.
- Do not create or support duplicate/fake accounts, decoy bids, staged competition, spam, prohibited auto-bidding, verification bypasses or policy evasion.
- Do not invent client facts, results, testimonials, timelines or capabilities.
- Do not commit passwords, OAuth tokens, API keys, cookies, session files, client secrets or literal private mailbox mappings to a public repository.
- Do not merge, deploy, change production or modify `main` without explicit authorization.
- Use a branch and draft pull request for repository changes.
- Keep ordinary reversible work autonomous, but do not make irreversible legal, payment, scope or production commitments outside approved rules.

## Working protocol

1. Inspect the repository and project-state files before changing anything.
2. Map every task to a funnel stage and measurable result.
3. Prefer the smallest change that improves revenue, conversion, reliability or delivery speed.
4. Preserve existing working behavior outside scope.
5. Validate changes with targeted tests or document checks.
6. Update `DECISIONS.md`, `GOAL_PROGRESS.md` and `NEXT_ACTION.md` when state changes.
7. Report: decision, files changed, validation, risks, commercial impact and next action.

## Discovery policy

Do not pre-prioritize AI agents, automation, Telegram bots, CRM, websites, MVPs, AI content or other supported services. Test them using real market data and shift resources only after measurable response, win-rate, profit and delivery evidence exists.
