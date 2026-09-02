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
