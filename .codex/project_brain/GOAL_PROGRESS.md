# Goal Progress

## North-star goal

Create a repeatable system that produces funded Antonov Digital client work with minimal manual sales effort.

## Current stage

**Stage 5 — issue #17 stale-reply correction before shared-operator redeploy**

## Readiness by workstream

- **Adult-owned Freelancehunt profile core: 100% complete**
- **Adult phone confirmation: complete**
- **Дія.Підпис verification: completed, reported by the user**
- **Operational Gmail connection to ChatGPT: confirmed**
- **Gmail support/private-message delivery from Freelancehunt: confirmed**
- **Instant official-RSS discovery: deployed and verified**
- **Railway → Telegram target-channel migration: completed**
- **Proposal-quality gate V3 plus nullable-metadata hotfix: deployed and verified**
- **AI Sales Closer Release 5A V4: deployed; issue #17 stale-reply correction is ready for Draft PR review**
- **Portfolio: deferred where evidence/media is incomplete; does not block launch**
- **Minor-owned account: 0% operational and excluded**

## Current live status

- `ADULT_IDENTITY_VISIBLE`
- `ADULT_PHONE_CONFIRMED_NEW_ACCOUNT`
- `CORE_PROFILE_PUBLISHED`
- `FOUR_LANGUAGE_COPY_SAVED`
- `PRIMARY_SPECIALIZATIONS_SAVED`
- `ADDITIONAL_SPECIALIZATIONS_SAVED`
- `TWENTY_SKILLS_SAVED`
- `NOTIFICATIONS_CONFIGURED`
- `PUBLIC_QA_PASSED`
- `ADULT_DIIA_VERIFICATION_COMPLETED`
- `OPERATIONAL_GMAIL_CONNECTED`
- `FREELANCEHUNT_PRIVATE_MESSAGE_EMAIL_CONFIRMED`
- `PORTFOLIO_DEFERRED`
- `REVENUE_FLOW_IMPLEMENTATION_REQUIRED`
- `DEPLOYED_LIVE_STATUS_HOTFIX_V2`
- `ISSUE_7_COMPLETED`
- `INSTANT_DISCOVERY_DEPLOYED_AND_VERIFIED`
- `TELEGRAM_CHANNEL_MIGRATION_COMPLETED`
- `STAGE_4_DEPLOYED_AND_VERIFIED`
- `ISSUE_11_COMPLETED`
- `STAGE_5_ACTIVE`
- `SALES_CLOSER_5A_V4_DEPLOYED`
- `ISSUE_17_CURRENT_WORK_ITEM`
- `READY_FOR_SINGLE_SHARED_OPERATOR_ZERO_OVERLAP_REDEPLOY_V2`

## Protected production baseline

- Production rollback `main`: `6baaa462ef70e40d45e9c144e269eff71786f35b`.
- Railway deployment: `480c3170-f354-4e4d-909d-c7a0e771e5d3`.
- Railway state: `SUCCESS / RUNNING`.
- Live-status state: `DEPLOYED_LIVE_STATUS_HOTFIX_V2`.
- GitHub issue #7 is completed. Its V2 safety guard must not be weakened.
- Instant discovery is deployed and verified, and the Telegram channel
  migration is complete.
- Stage 4 is deployed and verified; GitHub issue #11 is completed.
- Release 5A V4 is deployed. Stage 5 remains active; GitHub issue #17 is the
  current narrow operational hotfix.
- Release 5B timed follow-ups and Release 5C delivery handoff are deferred.

## Completed account and profile work

- [x] New genuine adult-owned Freelancehunt account created
- [x] Public profile URL confirmed: `https://freelancehunt.com/freelancer/AntonovDigital.html`
- [x] Adult-owner name, photo and phone confirmed
- [x] Adult owner completed Дія.Підпис verification personally
- [x] Ukrainian, English, Russian and Polish descriptions and slogans published
- [x] Status saved as `Вільний для роботи`
- [x] Main specializations saved: `AI та машинне навчання`, `Веб-програмування`
- [x] Twenty-six additional specializations saved
- [x] Twenty skills saved and publicly displayed
- [x] No invented hourly rate published
- [x] Antonov Digital team roles disclosed consistently
- [x] Daily project digest enabled
- [x] Private-message email notifications enabled
- [x] System information emails enabled
- [x] Browser push enabled
- [x] Sound notifications enabled
- [x] Promotional, news and blog mail disabled
- [x] Desktop/mobile public QA passed
- [x] Operational adult-owned Gmail mailbox connected to ChatGPT
- [x] Freelancehunt support/private-message emails confirmed on the operational mailbox

## Existing implementation baseline

The current code under `optidigital-agent/` already contains:

- Gmail OAuth read-only access
- email MIME parsing and sanitization
- digest parsing
- AI scoring
- PostgreSQL deduplication and retry queue
- Telegram cards
- `/reply_job` and `/skip_job`
- Railway-oriented environment configuration

Do not rewrite it from scratch.

## Confirmed implementation gaps

- [x] Feature configuration defaults now use real mode and a 60-second interval; production deployment remains gated
- [x] Feature polling target is fast enough for the two-minute normal-latency objective
- [x] Freelancehunt private-message patterns are explicit high-priority event types
- [x] Telegram cards contain the complete commercial decision package
- [x] Stored Gmail jobs preserve full safe task/message context
- [x] `/reply_job` uses the full persisted description, context, evidence, price, timeline and saved proposal
- [x] Active Gmail prompts/messages use Antonov Digital branding
- [x] Scoring uses the approved no-minimum-budget, no-preferred-lane revenue policy
- [x] The adult-owned OAuth identity and production ingestion baseline have been proven
- [x] Local adult-mailbox read-only test and controlled Telegram validation completed; the deployed flow supersedes this historical gate

## Stage 2 implementation plan

Follow `docs/STAGE_2_GMAIL_TELEGRAM_ACTIVATION.md`.

Required result:

```text
fresh Freelancehunt project/private-message email
→ detected within 2 minutes
→ classified correctly
→ persisted once
→ complete Telegram action card delivered
→ tailored proposal/reply draft available
→ adult owner performs the final platform action
```

## Immediate implementation work

- [x] Create an isolated feature branch from the confirmed safe Stage 2 base
- [x] Add explicit multilingual project/private-message/account event classification
- [x] Switch all active Gmail-path branding to Antonov Digital
- [x] Preserve full task/message context in durable storage
- [x] Fix proposal generation to use the full task description
- [x] Add revenue-oriented price/time/risk/evidence fields
- [x] Reduce normal Gmail detection latency to at most 2 minutes
- [x] Add high-priority private-message cards and safe security-event handling
- [x] Add tests for classification, deduplication, migration, proposals and Telegram formatting
- [x] Generate a local read-only OAuth token for the adult-owned operational mailbox
- [x] Verify the OAuth account identity without exposing token material
- [x] Run a real-mail dry run and one controlled Telegram delivery
- [x] Stop at `READY_FOR_RAILWAY_DEPLOY` with proof, variables and rollback plan

## 2026-09-02 — Stage 2 local validation result

- Local deployment-gate readiness: 0% -> 100%.
- Live production activation remains pending explicit Railway authorization.
- OAuth `gmail.readonly` identity: verified as public-safe alias
  `ur***@gmail.com`; mismatches wrote no token.
- Historical read-only Gmail probe: 8 platform emails; 4 private-message,
  1 marketing and 3 unknown; zero Gmail mutations.
- Controlled Telegram validation: one synthetic `[TEST]` card accepted as one
  message; zero real client/project data and zero Freelancehunt actions.
- Final implementation evidence is maintained in
  `docs/STAGE_2_DEPLOYMENT_GATE.md` and Draft PR #2.

## Deferred portfolio

The following prepared cards remain deferred until each has current links/status, permission, evidence and images:

- Bella Dent
- Dental Supplier AI Agent
- Gmail/Telegram Job Agent
- Status Dent
- Amidental
- Art Studio 184
- Audiobook Cleaner
- Mentium
- NFC Review Cards

Portfolio does not block Stage 2.

## Minor-owned account final state

- [x] Successful identity verification did not grant work access
- [x] Support confirmed ineligibility until `2029-01-28`
- [x] No bids, agreements or payments occurred after verification
- [ ] Preserve deactivation confirmation if not already stored outside the repository
- [ ] Keep the account and its notifications excluded from all ingestion

## Repository administration still pending

- [ ] Review and approve Draft PR #1
- [ ] Rename repository to `antonov-digital-freelance-revenue-engine`
- [ ] Change repository visibility to private
- [ ] Confirm Railway/GitHub linkage after rename
- [ ] Finish the ChatGPT Project and chat structure

## Stage 2 acceptance condition

Stage 2 is operational when:

1. the adult-owned verified profile remains conversion-ready;
2. a fresh project or private-message email reaches the approved mailbox;
3. Railway detects it within 2 minutes without duplicates;
4. Telegram receives a complete action card;
5. a tailored proposal/reply draft is generated from full available context; and
6. the adult owner can perform the final platform action with minimal editing.

## 2026-09-02 — Issue #7 live-status hotfix validation

- Hotfix implementation and local validation: 100% complete.
- Historical validation status at that checkpoint was
  `READY_FOR_LIVE_STATUS_HOTFIX_DEPLOY`; it was subsequently deployed and is
  superseded by the protected production baseline recorded above.
- Root cause closed in code: email/parser freshness was previously trusted
  without a live positive bid-availability proof, so a blocked project could
  reach scoring, proposal generation and a revenue-ready Telegram card.
- Both Freelancehunt ingestion paths now use one HTTP-first, anonymous
  Playwright-fallback guard before AI/scoring and before proposal-card delivery.
- Only `ACTIVE_BIDDABLE` with `biddable=true` can be qualified or expose direct
  proposal actions. Blocked, closed, executor-selected, deleted/unavailable and
  unknown projects are fail-closed.
- Additive persistence covers status, checked time, evidence, biddability,
  retry count, last error and qualification in both `orders` and `gmail_jobs`.
- Sanitized project 1650987 fixture result:
  `BLOCKED_RULE_VIOLATION`, `biddable=false`, `qualified=false`, no generated or
  displayed proposal.
- Validation proof: 164/164 Gmail-agent regression tests passed; compileall,
  migration contracts, active/blocked fixtures, Telegram formatting,
  UNKNOWN retry, repeat/restart dedup and production-like imports passed.
- Anonymous live verification of the actual 1650987 page remains
  `LIVE_STATUS_UNKNOWN` because the guessed canonical URL returned protected
  HTTP and the local browser fallback could not verify the page. The supplied
  issue evidence is represented only by the sanitized deterministic fixture;
  no stronger live claim is made.
- Production baseline remains main commit
  `60d5d3b30a9f21d8011f3d76f8b288fb3abcbd4d` on Railway deployment
  `fa129303-e1e3-42c1-b913-72469678b76d`; no production mutation was performed.

## 2026-09-02 — Deployment review V2 completed

- Closed the four review blockers: 60-second action freshness, durable UNKNOWN
  exhaustion plus manual read-only recheck, bounded shared-resource batch
  checking, and retry-safe Telegram diagnostics.
- Added Freelancehunt's official anonymous open-project RSS as a positive-only
  fallback for Cloudflare-protected HTML. Absence remains fail-closed and does
  not become a terminal classification.
- Full regression: 181/181 tests passed, including the previous 164 tests and
  17 V2 tests. Compileall, diff check, additive migration contracts and the
  dependency-complete Python 3.12 startup import passed; three scheduler jobs
  remain registered with overlap protection unchanged.
- Railway/Linux anonymous proof against the exact public URL 1650987 returned
  `LIVE_STATUS_UNKNOWN`, `biddable=false`, and zero proposal-generation calls.
  A current public-feed item returned `ACTIVE_BIDDABLE`, `biddable=true`, with
  official RSS membership as evidence. Three cold ten-project runs returned
  10/10 active; maximum measured time was 0.163 seconds.
- At that review checkpoint production remained on main commit
  `60d5d3b30a9f21d8011f3d76f8b288fb3abcbd4d`, deployment
  `fa129303-e1e3-42c1-b913-72469678b76d`. No merge, deployment, Railway
  variable, Gmail OAuth, Telegram secret or platform action occurred. That
  historical snapshot is superseded by the deployed baseline below.
- Deployment state: `DEPLOYED_LIVE_STATUS_HOTFIX_V2` on production `main`
  `da58c7bb4a6c3a4565f3590f83f7301b2e7b41c5`, Railway deployment
  `c9a3cebe-36b7-4697-9ec0-bd01dbc0c77a` (`SUCCESS / RUNNING`). Issue #7 is
  completed and superseded as the current work item by Stage 3 issue #9.

## 2026-09-02 — Stage 3 issue #9 deployment gate

- Created isolated branch `feature/freelancehunt-instant-discovery-v1` from
  the exact protected production baseline `da58c7bb4a6c3a4565f3590f83f7301b2e7b41c5`.
- The official public Freelancehunt project RSS is the primary discovery
  source. It feeds the shared live-status, commercial-analysis, durable dedup
  and Telegram pipeline on a 60-second overlap-protected schedule.
- One numeric Freelancehunt project ID now produces one stable repository key
  across RSS, Gmail single/digest events and the retained legacy parser.
- The feed path has no legacy keyword rejection or minimum-budget gate. It
  records executable yes/maybe/no, service lane, fit, effort, delivery/payment
  risk and CASH/REPUTATION/STRATEGIC mode.
- Only `ACTIVE_BIDDABLE` reaches price, timeline and proposal generation.
  Non-active and UNKNOWN states fail closed under the deployed V2 guard.
- Freelancehunt was removed from the old hourly automatic parser while
  Kabanchik and FreelanceUA remain. The read-only manual debug path remains.
- No bid, client message, merge, production deployment or Railway variable
  change is part of this implementation branch.
- Canonical QA: 200/200 tests passed (181 protected baseline + 19 Stage 3),
  compileall passed and `git diff --check` is clean apart from line-ending
  notices.
- PostgreSQL-like migration proof executed all 79 additive migration statements
  twice; all required Stage 3 columns existed and no destructive statement ran.
- Python 3.12 production-like startup under Railway runtime configuration
  imported the application and registered 60 seconds, `max_instances=1`,
  `coalesce=true`.
- A current official feed returned 50 parseable public projects; a sanitized
  current item resolved to a canonical ID and `ACTIVE_BIDDABLE`,
  `biddable=true`, without browser fallback.
- Controlled sanitized card telemetry measured 25.053 seconds from publication
  to send; immediate repeat and repository recreation each produced one
  duplicate and total send calls remained one.
- Production recheck confirmed unchanged `main`
  `da58c7bb4a6c3a4565f3590f83f7301b2e7b41c5` and Railway deployment
  `c9a3cebe-36b7-4697-9ec0-bd01dbc0c77a` (`SUCCESS`).
- Status: `READY_FOR_INSTANT_DISCOVERY_DEPLOY`.

## 2026-09-03 — Stage 4 issue #11 deployment gate

- Instant discovery is now `INSTANT_DISCOVERY_DEPLOYED_AND_VERIFIED`, and
  `TELEGRAM_CHANNEL_MIGRATION_COMPLETED` is the current channel state.
- The proposal-quality gate runs after the unchanged live-status guard and
  before qualification or Telegram delivery. Score and Fit remain separate;
  only fresh `ACTIVE_BIDDABLE` + `executable=yes` + `QUALITY_VALID` or
  `QUALITY_REPAIRED` can expose a proposal action.
- Missing, null, malformed, non-finite and zero Score/Fit fail closed for
  executable yes/maybe. Evidence is selected from the controlled Project Brain
  registry, and proposal text is checked for placeholders, contacts,
  unsupported claims, language, scope, specificity and commercial consistency.
- One exact-error repair is permitted. A second deterministic failure becomes
  manual review; provider failure remains retryable. Non-executable work stores
  no price, timeline or usable proposal.
- Controlled backfill is preview-first, bounded to 100, preserves source and
  old analysis snapshots, refreshes live status, and deduplicates proposal
  versions before any explicitly enabled replacement.
- Read-only production preview at `2026-09-03T08:03:00Z`: 55
  ACTIVE_BIDDABLE legacy rows; 55 with Score `<= 0`, 55 with null/zero Fit, 0
  empty prices, 0 empty timelines, 0 empty proposals, and 55 without the new
  approved evidence registry ID. No row was changed.
- Validation: 239/239 tests pass (200 protected baseline plus 39 Stage 4
  tests); compileall and production-like Python 3.12 import pass. The additive
  migration ran twice against isolated PostgreSQL 17 and all 33 Stage 4
  columns were present.
- Production remains unchanged on `main`
  `6b2d75d3b16e0b41531428926f9552f5ff6ab84b`, Railway deployment
  `43a219b0-14e9-4f94-a108-b1a12e20039a` (`SUCCESS / RUNNING`).
- Status: `READY_FOR_PROPOSAL_QUALITY_GATE_DEPLOY`.

## 2026-09-03 — Stage 4 issue #11 deployment review V2

- Every newly generated or rewritten canonical proposal now crosses one
  fail-closed service boundary: forced live refresh, candidate generation,
  deterministic validation, at most one repair, revalidation, content-bound
  versioning, persistence and version-aware delivery.
- Legacy direct `Order` generation is disabled. A `Response` is copyable only
  when its exact text hash, proposal version, source identity, quality result
  and live-validation timestamp all match under a locked final database read.
- Evidence and commercial clauses are application-owned. The model-owned body
  cannot introduce case/capability claims, prices, timelines or milestone
  logic; the final exact registry evidence and structured price/timeline block
  are inserted by the application and bound into `proposal_version`.
- Non-active backfill writes the first complete audit snapshot and hides active
  proposal fields in one transaction. UNKNOWN uses `live_status_pending` or
  `live_status_unknown_exhausted`, never the generic terminal state.
- Missing, malformed, provider-failed and real-zero Score/Fit survive storage
  and restart as distinct states (`—`, `INVALID`, `FAILED`, `0.0/10`).
- Validation: 276/276 tests pass, including 37 focused V2 behavioral and
  adversarial tests plus the protected 239-test suite. Compileall, Ruff F-rule
  checks, `git diff --check` and production-like Python 3.12 import pass.
- The additive migration ran twice on isolated PostgreSQL 17. All seven direct
  Response protection fields and six score-semantic fields were present;
  conflict preservation and atomic snapshot/hide behavior passed.
- Read-only production audit at `2026-09-03T09:45:05Z`: 73 total rows; 63
  ACTIVE_BIDDABLE legacy rows; all 63 have Score `<= 0`, null/zero Fit and no
  deployed approved-evidence field, while 0 have empty price, timeline or
  proposal. The V2 score/Response columns are correctly absent before deploy.
- Production remains unchanged on `main`
  `6b2d75d3b16e0b41531428926f9552f5ff6ab84b`, Railway deployment
  `43a219b0-14e9-4f94-a108-b1a12e20039a` (`SUCCESS / RUNNING`).
- Status: `READY_FOR_PROPOSAL_QUALITY_GATE_DEPLOY_V2`.

## 2026-09-03 — Stage 4 issue #11 deployment review V3

- Final proposal composition is fully application-owned after the model body:
  exact evidence and commercial clauses, milestone wording, timeline wording,
  `NO_DIRECT_CASE`, and `DEMO_REQUIRED` are approved constants for uk/ru/en/pl.
- Commercial terms now cross strict full-string allowlist parsers into typed
  `MoneyTerms` and `TimelineTerms`, persist as canonical JSON, and are rendered
  only from parsed values. Suffix injection, contradictory terms, malformed
  ranges, invalid values, contacts, and arbitrary tails fail closed.
- The exact localized final text is revalidated before its SHA-256 and
  `pqg-v3` version are computed. Save/reload must reproduce the same text,
  language, evidence, canonical terms, hash, version, and readiness decision.
- Multilingual first-person past-work/experience claims and generic URLs,
  domains, handles, phones, email obfuscation, social networks, messengers, and
  mixed-script bypasses are rejected across the body and model-owned fields.
- Unsolicited cards retain durable proposal-version dedup and stale-lease
  recovery. Explicit `/reply_job` retrieval always performs a fresh live check,
  may repeat the same validated text without a new version, and records each
  successful retrieval separately. Direct Response state becomes sent only
  after Telegram accepts the copy message.
- Validation: 302/302 tests pass, including 26 focused V3 tests. Compileall,
  Ruff F rules, diff check, and Python 3.12.14 production-like imports pass.
- Isolated PostgreSQL 17 accepted the additive migration twice. The three V3
  columns were present, and a persisted canonical proposal package passed an
  exact round-trip readiness check after reload.
- Current read-only production audit: 77 total rows, 67 ACTIVE_BIDDABLE; 67
  legacy zero Score, 67 null/zero Fit, 67 without deployed evidence fields,
  and one empty proposal. The V2/V3 columns remain absent, as expected before
  deployment. The transaction was read-only and rolled back.
- Production remains unchanged on `main`
  `6b2d75d3b16e0b41531428926f9552f5ff6ab84b`; Railway deployment
  `43a219b0-14e9-4f94-a108-b1a12e20039a` is `SUCCESS` with one of one replica
  running.
- Status: `READY_FOR_PROPOSAL_QUALITY_GATE_DEPLOY_V3`.

## 2026-09-03 — Stage 4 nullable Score/Fit metadata follow-up

- PR #12 was rolled back after normal scheduler traffic reached the official
  RSS `LIVE_STATUS_UNKNOWN` status-only path and attempted to persist
  `fit_score_valid=NULL` into a NOT NULL PostgreSQL column.
- The follow-up branch starts exactly from rollback `main` `01978e2b...`.
  Reverting the rollback produced reapply commit `a44641f`; its tree exactly
  matches approved Stage 4 source `468592c...` before the narrow hotfix.
- Commit `39beac1` centralizes Score/Fit normalization in the quality contract,
  applies it to analyzer and processor construction, and adds defensive
  normalization to insert/upsert/update/backfill and reload boundaries.
- The failing-before real PostgreSQL test reproduced
  `asyncpg.exceptions.NotNullViolationError` / SQLSTATE 23502 on
  `gmail_jobs.fit_score_valid`; the same route passes after the hotfix.
- Validation: the protected 302 tests remain passing; the full suite discovers
  310 tests (304 pass plus six opt-in PostgreSQL skips), and all eight focused
  tests pass with those six cases enabled against isolated PostgreSQL 17.
  Clean and existing-column migrations pass twice, as do scheduler, repeat,
  restart, insert, upsert, update, backfill, Python 3.12.14 import, compileall,
  Ruff F checks, diff check, localization, Telegram HTML/size, live-status, and
  cross-source dedup regressions.
- Production remains unchanged on rollback `main` `01978e2b...` and healthy
  Railway deployment `5af42416-7c91-4283-9c26-8282f0d6f4d4`.
- Status: `READY_FOR_PROPOSAL_QUALITY_GATE_NULLABLE_METADATA_HOTFIX_DEPLOY`.

## 2026-09-03 — Stage 5 issue #15 Release 5A deployment gate

- Stage 4 and its nullable-metadata correction are deployed and verified on
  production `main` `1f0bfb2ab95deb97cdde2eedd09fea7bceeecb05`, Railway
  deployment `765ba1da-4df3-4472-8ea8-b0d6fa5dad05` (`SUCCESS / RUNNING`).
- One restart-safe `sales_opportunities` row owns one concrete project/thread
  identity. Conversation turns, explicit owner confirmations, human fact
  requests and every state transition are append-only/auditable.
- Validated Stage 4 proposals create a version/hash-bound bid package. Only
  `/mark_bid_sent` records actual manually submitted terms; it never submits.
- Trusted private-message emails bypass score filtering, resolve by exact
  thread/project/reference evidence, preserve full context, classify intent,
  and produce a deterministic-validator-approved client-language draft.
- Missing dialogue context becomes `NEEDS_CONTEXT`; unavailable delivery facts
  become one `NEEDS_HUMAN_INPUT` request that `/answer_lead` resolves without
  deleting earlier drafts or history.
- `/mark_reply_sent` binds the exact reply version and SHA-256, records response
  latency and moves the opportunity to `WAITING_CLIENT`; it never sends.
- `/pipeline` and `/lead` expose current counts and compact auditable history.
  Working-window deferral is 08:00–21:00 Europe/Kyiv, with durable pending cards.
- Release 5B fields are present with `follow_up_status=DISABLED_5A`; no timed
  follow-up scheduler exists. Release 5C handoff is not implemented.
- Validation: 35 focused deterministic tests plus one real isolated PostgreSQL
  E2E; the full suite discovered 346 tests, passed 340 and skipped only six
  unrelated opt-in PostgreSQL cases.
  The entire additive migration list ran twice, and the restart retained the
  exact opportunity, confirmed turns and `WAITING_CLIENT` state.
- No production, Railway variable, OAuth, Telegram secret, Gmail, bid,
  message, contract, payment, backfill or replacement-card mutation occurred.
- Status: `READY_FOR_SALES_CLOSER_5A_DEPLOY`.

## 2026-09-03 — Stage 5A Draft PR #16 correction cycle V2

- Stage 4 is deployed and verified, issue #11 is completed, and the protected
  production baseline remains `main` `1f0bfb2ab95deb97cdde2eedd09fea7bceeecb05`
  with Railway deployment `765ba1da-4df3-4472-8ea8-b0d6fa5dad05`
  (`SUCCESS / RUNNING`).
- Write-state Telegram commands now resolve the actual sender by configured
  numeric user ID into `ADULT_OWNER`, `ARTEM`, `VADIM` or
  `READ_ONLY_MEMBER`. Missing role configuration and unauthorized actors fail
  closed; `/whoami`, `/pipeline`, `/lead` and notification cards remain
  read-only.
- Bid confirmation re-locks the opportunity and verifies the exact current
  proposal version, SHA-256, state and canonical Stage 4 commercial terms.
  Reply confirmation locks the opportunity and turns, rejects stale/hash-
  changed drafts, and stores the actual actor audit fields.
- Concurrent incoming turns use a PostgreSQL atomic sequence and a locked
  draft-publication boundary, so versions remain unique and only the draft for
  the latest incoming turn remains active.
- Human decisions are bound to request, source turn, intent and subject
  fingerprint. Application-owned clauses enforce technical, scope, price,
  timeline, availability, proof, access, selection and contract decisions.
- The explicit transition matrix prevents automatic reopening of terminal
  states. Selection readiness becomes `SELECTION_REVIEW`, contract evidence
  becomes `CONTRACT_REVIEW`, and no classification creates formal `SELECTED`.
- `/sync_lead_context` accepts one bounded plain-text owner/Artem copy, redacts
  credentials and reset material, rejects cross-opportunity identity, stores
  `UNKNOWN_DIRECTION`, and performs at most one validated generation.
- `/ack_lead` persists the actual actor. Each notified client turn owns one
  restart-safe five-minute working-window escalation; answer, sync or confirmed
  reply acknowledges it.
- A temporary 5A persistence failure cannot suppress a validated Stage 4 card:
  the card is labelled, sent once and leaves `sales_tracking_pending` for
  retry. Dialogue failure emits one sanitized no-reply fallback and leaves the
  Gmail event retryable.
- Validation: 68 focused 5A tests plus 34 parameterized subtests pass. The full
  ordered `unittest` suite runs 381 tests successfully, with nine opt-in
  PostgreSQL skips when no disposable URL is supplied. Three real isolated
  PostgreSQL 17 tests pass; the full additive migration list runs twice,
  concurrent reply versions are unique, terminal races fail closed, and the
  synthetic sales loop survives restart. Python 3.12.14 imports, compileall,
  changed-file Ruff F rules, Telegram HTML/size checks and diff checks pass.
- No merge, deploy, production migration/backfill, Railway variable, OAuth,
  Telegram secret, card replacement, bid, client message, contract or payment
  action occurred. Release 5B follow-ups and Release 5C handoff remain deferred.
- Status: `READY_FOR_SALES_CLOSER_5A_DEPLOY_V2`.

## 2026-09-03 — Stage 5A Draft PR #16 correction cycle V3

- Added a typed real-notification parser for Ukrainian, Russian, English and
  Polish wrappers. Sanitized HTML structure is authoritative, deterministic
  plain text is the fallback, and ambiguous message boundaries fail closed.
- Wrapper language and client-message language are persisted separately. Only
  the isolated client text reaches intent classification, generation, storage
  as message content and the copy-ready Telegram section.
- Freelancehunt support/onboarding notifications route to a bounded safe support
  card outside the sales repository, generator and funnel metrics.
- Exact resolution now supports a bounded active-state conversation-title
  lookup with Unicode/HTML/space/punctuation normalization and atomic thread
  binding. Zero, duplicate, terminal-only and thread-conflict candidates become
  `NEEDS_CONTEXT`; resolution basis is persisted on the incoming turn.
- Intent precedence now puts price before rejection, requires explicit terminal
  rejection phrases and distinguishes technical uses of “access/доступ” from an
  explicit grant/share/use of access or credentials.
- Explicit rejection persists a sanitized loss reason, disables follow-up,
  transitions to `LOST`, and produces no reply draft, AI call or mark command.
  Selection/contract copy is neutral and the validator blocks internal actor or
  automation language in any copy-ready reply.
- Partial Telegram role configuration is supported per command: either Artem or
  Vadim may answer independently; any configured permitted role may acknowledge,
  cancel or regenerate; owner or Artem may sync. Owner-only confirmations,
  unknown actors and duplicate IDs remain fail closed; `/whoami` is read-only.
- Five sanitized real-shape fixture files cover 19 parser/resolution/routing cases.
  Focused 5A V1/V2/V3 validation runs 98 tests successfully. The full suite runs
  412 tests successfully with ten expected opt-in PostgreSQL skips.
- Four isolated real PostgreSQL 17 tests pass after the full additive migration
  list runs twice, including restart/dedup, unique reply allocation, terminal
  races and concurrent exact-title thread binding. Python 3.12.14 imports,
  compileall, changed-file Ruff F rules, Telegram HTML/size and diff checks pass.
- No merge, deployment, production migration/backfill, variable, secret, OAuth,
  Gmail write, bid, message, contract or payment action occurred. Release 5B and
  Release 5C remain deferred.
- Status: `READY_FOR_SALES_CLOSER_5A_DEPLOY_V3`.

## 2026-09-04 — Stage 5A Draft PR #16 correction cycle V4

- Added all eight required `/profile` and `/profile/show` URL shapes and a
  real-form Ukrainian onboarding fixture using
  `/ua/profile/show/freelancehunt_nastasiia.html`. The staff slug alone routes
  the notification outside sales.
- Restarted support scans produce one mocked Telegram support card total and
  zero sales opportunities, AI calls, qualified increments, pending ACKs or
  escalations. An ordinary client's use of the word Freelancehunt remains a
  client message.
- Reordered intent classification to terminal rejection, formal
  contract/selection, genuine price objection, timeline, scope, then other
  intents. The four required rejection-plus-price cases close as `LOST` with
  no reply or follow-up; four real objections stay price objections and four
  neutral budget statements do not.
- Added additive orphan/tombstone columns and `MERGED` state. Exact project URL,
  project ID or reply/reference evidence combined with the orphan thread can
  invoke an atomic merge; sender, fuzzy title, similar text, contradictory
  identity, unchecked terms and unverified bid packages fail closed.
- Both in-memory and PostgreSQL repositories re-home turns, Gmail identities,
  ACK/escalation state, human requests and context sync rows; canonical
  proposal, submitted price and submitted timeline remain byte-for-byte
  unchanged. Both records retain audit transitions and the orphan is excluded
  from active counts.
- Focused V4 validation passes 12 tests plus 30 parameterized subtests. Five
  isolated PostgreSQL 17 tests pass after the entire additive migration list
  runs twice, including two concurrent merge transactions, restart, repeat
  import, future-thread routing and mocked one-card delivery.
- The full ordered suite passes 425 tests with six unrelated opt-in skips while
  the disposable sales PostgreSQL URL is enabled. Python 3.12.14 production
  import, compileall, changed-file Ruff F rules and `git diff --check` pass.
- Protected production remains on `main`
  `1f0bfb2ab95deb97cdde2eedd09fea7bceeecb05` and Railway deployment
  `765ba1da-4df3-4472-8ea8-b0d6fa5dad05`; no merge, deploy, production
  migration/backfill, variable, secret, OAuth, Gmail, Telegram or platform
  mutation occurred.
- Status: `READY_FOR_SALES_CLOSER_5A_DEPLOY_V4`.

## 2026-09-04 — GitHub issue #17 single shared Telegram operator hotfix (Draft PR #18)

- Created `fix/sales-closer-single-shared-operator-v1` from exact production
  `origin/main` `030128fa958c5243bfe3f1f28005813e2a8605a4`. Production Railway
  deployment `4664e3e1-ff90-458c-92cc-2d0f6ba05acd` remains `SUCCESS / RUNNING`.
- Added mutually exclusive `SEPARATE_ROLES` and `SINGLE_SHARED_OPERATOR`
  configuration. Shared mode accepts one positive numeric ID only when every
  legacy role ID is absent; unknown, missing, malformed, nonpositive,
  duplicate and conflicting configurations fail closed without echoing IDs.
- `/whoami` reports the operator mode, configured shared account and
  `SELF-ATTESTED ACTION ROLE` assurance without a full numeric ID. Generic
  shared operations use neutral `SHARED_OPERATOR`, not a fabricated person.
- Bid/reply confirmations use a read-only exact package preview and require
  exact `OWNER_CONFIRMS`. Stored audit binds actual Telegram ID, shared mode,
  self-attested adult-owner role, timestamps, phrase version, exact
  opportunity/version/hash and canonical submitted terms. No phrase means no
  confirmation and no `WAITING_CLIENT`/`BID_SUBMITTED` transition.
- Shared `/answer_lead` requires explicit `ARTEM` or `VADIM`. Stored audit keeps
  the self-attested fact source, request/source turn, subject fingerprint,
  structured answer code/text, actual Telegram ID and timestamps; duplicate
  source changes fail closed.
- Added restart-safe nullable audit columns to confirmations and human requests
  without destructive SQL. Existing separate-role rows and commands remain
  compatible.
- Added 42 shared-operator tests, including a complete synthetic proposal →
  owner confirmation → client reply → exact reply confirmation E2E. The full
  suite passes 467 tests on isolated PostgreSQL 17 with the migration list
  applied twice; six unrelated opt-in tests remain skipped. Python 3.12.14
  production imports, compileall, changed-file Ruff F checks and diff checks
  pass.
- No merge, deployment, Railway variable/secret, OAuth, production migration,
  real Telegram card, bid, client message, contract, Workspace or payment
  action occurred. Release 5B and Release 5C remain deferred.
- Status: `READY_FOR_SINGLE_SHARED_OPERATOR_DEPLOY`.

## 2026-09-04 — Issue #17 stale-reply precedence correction

- Continued the exact local reapply branch from
  `3345194d6026833eb0db5b3ecc9583cd03cd6e0a`; the approved shared-operator
  tree was unchanged before the narrow correction.
- Reproduced the pre-fix failure safely: confirmation of an old reply after a
  newer incoming turn returned the generic `CLIENT_REPLIED` state refusal
  instead of the latest-turn stale error and regeneration command. It created
  zero reply confirmations and performed zero platform writes.
- Added one deterministic preview/confirmation validation contract with stale
  precedence above generic state refusal. In-memory actual confirmation and
  PostgreSQL actual confirmation persist only `OUTGOING_SUPERSEDED` on stale;
  preview remains read-only.
- Regression coverage proves stale behavior across all six post-incoming
  states, shared and separate-role owner paths, preview/confirmation race,
  repeated refusal, current forbidden-state refusal and hash mismatch.
- Full discovery passes 474 tests with 12 opt-in PostgreSQL skips. Focused V2
  plus shared-operator coverage passes 81 tests. Six isolated PostgreSQL 17
  tests pass with the entire additive migration list applied twice and stale
  audit preserved across repository restart.
- Telegram HTML/size (12), Stage 4 quality (102), and Stage 5A V3/V4 parser and
  resolution (42) regressions pass. Python 3.12.14 import, compileall, Ruff F
  and `git diff --check` pass.
- Production remains unchanged on rollback `main`
  `6baaa462ef70e40d45e9c144e269eff71786f35b`, Railway deployment
  `480c3170-f354-4e4d-909d-c7a0e771e5d3`. No merge, deployment, variable,
  production migration, Telegram card or platform write occurred.
- Status: `READY_FOR_SINGLE_SHARED_OPERATOR_ZERO_OVERLAP_REDEPLOY_V2`.
