# Next Action

## Current status

`READY_FOR_PROPOSAL_QUALITY_GATE_DEPLOY`

Instant discovery is deployed and verified, and the Telegram target-channel
migration is complete. The protected production baseline is:

- state: `DEPLOYED_LIVE_STATUS_HOTFIX_V2`;
- GitHub issue #7: completed;
- production `main`: `6b2d75d3b16e0b41531428926f9552f5ff6ab84b`;
- Railway deployment: `43a219b0-14e9-4f94-a108-b1a12e20039a`;
- deployment state: `SUCCESS / RUNNING`.

Stage 4 is active and GitHub issue #11 is the current work item. The isolated
branch `feature/proposal-quality-gate-v1` adds deterministic proposal-quality
validation after the existing live-status guard, separates commercial Score
from execution Fit, permits at most one bounded repair, and fails closed on
every proposal/action path. Current production Score/Fit `0.0` cards are not
proposal-ready.

Validation evidence:

- 239/239 tests pass, including 39 focused Stage 4 quality-gate tests;
- all 33 Stage 4 additive columns were present after two consecutive
  migrations against an isolated PostgreSQL 17 database;
- the read-only production audit found 52 ACTIVE_BIDDABLE legacy rows with
  Score `<= 0`, null/zero Fit and no controlled evidence registry ID;
- price, timeline and proposal were non-empty in those 52 rows, demonstrating
  why field presence alone is insufficient;
- production remains unchanged on the protected baseline above.

No merge, production deployment, Railway variable change, OAuth/Telegram
secret change, bid or client message is authorized by the Stage 4
implementation work.

## Exactly one next action

Review Draft PR for issue #11 and, if accepted, provide a separate explicit
proposal-quality-gate deployment authorization.
