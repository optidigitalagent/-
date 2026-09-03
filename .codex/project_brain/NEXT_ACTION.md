# Next Action

## Current status

`READY_FOR_PROPOSAL_QUALITY_GATE_NULLABLE_METADATA_HOTFIX_DEPLOY`

Stage 4 issue #11 remains open after PR #12 was rolled back. The follow-up
branch is `fix/proposal-quality-gate-nullable-score-fit-metadata-v1`, created
from rollback `main` `01978e2b1935ea708f86afdeaed321bb3f8db8c2`.
Commit `a44641f` cleanly reapplies the approved Stage 4 tree, and separate
commit `39beac1` adds the nullable Score/Fit metadata hotfix.

Validation evidence:

- all 302 protected tests remain passing; the full suite discovers 310 tests,
  runs 304 successfully and skips only six opt-in PostgreSQL cases;
- all eight focused nullable-metadata tests pass when those six cases run on
  an isolated real PostgreSQL 17 server;
- compileall, Ruff F-rule checks, `git diff --check`, and production-like
  Python 3.12.14 imports pass;
- the pre-fix real PostgreSQL test reproduced SQLSTATE 23502 on
  `fit_score_valid=NULL`; the identical route passes after normalization;
- clean and production-like existing-column schemas each accepted `init_db`
  twice and retained NOT NULL boolean/state contracts;
- scheduler, second-cycle, restart, conflict-upsert, update, live recheck and
  quality-backfill persistence paths retain coherent Score/Fit semantics;
- production remains unchanged on rollback `main`
  `01978e2b1935ea708f86afdeaed321bb3f8db8c2`, Railway deployment
  `5af42416-7c91-4283-9c26-8282f0d6f4d4` (`SUCCESS`, 1/1 replica running).

No merge, deployment, Railway variable change, OAuth/Telegram secret change,
backfill, replacement card, bid, client message, contract, or payment was
performed.

## Exactly one next action

Review the new follow-up Draft PR and, if accepted, provide a separate explicit
nullable-metadata hotfix deployment authorization.
