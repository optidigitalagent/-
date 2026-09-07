# Decision Log

Current amendment: explicit production rollout authorization, 2026-09-07.
Preserve prior work; current gate passed 552 full offline tests (0 failures,
errors or skips), including 283 targeted tests, isolated PG migrations/restart.
R1/R2/R3 and freshness corrections are accepted local mechanics. Publish one
complete checkpoint because splitting intertwined changes risks content loss.
Production preflight, zero-overlap rollout and activation verification still
must pass before tagging a freeze baseline. Prior phase prohibitions below
are historical; only the latest user's explicit scope supersedes them.
No controlled model calls; ledger 8/8 and reserve $0.03262905 unchanged.
Sales Brain begins offline only after successful production freeze checkpoint.
Live sales quality NOT_VALIDATED; live client cycle NOT_RUN; issues stay open.

## 2026-09-07 — Explicit local A→B scope: minimal 5B/5C

- Latest user instruction authorizes local follow-up/handoff, superseding the
  earlier sequencing prohibition only. Issue #15 reused; issue #20 stays open.
- Extend the existing SalesCloserService/PostgresSalesRepository/opportunity,
  Telegram role guards and APScheduler. One additive lifecycle_json column;
  no second CRM/service, no platform-send or financial capability.
- Timers recover from confirmed sends: 12h, then 24h after first actual follow-up,
  maximum two. Fresh owner-self-attested exact dialogue read (120s) is required
  before preparing/confirming use; read failure is not silence. Incoming insert
  atomically cancels drafts. Platform status events pause, never prove a win.
- Terms versions distinguish proposed/sent/client accepted/team confirmed.
  New incoming messages invalidate unreceived readiness; changed terms inherit
  no acceptance. Handoff requires selected-our-team, scope/price/payment/deadline,
  team capacity and explicit start evidence. Payment UNKNOWN/PROMISED/RESERVED/
  RECEIVED are separate; reserve is not received revenue. Receipt enters IN_DELIVERY.
- SYNTHETIC PostgreSQL mechanical A→B passes with service/repository restarts,
  real handlers/renderer/scheduler, and negative controls. No live-client cycle
  or model-quality improvement claimed. Local 5B/5C defaults off.
- Related 175-test run had four freshness subtest failures in one pre-existing
  import-timestamp fixture; isolated fresh-process rerun passes all 13 controls.
  Original failure retained, application freshness guard unchanged.
- Ledger unchanged at 8/8 and $0.03262905 reserve; model calls zero. No secrets,
  billing, production, Railway, OAuth, git publication or external messages.
- Next: review artifacts/private/a_to_b/a_to_b_review.zip with RESULT_RU.md.

## 2026-09-07 — Authorized continuation 7/8, stop at 8/8

- User accepted the prior delta for next validation and explicitly expanded the
  persistent call ceiling 6→8, same $1 total; all six prior entries/reserves kept.
- Only runner allowance constants/test expectations changed. After completion 7,
  the diagnostic repair allowlist gained its observed ask_source_perspective_mismatch
  code; the existing gate already classifies it as model-repairable. No analyzer,
  prompt, schema or accepted gate rewrite.
- Existing RSS/public path: 10 items, 1651774 absent; public status_code=0,
  no fresh full text. Used the authorized unchanged HISTORICAL_REAL_SNAPSHOT.
- Calls 7 and 8 (one targeted repair) returned identical raw ASK content. Gate
  rejects the invented client-reference dependency. Manual source/claim findings
  were attached to targeted repair, with no predetermined decision/scores/terms.
- MODEL_ON_REAL_SNAPSHOT=FAIL; LIVE_MODEL_E2E=NOT_RUN; CURRENT_BID_READY=NO.
  Ledger 8/8, reserves $0.03262905; new usage cost estimate $0.00237195.
- Stop model calls. No DB was started, no downstream 5A/delivery or production.
  Next action: review artifacts/private/issue20/validation_7_8/RESULT_RU.md
  and result_review.zip. IMPLEMENTED_WITH_VALIDATION_BLOCKERS remains.

## 2026-09-07 — Three false refusals, pure gate correction

- Bind ASK addressee to the leading action recipient, not later participant mentions.
- Bind known quantities to the same deliverable/attribute in the source clause;
  model absence_reason cannot overrule that source. No new schema or model judge.
- Replace arbitrary evidence word overlap with bounded approved capability aliases,
  including Telegram/телеграм. Explicit unrelated audio controls remain rejected;
  absence of vocabulary alone is not a mismatch. Registry claims are unchanged.
- 13 synthetic/mutation controls pass through full validate_analysis; 141 related
  tests, 140 pass and 1 expected PostgreSQL skip, including previous 16 targeted.
- No new model calls; ledger 6/6, reserve $0.02232975 unchanged. No PG rerun, API,
  secrets, production or git writes. IMPLEMENTED_WITH_VALIDATION_BLOCKERS remains.
- Review: artifacts/private/issue20/FALSE_REFUSAL_REPORT_RU.md and
  false_refusal_fix_20260907.zip (delta against review_fix_20260907.zip).

## 2026-09-07 — Independent-review corrections, offline only

- Add a compact ASK dependency to existing model_output_json: missing fact,
  owner, category, source/absence basis, necessity and estimate impact. No new DB
  columns, agent or model stage. Preserve TAKE/ASK/SKIP and genuine score states.
- Distinguish executor portfolio preference from mandatory client reference and
  start inputs. 'Will send privately' does not establish 'after selection'; old
  raw artifacts stay unchanged. No manufactured portfolio or free sample promise.
- Require a concrete action addressed to the fact owner, show it separately from
  the question, and reuse the 120-second freshness guard before client ASK display.
  Internal TEAM questions are explicitly not client messages or bid permission.
- Repair may change model evidence selection; validate new selection and use only
  registry text. One rejected response plus field diagnostics, no recursive copies.
- TAKE wire constrains finite 0..10 scores and nonempty offers; independent gate
  still blocks genuine zero readiness without changing zero to a positive value.
- Offline proof: 11 initial tests / 18 failures including subtests; final 16 new
  tests pass, related group 209 tests with 1 expected skip; isolated PostgreSQL
  ASK/TAKE roundtrip passes separately. Zero external connection attempts in the
  guarded offline run. No model calls, ledger/reserve unchanged at 6/6 / $0.02232975.
- IMPLEMENTED_WITH_VALIDATION_BLOCKERS. New model behavior/live E2E not validated.
  Next action is review of artifacts/private/issue20/REVIEW_FIX_REPORT_RU.md and
  review_fix_20260907.zip; a future live test needs separate explicit permission.

## 2026-09-07 — ASK contract correction; final authorized calls 5/6

- Replace conflicting forced offer examples with coherent TAKE/ASK/SKIP prompts
  and supported nested-anyOf strict SDK wire schema; retain flat storage adapter.
  ASK/SKIP never compose an offer. Source budget and genuine zero semantics remain.
- Repair receives model-correctable errors only; immutable source/live errors
  still block actionability. Unsupported claims are checked on ASK as well.
- After failing-before/passing-after tests, isolated PostgreSQL round-trip and
  diff review, use the user's new 4->6 authorization on historical real 1651774.
  Current public enrichment returned no usable full text (helper status 0).
- Actual calls 5/6 have no contradictory offer fields but fail truthful/useful
  content; manual source-perspective review was explicitly supplied to repair.
  No forced TAKE/score/price, no gate relaxation, no further model calls.
- Ledger 6/6, reserves $0.02232975; preserve all previous entries. New estimated
  cost $0.00223575. ACCOUNT_IDENTITY/BILLING=NOT_VERIFIED, key use EXPLICIT.
- MODEL_ON_REAL_SNAPSHOT=FAIL; LIVE_MODEL_E2E=NOT_RUN; CURRENT_BID_READY=NO;
  IMPLEMENTED_WITH_VALIDATION_BLOCKERS. Real-model downstream was not run.
  Next action is review of the sanitized package, not deployment or paid retries.
- Evidence: artifacts/private/issue20/ASK_CONTRACT_IMPLEMENTATION_REPORT.md.

## 2026-09-07 — Issue #20 historical-source model diagnostic

- Use explicitly authorized current key with existing analyzer/prompts/schema,
  provider/budget and unchanged gate on exact historical source. No /me or billing
  requirement, current-source claim, database, delivery or 5A creation.
- Two completions consumed step permission: ledger 4/6. Repair did not correct
  ASK price/timeline/proposal conflicts. No further model request authorized.
- Preserve original replies/report; separate offline replay corrects only the
  harness repair-count metadata, not readiness status or errors.
- MODEL_ON_REAL_SNAPSHOT=FAIL, LIVE_MODEL_E2E=NOT_RUN, CURRENT_BID_READY=NO.
  IMPLEMENTED_WITH_VALIDATION_BLOCKERS. Next work is offline diagnosis from saved
  output, not another paid retry or weakened readiness requirements.

## 2026-09-06 — Issue #20 explicit current-key authorization supersedes /me gate

- The user explicitly authorizes the current local key despite the prior `/me`
  HTTP 404. Preserve `ACCOUNT_IDENTITY=NOT_VERIFIED`; do not require a screenshot
  or another identity request. The executed prior command used the literal
  `https://api.openai.com/v1/me`, without a duplicated `/v1`.
- The current authorized step starts at persistent 2/6 and ends at no more than
  4/6: one real analyzer request and one targeted validation repair only after
  completion. Existing reservations stay intact; API/transport failure closes
  the step. Official-host-only transport, TLS verification and no redirects or
  retries are enforced by the runner.
- Fresh 1651774 RSS evidence is active, but public full-text retrieval is
  protected (HTTP 403). Three plausible alternatives within a ten-project RSS
  sample also remain PARTIAL/UNKNOWN after enrichment. No model was called.
- Result: `LIVE_MODEL_E2E=NOT_RUN`, ledger 2/6, reserves `$0.00522225`, status
  `IMPLEMENTED_WITH_VALIDATION_BLOCKERS`. Do not reuse the previous full scope
  as current. Existing explicit key-use authorization persists.

## 2026-08-31 — Brand and delivery team

- Use the public brand Antonov Digital.
- Public structure: two founders plus developer Vadim.
- A genuine adult account owner is presented truthfully as the physical-person profile owner who handles platform communication, agreements, contracts and payments.
- Artem Antonov is presented as co-founder and partner responsible for management, marketing, acquisition, communication preparation and selected development.
- Vadim is presented as the developer responsible for the main technical implementation when team roles are described.
- Remove unsupported claims about a four-person OptiDigital team or an account owner being the primary developer when that is not true.

## 2026-08-31 — Service discovery

- Do not set an initial priority among AI agents, automation, Telegram bots, CRM, websites, MVPs, AI content, audio, SEO/GEO, data/monitoring and other executable online services.
- Test demand using real market data from channels the team is legally and operationally allowed to use.
- Broad coverage does not permit claiming skills or delivery capacity that cannot be supported by evidence or a realistic plan.

## 2026-08-31 — Pricing

- No fixed minimum project value.
- Small and discounted projects are allowed for cash, reputation or strategic reasons when scope is controlled.
- Public preference is project or milestone pricing.
- Do not invent an hourly rate; use a negotiable option when the platform supports it.

## 2026-08-31 — Availability

- Public status: fully available for work.
- Founder availability for intervention: approximately 08:00–21:00 Europe/Kyiv.
- Peak work capacity may reach 18 hours, but customer deadlines must use conservative capacity.

## 2026-08-31 — Languages and sales assets

- Use Ukrainian as the primary Freelancehunt profile language.
- Ukrainian, Russian and English are supported for written communication and calls.
- Polish is supported for written communication with AI assistance; do not claim unsupported oral fluency.
- English calls and short video walkthroughs are allowed.
- Antonov Digital has no approved logo yet; the logo is not a blocker for sales-material preparation.

## 2026-08-31 — Email and alert roles

- Only a mailbox tied to a legally eligible and approved acquisition channel may feed the revenue agent.
- An eligible adult-owned Freelancehunt mailbox may later connect through minimum-permission Gmail OAuth for permitted notification ingestion.
- A direct-sales mailbox remains a separate lawful channel.
- Exact mailbox addresses are not committed while the repository is public.

## 2026-08-31 — Freelancehunt account integrity

- Reject duplicate, fake and decoy accounts.
- Reject deliberately weak staged bids.
- Internally compare proposal variants and send only the best legitimate version through an approved channel.
- Do not share or transfer account ownership or credentials.
- Gmail ingestion does not authorize automatic bids, platform messages or profile actions.

## 2026-08-31 — Freelancehunt support outcome: initial minor-account ruling

- Artem registered an account using truthful personal data and immediately contacted support before operational use.
- Support stated that the account cannot be used for any purpose before age 18, including passive project alerts and market analysis.
- Support instructed Artem to deactivate the account and contact support after turning 18 to restore access.

## 2026-08-31 — Freelancehunt support outcome: adult-owner route

- Support confirmed that a genuine adult physical person may independently register and operate their own account.
- Support stated that Artem may be identified in client correspondence as a partner because the legal account owner is a legally capable adult.
- Route status is `APPROVED_ADULT_PHYSICAL_PERSON_PROFILE_WITH_DISCLOSED_ANTONOV_DIGITAL_TEAM`.
- The adult owner controls the account, passes verification, submits bids, conducts correspondence, performs Workspace actions, contracts and receives payment.
- Artem does not access or impersonate the adult account owner.
- Antonov Digital may be disclosed as the delivery team.
- Client-facing descriptions of the team, roles and delivery responsibility remain truthful.
- This approval does not override platform restrictions on automatic bidding, mass messaging or credential sharing.

## 2026-08-31 — Prepared profile-content decisions

- Primary profile language: Ukrainian.
- Public availability: fully available.
- Pricing: project or milestone, negotiated from scope.
- All factual portfolio cases, client names, screenshots, links, technologies and truthful role descriptions are approved for use when evidence and assets are ready.
- Codex may choose the strongest truthful portfolio order.
- Prepared assets include four language descriptions, specialization strategy, twenty skills, notifications and nine portfolio cards.

## 2026-08-31 — Codex browser profile setup

- Preferred surface: Codex in the ChatGPT desktop app with a connected browser.
- Use the built-in browser/computer-use capability when available; Playwright or Chrome DevTools MCP is an acceptable fallback.
- Browser automation is a profile-setup convenience, not an automated bidding or messaging system.
- A genuine account owner personally handles login, CAPTCHA, OTP, 2FA, identity verification, document upload, payment configuration and contractual acceptance.
- Codex may autonomously inspect, write, save and verify ordinary reversible fields using approved source material.
- Portfolio items are published only when factual evidence and required assets exist.

## 2026-08-31 — Canonical repository

- Preserve the history of `optidigitalagent/-` as the canonical repository.
- Target name: `antonov-digital-freelance-revenue-engine`.
- Target visibility: private.
- Project-brain work uses branch `setup/project-brain-v1` and a draft pull request.
- No production code, merge or deployment is part of the project-brain stage.

## 2026-08-31 — Repository privacy

- The current repository is public.
- Do not commit literal mailbox addresses, secrets, client-private data or recovery information until visibility is private.
- Public-safe aliases and environment-variable names are used in documentation.

## 2026-08-31 — Stage 0 Draft PR

- Draft PR #1 was opened from `setup/project-brain-v1` into `main`.
- Existing production code and Railway deployment were not changed.
- The previous Gmail/Telegram agent instructions were preserved in `docs/LEGACY_AGENT_ARCHITECTURE.md`.

## 2026-09-01 — Minor identity verification did not create eligibility

- Artem personally completed identity verification using his own identity and birth date `2011-01-28`.
- No bid, agreement, project work or payment followed the verification.
- Freelancehunt support clarified in writing that identity verification confirms the person and submitted data only; it does not override the age rule.
- Support confirmed that Artem cannot submit bids, enter agreements, perform projects or receive payment through Freelancehunt before age 18.
- Earliest eligibility date is `2029-01-28`.
- Support stated that no additional sanctions will apply because no work-related platform action followed verification.
- Support instructed that the account must be deactivated until age 18.
- Final minor-account state is `VERIFIED_IDENTITY_BUT_DEACTIVATION_REQUIRED_UNTIL_2029-01-28`.

## 2026-09-01 — Revenue-preservation decision after channel closure

- Treat the minor-owned Freelancehunt profile as unusable, even though commercial profile work reached a high degree of completion.
- Preserve the profile copy, specialization list, skill list, notification plan, portfolio cards and proposal logic as reusable sales assets.
- Do not connect the minor account or its notifications to Gmail, Telegram, CRM or Railway.
- Do not repurpose or transfer the minor account to an adult.
- Continue revenue acquisition through:
  1. a separately created genuine adult-owned Freelancehunt profile under the support-approved model; and/or
  2. direct sales and other age-eligible channels.
- Track commercial-asset readiness separately from channel eligibility so a polished but ineligible profile is never mistaken for a revenue-ready channel.

## 2026-09-02 — Stage 2 local deployment gate

- Extend the existing Gmail/PostgreSQL/Telegram implementation; do not replace
  the production architecture.
- Treat all required Freelancehunt event classes as first-class persisted
  events, with Ukrainian, Russian, English and Polish subject coverage.
- Use a 60-second polling interval, narrow platform-sender query, PostgreSQL
  message-ID/stable-key dedup, restart-safe retry, `max_instances=1` and
  scheduler coalescing for the first revenue cycle.
- Private client messages, status changes and workspace/contract events bypass
  project-score filtering. Project score applies only to project candidates.
- There is no minimum budget and no preselected preferred service lane.
- Persist the full safe source context and the first generated proposal;
  `/reply_job` returns the saved draft first and rewrites only on explicit
  request without discarding the specification.
- Security/account events are redacted before analysis or Telegram; sensitive
  links are never forwarded.
- Gmail OAuth must force account selection and verify `users.getProfile`
  against the exact runtime secret before writing a token. Mismatch attempts
  fail closed and leave no token file.
- The approved operational mailbox source was corrected during local OAuth
  validation. Public repository evidence uses only the verified masked alias
  `ur***@gmail.com`; the exact address remains a runtime secret.
- Local read-only validation and exactly one synthetic Telegram TEST card
  passed. No Gmail mutation, Freelancehunt action, Railway variable change,
  deploy or merge was performed.
- Draft PR #2 is the deployment candidate. Production activation requires a
  new explicit authorization.

## 2026-09-02 — Freelancehunt live-status hotfix gate

- A Freelancehunt project is a qualified revenue opportunity only when its
  public live page positively proves that bidding is available.
- The canonical statuses are `ACTIVE_BIDDABLE`, `BLOCKED_RULE_VIOLATION`,
  `CLOSED`, `EXECUTOR_SELECTED`, `DELETED_OR_UNAVAILABLE` and
  `LIVE_STATUS_UNKNOWN`. Negative evidence takes precedence over bid-CTA
  evidence.
- Use an ordinary anonymous HTTP read first and a fresh cookie-free Playwright
  context only as fallback. Never log in, solve CAPTCHA or perform a platform
  action during this check.
- Absence of a known closure banner is not active proof. Only an enabled bid
  form/action or explicit enabled multilingual bid CTA may yield
  `ACTIVE_BIDDABLE`; ambiguous or failed checks fail closed as
  `LIVE_STATUS_UNKNOWN`.
- `LIVE_STATUS_UNKNOWN` remains non-qualified and uses at most three retries
  with bounded exponential backoff. Non-active diagnostics are deduplicated
  independently from status transitions so a project produces at most one.
- Apply the same checker before AI/scoring and Telegram delivery in both Gmail
  single/digest ingestion and the legacy direct Freelancehunt parser. Direct
  proposal/rewrite/send commands also require stored `ACTIVE_BIDDABLE` plus
  `biddable=true`.
- Persist live evidence through additive columns only. Existing rows and any
  historical proposal text are retained, but a non-biddable row cannot display
  or use that proposal.
- The hotfix remains isolated on `fix/freelancehunt-live-status-guard` until a
  separate merge/deploy authorization; production variables and the running
  deployment remain unchanged.

## 2026-09-02 — Live-status deployment review V2

- Every direct and Gmail proposal display, generation, rewrite or manual-copy
  action uses the same asynchronous guard. A saved `ACTIVE_BIDDABLE` result is
  reusable for at most 60 seconds; otherwise it is refreshed and persisted in a
  separate short transaction after network work.
- `LIVE_STATUS_UNKNOWN` keeps its canonical external value. After three
  automatic attempts, the durable processing state becomes
  `live_status_unknown_exhausted`; automatic reads stop, the item can settle,
  and `/recheck_live` remains an explicit read-only recovery path.
- One scan shares an anonymous HTTP client and one cookie-free Chromium
  browser/context, limits concurrency to four (bounded to 3–5), caps HTTP at
  five seconds and browser work at eight seconds, deduplicates URLs, and has an
  80-second overall budget (hard-clamped to 90 seconds).
- When public HTML is protected, membership in Freelancehunt's official
  anonymous `projects.rss` open-project feed is sufficient positive active
  evidence. Absence from that feed is not terminal and never proves closed.
  Page-level terminal evidence still takes precedence.
- A live-status diagnostic is marked delivered only after Telegram confirms a
  successful send. Failed delivery remains `live_status_notice_pending` and is
  retried independently with processed-key dedup after success.
- Railway/Linux read-only proof used no login, cookies, CAPTCHA, bid, message,
  secret or variable change: the exact public control project 1650987 remained
  non-biddable/UNKNOWN, while a current feed item was positively
  `ACTIVE_BIDDABLE`. Production remains on the unchanged known-good main
  deployment until separate authorization.

## 2026-09-02 — Stage 3 instant discovery architecture

- Issue #7 is completed and deployed as `DEPLOYED_LIVE_STATUS_HOTFIX_V2` on
  production `main` `da58c7bb4a6c3a4565f3590f83f7301b2e7b41c5`, Railway
  deployment `c9a3cebe-36b7-4697-9ec0-bd01dbc0c77a` (`SUCCESS / RUNNING`).
- Issue #9 is the active Stage 3 work item. Its implementation remains isolated
  on `feature/freelancehunt-instant-discovery-v1` until separate deployment
  authorization.
- Use the official anonymous `projects.rss` feed as the primary fresh-project
  discovery source and poll it every 60 seconds with `max_instances=1` and
  `coalesce=true`.
- Derive one durable 64-hex stable key from the canonical numeric Freelancehunt
  project ID for RSS, Gmail and the legacy parser. PostgreSQL remains the
  restart-safe source of truth.
- Reuse, never relax, the V2 live-status guard. Only `ACTIVE_BIDDABLE` can reach
  price, timeline, proposal and the manual-owner Telegram action card.
- Remove Freelancehunt from the old hourly automatic parser only after the new
  scheduler path is present; retain other platforms and the manual read-only
  Freelancehunt diagnostic path.
- Apply no old keyword exclusion or minimum-budget rejection to Freelancehunt.
  Let the commercial analyzer classify truthful broad online lanes and persist
  executable state, service lane, fit, effort, risk and strategic mode.
- Measure publication-to-first-seen and publication-to-Telegram latency. The
  normal path target is at most 120 seconds.
- Never automate a bid or client message. The adult owner performs the final
  platform action manually.

## 2026-09-03 — Stage 4 proposal-quality gate

- Treat `ACTIVE_BIDDABLE` as necessary but insufficient for a proposal-ready
  card. Proposal actions additionally require `executable=yes` and persisted
  `QUALITY_VALID` or `QUALITY_REPAIRED`.
- Preserve `score` and `fit_score` as independent finite 0–10 values. Missing,
  malformed and non-finite values remain invalid rather than becoming `0.0`.
- Run deterministic validation after the live-status guard and before
  qualification or Telegram delivery. Permit at most one AI repair using the
  original source context and exact validation errors, then validate again.
- Restrict evidence to the approved Project Brain registry and persist its
  stable ID separately from approved factual wording and source-grounded
  project evidence.
- Fail closed across saved proposal display, view, rewrite, direct reply and
  manual-copy/send paths. A quality recheck refreshes live status first and
  never submits a bid or client message.
- Backfill is preview-first, bounded to 100 rows, audit-preserving and
  proposal-version deduplicated. Production rows remain untouched until a
  separately authorized deployment and backfill execution.
- Protected production remains `main`
  `6b2d75d3b16e0b41531428926f9552f5ff6ab84b`, Railway deployment
  `43a219b0-14e9-4f94-a108-b1a12e20039a` (`SUCCESS / RUNNING`). Instant
  discovery is deployed and verified; Telegram channel migration is complete;
  issue #11 is the current work item.

## 2026-09-03 — Proposal-quality gate V3 correction contract

- Treat the model's commercial strings as untrusted input. Accept only a full
  allowlist parse into canonical `MoneyTerms` and `TimelineTerms`; compose the
  final price, milestone, and timeline text from those typed values.
- Keep every explanatory evidence/commercial sentence application-owned and
  localized for uk/ru/en/pl. Runtime AI translation cannot authorize final
  delivery wording.
- Revalidate the complete localized proposal after composition, then compute
  the exact content hash, then the `pqg-v3` version. No mutable proposal field
  may change after version calculation.
- Fail closed on multilingual model-authored past-work claims and on generic
  off-platform contacts or links in every model-owned text field.
- Keep unsolicited delivery exactly-once per proposal version through the
  existing durable claim/lease contract. Treat explicit owner retrieval as a
  repeatable read action with a forced fresh live check and separate telemetry;
  it must neither generate a new version nor consume unsolicited dedup state.
- A direct Response remains draft/retryable until Telegram confirms the exact
  copy message. Re-lock and revalidate the same text/version before persisting
  the sent state.

## 2026-09-03 — Nullable Score/Fit metadata hotfix contract

- Keep the PostgreSQL `score_valid`, `fit_score_valid`, `score_state`, and
  `fit_score_state` columns NOT NULL. Nullable application metadata is a
  boundary defect, not a reason to weaken the schema.
- Use one `normalize_score_metadata` contract for both Score and Fit from model
  parsing through processor construction and repository persistence.
- Preserve `MISSING`, `INVALID`, `FAILED`, genuine `0.0`, and finite 0–10
  values as distinct semantics. A numeric `0.0` compatibility value never
  overrides its validity/state metadata.
- Normalize before digest/RSS and single-job construction, insert, conflict
  upsert, update, retry/restart, live recheck, and quality backfill writes.
- Treat an otherwise proposal-ready record with unavailable Score/Fit metadata
  as `QUALITY_MANUAL_REVIEW`, clear the active commercial/proposal package, and
  emit only sanitized metadata-contract telemetry.
- Keep issue #11 open. Merge, Railway deployment, production migration,
  backfill, replacement cards, variables, secrets, bids, and client messages
  require separate authorization.

## 2026-09-03 — Stage 5A sales-closer contract

- One sales opportunity is keyed by exact project ID, thread ID, safe project
  URL or proven reply-reference mapping. Client name is only a last,
  non-authoritative hint and may resolve only one active candidate.
- Every opportunity state change records timestamp, source, previous/new state,
  reason and one allowed actor: `system`, `adult_owner` or `Artem`.
- A bid is `BID_SUBMITTED` only after the adult owner confirms actual price,
  timeline and the exact validated proposal version. A reply is sent only after
  the adult owner confirms the exact reply version/hash. Telegram commands
  record these actions but never perform them on Freelancehunt.
- Trusted `CLIENT_PRIVATE_MESSAGE` events use a dedicated, score-bypassing
  dialogue path. Gmail message ID and canonical turn identity both deduplicate;
  conflicting identifiers fail closed into a separate `NEEDS_CONTEXT` record.
- AI sees the complete source description, exact submitted proposal and terms,
  confirmed dialogue, constraints, decisions, open questions, human facts,
  approved evidence and current state. Unconfirmed drafts are never promises.
- Deterministic validation is authoritative and permits at most one bounded AI
  repair. Unsupported commitments, mismatched commercial terms, invented
  evidence, contacts, language mismatch, unrelated text, contradictions,
  missing context and free scope expansion are blocked.
- Release 5A persists the Release 5B timing fields with follow-ups disabled.
  No follow-up scheduler or Release 5C delivery handoff is part of this change.
- Production merge/deploy, variables, OAuth, Telegram secrets, backfill,
  replacement cards, bids, messages, contracts and payments remain separately
  authorized stop-gate actions.

## 2026-09-03 — Stage 5A correction cycle V2 contract

- Authorize state writes by the actual Telegram sender's configured numeric ID,
  never by the command name or username. Owner-only confirmation commands and
  Artem/Vadim fact decisions remain separate; missing settings fail closed.
- Treat the current Stage 4 proposal version, content SHA-256 and canonical
  `MoneyTerms`/`TimelineTerms` as one indivisible bid-confirmation package.
- Allocate reply versions atomically and publish drafts through a locked latest-
  incoming check. A stale draft becomes `OUTGOING_SUPERSEDED` and cannot create
  a confirmation or `WAITING_CLIENT` transition.
- Scope every human answer to one request, incoming turn, intent and subject
  fingerprint. Render commitments from structured application-owned decisions;
  do not reuse broad opportunity-wide capability facts.
- Reuse Stage 4's public contact and unsupported-claim guards and its exact
  localized evidence registry. Access, selection and contract replies are
  fixed fail-closed text and perform no platform action.
- Keep `LOST`, `CLOSED`, formal `SELECTED` and `HANDOFF_READY` terminal. Client
  readiness and contract signals stop at review states in Release 5A.
- Context imports are bounded, credential-redacted, actor-bound and stored as
  `OWNER_COPIED_THREAD` with `UNKNOWN_DIRECTION` unless separately confirmed.
- Use the existing minute scheduler for one persistent five-minute
  unacknowledged-turn reminder during 08:00–21:00 Europe/Kyiv. This is an owner
  alert, not a Release 5B client follow-up.
- Preserve Stage 4 delivery when 5A storage is temporarily unavailable and keep
  both opportunity persistence and sanitized dialogue handling retryable.
- Release 5B client follow-ups and Release 5C delivery handoff remain deferred;
  production changes require separate explicit authorization.

## 2026-09-03 — Stage 5A correction cycle V3 contract

- Parse real Freelancehunt private-message notifications through one dedicated,
  fail-closed contract. Store only the isolated client-authored message as the
  incoming turn; wrapper, profile, CTA, footer, tracking and sensitive links
  are routing metadata rather than client content.
- Detect wrapper language from the notification marker and client language only
  from the isolated message. Platform support/onboarding messages never create
  sales opportunities, drafts or funnel transitions.
- Resolve by exact authoritative identifiers first. When project ID is absent,
  permit one exact normalized conversation-title match among active states and
  atomically bind its thread ID/URL. No fuzzy title match is permitted; zero,
  multiple or conflicting matches require context.
- Classify intent only from client-authored text. Price evidence has precedence;
  rejection requires an explicit terminal phrase; access requires explicit
  grant/share/use semantics plus a resource, credential, role or permission.
- An explicit terminal rejection records the incoming turn and safe loss reason,
  disables follow-up, moves to `LOST`, and creates neither a reply draft nor a
  send-confirmation instruction.
- Copy-ready text must not expose bots, AI agents, internal automation or owner-
  review narration. Selection and contract responses use neutral client-facing
  Freelancehunt Workspace wording without accepting terms or payment.
- Multi-role Telegram commands require any actually configured permitted role,
  not every possible role setting. Owner-only confirmations remain owner-only;
  unknown actors and duplicate numeric role IDs fail closed.
- Schema changes remain additive and restart-safe. Release 5B, Release 5C and all
  production/platform mutations remain outside this correction cycle.

## 2026-09-04 — Stage 5A correction cycle V4 contract

- Treat all eight required `/profile` and `/profile/show` URL forms as profile
  identities. A normalized `freelancehunt_` slug is authoritative platform
  staff evidence and routes outside sales without relying on subject wording.
- Classify an explicit terminal rejection before contract/selection and price.
  Price requires both a price/budget term and objection, reduction,
  counteroffer or negotiation semantics; a neutral budget statement is not an
  objection.
- Mark title-resolution fallback records explicitly as orphans. Merge one only
  from `NEEDS_CONTEXT` into a distinct active canonical opportunity whose
  submitted proposal hash and canonical actual terms are complete and valid.
- Require the orphan's exact thread ID plus an exact canonical project ID, URL
  or reply/reference ID. Names, fuzzy titles and similar text are never merge
  evidence; conflicting combinations fail closed.
- Lock both PostgreSQL opportunities in deterministic order and revalidate the
  full contract in one transaction. Re-home turns and their Gmail, ACK and
  escalation fields, human requests and context sync rows; never copy orphan
  proposal or commercial fields.
- Keep both histories. Tombstone the source as `MERGED` with target, timestamp,
  actor and hashed identity evidence, add audit transitions on both records,
  exclude the tombstone from active pipeline counts and bind all future thread
  traffic to the canonical opportunity.
- Owner-copied context is content-addressed on the canonical opportunity, so a
  repeated import or restart reuses the stored result and does not generate a
  second reply or card. No platform write capability is added.
- Status: `READY_FOR_SALES_CLOSER_5A_DEPLOY_V4`.

## 2026-09-04 — Stage 5A single shared Telegram operator hotfix contract

- Support exactly one active Telegram operator mode: `SEPARATE_ROLES` or
  `SINGLE_SHARED_OPERATOR`. Preserve the existing separate-role behavior and
  fail closed on an unknown mode, missing/nonpositive shared ID, duplicate role
  IDs, or any shared/separate configuration conflict.
- A shared Telegram ID proves only the configured account. It never proves
  which physical person typed a command. Persist the actual Telegram user ID,
  operator mode, `SHARED_ACCOUNT_SELF_ATTESTED`, claimed action/source role,
  attestation version and timestamps.
- `/mark_bid_sent` and `/mark_reply_sent` first produce a non-mutating exact
  version/hash/terms preview. Only exact `OWNER_CONFIRMS` records the adult
  owner's personally completed Freelancehunt action; the application performs
  no platform action.
- `/answer_lead` in shared mode requires explicit `ARTEM` or `VADIM` source and
  preserves the request, source turn, subject fingerprint, structured decision
  and self-attested source audit. Unknown or contradictory sources fail closed.
- The configured shared account may acknowledge, sync/cancel context and
  regenerate using the neutral `SHARED_OPERATOR` audit role. Unknown Telegram
  IDs remain read-only. `/whoami` never prints the full numeric ID.
- Schema changes are additive and restart-safe. Existing version/hash,
  commercial-term, truthfulness/contact/evidence, stale-reply, resolution,
  dedup, escalation and support-routing protections remain unchanged.
- Release 5B and Release 5C remain deferred. Merge, deployment, Railway
  variables/secrets, production migrations/backfills and all real platform
  actions require separate authorization.
- Status: `READY_FOR_SINGLE_SHARED_OPERATOR_DEPLOY`.

## 2026-09-04 — Shared-operator stale-reply precedence correction

- Use one side-effect-free deterministic reply-validation result for preview,
  in-memory confirmation and PostgreSQL confirmation. Its exhaustive outcomes
  are `CURRENT_AND_ALLOWED`, `STALE`, `CURRENT_BUT_STATE_FORBIDDEN`,
  `HASH_MISMATCH` and `VERSION_NOT_FOUND`.
- Resolve the exact requested version, latest incoming turn and latest active
  draft before checking opportunity state. An older draft always returns
  `StaleReplyError` with the latest incoming-turn ID and exact
  `/regenerate_lead <opportunity_id>` action, including when the opportunity is
  currently `CLIENT_REPLIED`, `NEEDS_HUMAN_INPUT`, `NEEDS_CONTEXT`,
  `NEGOTIATING`, `SELECTION_REVIEW` or `CONTRACT_REVIEW`.
- Preview uses the same validation decision but never mutates storage. Actual
  confirmation persists only the stale draft's `OUTGOING_SUPERSEDED` marker;
  it creates no owner confirmation, does not acknowledge the latest incoming
  turn and does not move the opportunity to `WAITING_CLIENT`.
- PostgreSQL locks the opportunity and turns, commits the stale marker alone,
  and raises the canonical stale error. Current drafts retain the existing
  state, hash, version, role and `OWNER_CONFIRMS` protections.
- The Telegram handler returns a bounded actionable stale message without a
  traceback or SQL details. No Freelancehunt write capability is added.
- Merge, deployment, Railway variable changes and production migrations remain
  outside this correction authorization.

## 2026-09-05 — Issue #20 decision-first revenue card contract

- Treat the normalized public candidate as source authority for project ID,
  URL, budget/currency and completeness. A model may analyze those facts but
  may not replace them. An RSS preview is always `PARTIAL`; character count is
  not evidence that the full project specification was observed.
- Require OpenAI Structured Outputs (`json_schema`, strict) and local Pydantic
  validation. Persist provider outcome, actual model, finish reason and token
  usage. Refusal, truncated/empty content, schema failure and API failure are
  technical states and never commercial SKIP decisions.
- Make `TAKE`, `ASK` and `SKIP` explicit durable decisions. TAKE alone may
  contain canonical price/timeline/proposal and create a Stage 5A opportunity;
  ASK contains exactly one source-fact question and no proposal; SKIP contains
  a source-grounded mismatch reason and no proposal. Normal cards do not expose
  quality error codes; `/job_diagnostics` is admin-only.
- Apply a deterministic no-model SKIP only when the public source itself both
  requires a logo specialist and explicitly excludes AI. The decision says
  that compliance with the mandatory delivery mode is unconfirmed; it does
  not invent a claim that the team has no designer. Low budget alone remains
  forbidden as a rejection reason.
- Retry Gmail metadata/full reads only for 500/502/503/504, at most three
  attempts with exponential jitter and no event-loop blocking. Persist each
  exhausted message ID in PostgreSQL, retry it after restart without losing
  neighboring messages, resolve it on success, and emit one alert only from
  the third failed scan onward. Authentication, permission and rate-limit
  categories fail immediately and remain distinct.
- The issue #20 live runner must load only `.env.issue20.local`, set SDK retries
  to zero, fix the model to `gpt-4o-mini`, use an ignored persistent six-call/
  $1 ledger, isolated PostgreSQL and a fake Telegram transport. A rerun never
  resets its allowance.
- The first and only model attempt reached OpenAI but returned `RateLimitError`;
  API usage was not returned and no candidate/proposal/5A row or Telegram
  message was produced. Further paid attempts stopped. Status is
  `IMPLEMENTED_WITH_VALIDATION_BLOCKERS`, not deployment-ready.

## 2026-09-05 — Issue #20 offline diagnostics, scope and Gmail correction

- Preserve API failures through one allowlisted diagnostic envelope and write a
  machine-readable failure report before PostgreSQL reload. Unknown usage and
  cost remain `NOT_RETURNED` / `UNKNOWN`; reserved upper bound is separate.
  Never infer the historical 429 cause from synthetic fixtures.
- Bind every future result to HEAD, dirty state and SHA-256 of the runner and
  relevant source files. Never hash or report env/artifact content as source.
- Require auditable scope enrichment for RSS `FULL`. Treat main-text
  completeness, materials availability and fixed-term sufficiency separately.
  Scope-relevant missing materials produce deterministic `ASK`; execution-input
  materials may permit `TAKE` only with an application-owned start condition.
- Classify Gmail 403 from structured `error.errors[].reason`; missing,
  conflicting or unknown reasons remain `UNKNOWN`. Resolve durable fetch
  pending only after a stored job/processed handoff, not immediately on fetch.
- Restrict the future runner to the dedicated loopback issue20e2e database,
  explicit disabled external delivery and a private verified current-candidate
  scope snapshot. Keep model `gpt-4o-mini`, SDK retries 0 and the existing 6/$1
  ledger contract.
- Offline acceptance does not establish the exact cause of two historical
  production `INVALID` states and is not live-model E2E. Status remains
  `IMPLEMENTED_WITH_VALIDATION_BLOCKERS`.

## 2026-09-06 — Issue #20 current RSS candidate and live failure boundary

- Use project `1651774` from the current official RSS sample as the bounded
  real candidate. Its verified public scope is three simple photo-based Canva
  product reels, up to 16 seconds, with product/brand assets supplied after
  selection. Treat the source budget as `NOT_SPECIFIED` and do not claim a
  directly matching production case.
- Mark the private snapshot's scope/material judgment as manual. Production
  enrichment may identity-bind a fetched public page, but protected/ambiguous
  pages fail closed and runtime does not autonomously prove fixed-term
  sufficiency.
- Enrich new RSS candidates before analyzer dispatch through the existing
  discovery pipeline; never promote an RSS excerpt, protected page or missing
  attachment to verified `FULL`.
- Apply the existing additive database migrations in the isolated runner
  before repository use. Preserve a new provider failure report and do not
  replace it with a generic missing-row error.
- The one authorized new request returned HTTP 429,
  `credit_balance_exhausted` / `insufficient_quota`, with no completion or
  usage. Stop all further step calls and repairs. This classifies only the new
  attempt; the first historical 429 remains `UNKNOWN`.
- Persistent ledger is 2/6, actual API-derived cost is `UNKNOWN`, billing is
  `NOT_VERIFIED`, and reserved total is `$0.00522225`. No financial setting may
  be changed by the agent.
- `LIVE_MODEL_E2E=FAIL`; overall status stays
  `IMPLEMENTED_WITH_VALIDATION_BLOCKERS`.
## 2026-09-07 — R1–R3 review delta (local mechanics only)

- First receipt must atomically recheck current prerequisites, current terms
  version and packet/proposal hashes, not rely on a legacy valid flag.
  Loss of a required reserve invalidates unreceived readiness. NONE does not
  require advance payment. Preserve earlier packets/receipts/evidence.
- Persist internal follow-up notification state in the same opportunity JSON;
  reuse existing scheduler/notifier/bot/chat and Kyiv office hours. A locked
  claim rechecks cancellation/current draft before transport. Mark delivered
  only after transport success; keep pending/recovery lease across restart.
  Do not claim external network exactly-once semantics.
- Literal followup_sent card action requests reference as an explicit second
  step. Never infer the owner's checked source or remove owner/version/hash guards.
- No new model calls, ledger 8/8 and reserve $0.03262905 unchanged. Default
  SALES_LIFECYCLE_ENABLED remains false; no production activation.
- Preserve historical 175-test FAIL and failed live responses #7/#8.
  Overall status remains IMPLEMENTED_WITH_VALIDATION_BLOCKERS.
- Review only the new artifacts/private/a_to_b_r1_r3/a_to_b_r1_r3_delta.zip;
  original a_to_b_review.zip is retained byte-for-byte.
## 2026-09-07 — narrow R2 restart/freshness continuation

- Independent review accepted R1/R3; fix only the reproduced R2 renewal gap.
- Reconcile eligibility uses the actual freshness result, not the stale status
  string while awaiting the next tick. Fresh checks cancel pending sync notices.
- Expired checks bind sync identity to persisted dialogue event_id (legacy
  fallback: at). Repeated ticks/restarts reuse that identity. Original initial
  sync and draft identities, working hours, leases, cancellation and delivery
  acknowledgement remain unchanged. No new service, scheduler or table.
- Exact registered-callback scenario fails before (1 instead of 2 cards) and
  passes after, including two expired generations and timely draft. Nine
  targeted R1/R2/R3 tests PASS; no full-suite rerun or historic FAIL relabeling.
- MECHANICAL_A_TO_B_CANDIDATE_FOR_FREEZE=YES only within this mechanics scope;
  LIVE_SALES_QUALITY=NOT_VALIDATED; LIVE_CLIENT_CYCLE=NOT_RUN.
- Model calls 0; ledger 8/8/reserve $0.03262905 and both prior review archives
  preserved. Production/default enablement and external delivery unchanged.
- Next action: separately scoped sales-quality evaluation using saved material.
  Evidence: artifacts/private/a_to_b_r2_freshness/RESULT_RU.md.
