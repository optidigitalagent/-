# Next Action

## Current authorization — production rollout, then offline Sales Brain V1

CURRENT_DEPLOY_GATE=PASS: 552 current full offline tests, 0 failures/errors/skips;
283 targeted tests are overlapping coverage, not additional unique tests.
Next action: complete the authorized zero-overlap production rollout, with
read-only data preflight before lifecycle activation. Keep production disabled
if existing opportunities make activation unsafe; do not backfill to force it.
Only after verified deploy/activation/tag: branch feat/sales-brain-v1 from exact
production SHA and build offline sales semantics/golden scenarios. No Sales Brain
deployment in this task. Controlled ledger 8/8; reserve $0.03262905 unchanged.
Previous priorities below are historical, not concurrent work instructions.

## Previous priority — sales quality after the narrow R2 freshness fix

R1 and R3 accepted by independent review. The reproduced R2 restart/freshness
gap is fixed locally: one FAIL before, all nine targeted tests PASS after.
Fresh dialogue suppresses obsolete sync tasks before tick; expiry renews the
sync identity once per observation event (legacy fallback: observation time).
Evidence: artifacts/private/a_to_b_r2_freshness/RESULT_RU.md and its delta zip.
MECHANICAL_A_TO_B_CANDIDATE_FOR_FREEZE=YES within the reviewed mechanics scope.
LIVE_SALES_QUALITY=NOT_VALIDATED; LIVE_CLIENT_CYCLE=NOT_RUN; PRODUCTION_CHANGED=NO.
No model calls; ledger 8/8, reserve $0.03262905 unchanged. Historic 175-test FAIL
and live failures #7/#8 remain unchanged. No production readiness claim.

Exactly one current next action: evaluate sales quality in a separately scoped
task using saved real material, without new model calls or external delivery.

Everything below is historical context, not another current action.

## Previous priority — review the R1–R3 correction delta

The three independent review findings are addressed locally in the existing
lifecycle/service/scheduler/notifier/handler. A first handoff receipt rechecks
current start prerequisites; pending internal follow-up cards survive failures
and restart; the literal owner action explicitly asks for its reference.
Evidence and run-by-run results: artifacts/private/a_to_b_r1_r3/RESULT_RU.md.
No model calls or production/external actions. Ledger remains 8/8 with reserve
$0.03262905. Default SALES_LIFECYCLE_ENABLED=false. Historical 175-test FAIL
and live responses #7/#8 are not reclassified. IMPLEMENTED_WITH_VALIDATION_BLOCKERS.

Exactly one current next action: independently review
artifacts/private/a_to_b_r1_r3/a_to_b_r1_r3_delta.zip against R1–R3.

Everything below is historical context, not another current action.

## Previous priority — initial local A→B mechanics review

Latest user scope explicitly allowed local minimal 5B/5C. The synthetic
PostgreSQL deal reaches IN_DELIVERY via existing 5A, true owner-confirmation
handlers, scheduler/draft cancellation, versioned agreements, start evidence,
handoff and team receipt, including restart/no-duplicate checks.
MECHANICAL_A_TO_B_TEST=PASS; LIVE_SALES_QUALITY=NOT_VALIDATED;
LIVE_CLIENT_CYCLE=NOT_RUN; PRODUCTION_CHANGED=NO.
No new model calls: ledger 8/8 and reserve $0.03262905 remain unchanged.
The failures from actual calls #7/#8 remain unresolved, not erased by fixtures.
5B/5C is opt-in and was not activated in production.

Exactly one current next action: review artifacts/private/a_to_b/a_to_b_review.zip
and its RESULT_RU.md, focusing on evidence/version guards and the actual synthetic handoff card.

Everything below is historical context, superseded only as the next-action priority.

## Current status

`IMPLEMENTED_WITH_VALIDATION_BLOCKERS`

Accepted delta proceeded to explicitly authorized real-model calls 7/8.
Fresh RSS/public check did not establish current full scope for 1651774:
10 RSS candidates, no 1651774, public helper status_code=0 (not asserted 403).
Historical real snapshot retained original timestamps/hash; no invented current status.
Main 7 and targeted repair 8 returned identical invalid CLIENT-reference ASK.
MODEL_ON_REAL_SNAPSHOT=FAIL; LIVE_MODEL_E2E=NOT_RUN; CURRENT_BID_READY=NO.
Ledger now 8/8; total reserves $0.03262905, new usage cost estimate $0.00237195.
All six prior entries unchanged. No further calls authorized. No PostgreSQL started;
renderer, 5A opportunity and external delivery not run. Account/billing NOT_VERIFIED.
Next action: review artifacts/private/issue20/validation_7_8/result_review.zip.
Report: artifacts/private/issue20/validation_7_8/RESULT_RU.md.

## Previous real-model result 5/6 (historical, superseded by 7/8 above)

Latest ASK-contract correction: mandatory example prices/times removed;
serialized decision branches prevent ASK offers and composition preserves ASK.
Calls 5/6 returned empty ASK offer fields, but both retain an unsupported
experience claim and an unnecessary client-examples question. One targeted
repair did not fix the content. MODEL_ON_REAL_SNAPSHOT=FAIL.
Persistent ledger is 6/6, with $0.02232975 cumulative reserves. New calls cost
an estimated $0.00223575; historical entries/reserves are unchanged. No model
requests remain authorized. ACCOUNT_IDENTITY and BILLING are NOT_VERIFIED;
current-key use was EXPLICIT. No /me, keys or billing operations were repeated.
Fresh bounded RSS/public enrichment did not establish current full scope:
public helper status_code=0, not an asserted HTTP 403. Historical source retains
original timestamps/hash. LIVE_MODEL_E2E=NOT_RUN; CURRENT_BID_READY=NO.
Targeted/related offline tests and isolated synthetic PostgreSQL ASK/TAKE
round-trip passed; local cluster stopped. Real-model PostgreSQL/reload,
renderer, delivery and 5A were NOT_RUN. No production changes.
See artifacts/private/issue20/ASK_CONTRACT_IMPLEMENTATION_REPORT.md and
review_package_20260907_ask_contract.zip in the same private directory.

The historical first 429 remains `UNKNOWN`, and the exact causes of the two
historical production `INVALID` records remain unproved. Production and all
external systems remain unchanged.

## Exactly one next action

Review validation_7_8/result_review.zip and RESULT_RU.md under artifacts/private/issue20.
No new model call or automatic filter rewrite: allowance is exhausted at 8/8.
