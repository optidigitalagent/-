# Antonov Digital Freelance Revenue Engine

## Mission

Build a lawful, measurable and highly automated revenue system for Antonov Digital that converts opportunities into funded client projects with minimal manual involvement before delivery.

The system is judged by funded revenue, completed projects, reviews, repeat clients and net profit — not by feature count, alerts, prompts or AI calls.

## Team

- Founder 1: management, marketing, client acquisition, communication and selected development work.
- Founder 2: primary developer.
- Public brand: Antonov Digital.
- Public claims must be factual and supported by evidence.

## Current phase

**Stage 0 — Project brain and operating system.**

No production development is required in this stage. The goal is to establish durable context, rules, workflows, account strategy, email roles, metrics and handoff conventions before profile setup and implementation.

## Current repository status

- Canonical repository: `optidigitalagent/-`
- Target repository name: `antonov-digital-freelance-revenue-engine`
- Current visibility: public
- Target visibility: private
- Project-brain branch: `setup/project-brain-v1`

Because the repository is currently public, exact mailbox addresses and other private configuration are intentionally excluded.

## Source of truth

- ChatGPT Project: strategy, profile work, proposal work and operating discussions.
- GitHub repository: durable rules, facts, decisions, current state and code.
- Codex app / CLI / IDE: repository execution, implementation, tests and draft pull requests.
- VS Code: local inspection, debugging, testing and manual review.
- Railway: runtime and deployment only; it is not the project brain.

## Required reading order

1. `AGENTS.md`
2. `.codex/project_brain/PROJECT_BRAIN.md`
3. `.codex/project_brain/BUSINESS_RULES.md`
4. `.codex/project_brain/PLATFORM_RULES.md`
5. `.codex/project_brain/DECISIONS.md`
6. `.codex/project_brain/GOAL_PROGRESS.md`
7. `.codex/project_brain/NEXT_ACTION.md`

## Repository map

- `optidigital-agent/` — existing working agent implementation.
- `.codex/project_brain/` — durable business context and changing project state.
- `.codex/workflow/` — how ChatGPT and Codex plan, execute, review and report work.
- `docs/` — channels, lifecycle, metrics and ChatGPT Project setup.

## Security

Never commit passwords, OAuth refresh tokens, API keys, cookies, session files, Telegram tokens, client secrets, private mailbox mappings or private client data.

Use `.env.example` for variable names only. Store production secrets in Railway environment variables or another approved encrypted secret manager.

## Account strategy

- Use one legitimate Freelancehunt freelancer account in an approved legal format.
- Never use duplicate, fake or decoy freelancer accounts.
- Never submit deliberately weak bids to manipulate a client’s perception.
- Never automate bids or messages where the platform prohibits it.
- Use one broad, truthful Antonov Digital profile and route each opportunity internally to the most relevant service lane, case and proposal.

## Development governance

- Protect `main`.
- Use a dedicated branch and draft pull request.
- Do not merge, deploy or modify production without explicit authorization.
- Every completed task must update project state where applicable.
