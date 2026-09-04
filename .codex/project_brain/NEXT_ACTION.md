# Next Action

## Current status

`READY_FOR_SINGLE_SHARED_OPERATOR_ZERO_OVERLAP_REDEPLOY_V2`

The issue #17 reapply branch now includes the narrow stale-reply precedence
correction on top of the exact approved shared-operator tree. One deterministic
contract is shared by preview, in-memory confirmation and PostgreSQL
confirmation; only actual stale confirmation persists `OUTGOING_SUPERSEDED`.

Validation evidence:

- 81 focused V2/shared-operator tests pass;
- full discovery passes 474 tests with 12 opt-in PostgreSQL skips;
- six real PostgreSQL 17 tests pass with migrations twice and restart proof;
- Python 3.12.14 production-like import, compileall, changed-file Ruff F rules
  and `git diff --check` pass.

Production remains unchanged on rollback `main`
`6baaa462ef70e40d45e9c144e269eff71786f35b`, Railway deployment
`480c3170-f354-4e4d-909d-c7a0e771e5d3` (`SUCCESS / RUNNING`). No merge,
deployment, variable, secret, OAuth, production migration/backfill, real
Telegram card or platform action was performed. Release 5B/5C remain deferred.

## Exactly one next action

Review the new stale-reply correction Draft PR and, if accepted, provide the
separate zero-overlap merge/deployment authorization.
