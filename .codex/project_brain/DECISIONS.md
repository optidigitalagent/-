# Decision Log

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
