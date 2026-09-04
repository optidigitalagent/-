# Next Action

## Current status

`READY_FOR_SALES_CLOSER_5A_DEPLOY_V4`

Draft PR #16 remains the only Release 5A work item. Correction cycle V4 closes
the three final review blockers: real `profile/show` platform-support routing,
terminal-rejection/contract/price precedence, and exact-identity atomic
orphan-to-canonical recovery. It preserves V3's parser, actor, version/hash,
human-decision, stale-draft, ACK/escalation, Stage 4 fallback and no-platform-
write protections.

Validation evidence:

- 12 focused V4 tests plus 30 parameterized subtests pass;
- five isolated PostgreSQL 17 tests pass, including migrations twice,
  concurrent merge, restart, repeat import and future-thread routing;
- the full ordered suite passes 425 tests with six unrelated opt-in skips while
  the disposable sales PostgreSQL URL is enabled;
- Python 3.12.14 production import, compileall, changed-file Ruff F rules,
  Telegram HTML/size regressions and `git diff --check` pass.

Production remains unchanged on `main`
`1f0bfb2ab95deb97cdde2eedd09fea7bceeecb05`, Railway deployment
`765ba1da-4df3-4472-8ea8-b0d6fa5dad05`. No merge, deployment, variable,
secret, backfill or platform action was performed.

## Exactly one next action

Review Draft PR #16 correction cycle V4 and, if accepted, provide separate
explicit merge/deployment authorization.
