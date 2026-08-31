# Decision Log

## 2026-08-31 — Brand and delivery team

- Use the public brand Antonov Digital.
- Public structure: two founders plus developer Vadim.
- The genuine adult account owner is presented truthfully as the founder who owns the profile and handles client/operational responsibility, agreements, contracts and payments.
- Artem Antonov is presented as co-founder and partner responsible for management, marketing, acquisition, communication and selected development.
- Vadim is presented as the developer responsible for the main technical implementation when team roles are described.
- Remove unsupported claims about a four-person OptiDigital team or the adult owner being the primary developer.

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
- The adult owner has a real profile photo available.
- Antonov Digital has no approved logo yet; the logo is not a blocker for profile launch.

## 2026-08-31 — Email and alert roles

- Use one adult-owned operational mailbox for the sole active Freelancehunt account and its notification stream.
- The same mailbox may later be connected to the revenue agent through minimum-permission Gmail OAuth for permitted notification ingestion.
- Do not use an alert-mirror or forwarding mailbox in the current architecture.
- The mailbox formerly tied to the minor founder's account is excluded from the current flow.
- The previously used `newartem855` mailbox is excluded from this project.
- A separate direct-sales mailbox remains optional and unassigned.
- Exact mailbox addresses are not committed while the repository is public.

## 2026-08-31 — Freelancehunt account integrity

- Use one genuine adult-owned freelancer account.
- Reject duplicate, fake and decoy accounts.
- Reject deliberately weak staged bids.
- Internally compare proposal variants and send only the best legitimate version through an approved channel.
- Do not share the adult owner's login with the minor founder.
- Gmail ingestion does not authorize automatic bids, platform messages or profile actions.

## 2026-08-31 — Freelancehunt support outcome: minor account

- The 15-year-old founder registered an account using truthful personal data and immediately contacted support before operational use.
- Support stated that the account cannot be used for any purpose before age 18, including passive project alerts and market analysis.
- Support instructed the founder to deactivate the account and contact support after turning 18 to restore access.
- User later confirmed that this account is deactivated and not used.
- Account status is `DEACTIVATED_UNTIL_18`.

## 2026-08-31 — Freelancehunt support outcome: adult-owner route

- Support confirmed that a genuine adult person may independently register and operate their own account.
- Support stated that Artem may be identified in client correspondence as a partner because the legal account owner is a legally capable adult.
- Route status is `APPROVED_ADULT_OWNER_WITH_DISCLOSED_PARTNER`.
- The adult owner controls the account, passes verification, submits bids, conducts correspondence, contracts and receives payment.
- Artem does not access or impersonate the adult account owner.
- Client-facing descriptions of the team, roles and delivery responsibility remain truthful.
- This approval does not override platform restrictions on automatic bidding, mass messaging or credential sharing.

## 2026-08-31 — Adult-owned profile content decisions

- The adult-owned account has not yet been registered.
- Adult owner location: Kyiv, Ukraine.
- Owner public role: founder of Antonov Digital; do not describe the owner as the primary developer.
- Artem's role and Vadim's technical role are described in `ops/freelancehunt/profile_source.yaml`.
- Profile language: Ukrainian.
- Public availability: fully available.
- Pricing: project or milestone, negotiated from scope.
- All existing portfolio cases, client names, screenshots, links, technologies and truthful role descriptions are approved for use when evidence and assets are ready.
- Codex may choose the strongest truthful portfolio order.

## 2026-08-31 — Codex browser profile setup

- Preferred surface: Codex in the ChatGPT desktop app with the project folder open.
- Use the built-in browser/computer-use capability when available; Playwright or Chrome DevTools MCP is an acceptable fallback.
- This is a one-time profile setup workflow, not an automated bidding or messaging system.
- The adult owner personally handles login, CAPTCHA, OTP, 2FA, identity verification, document upload, payment configuration and contractual acceptance.
- Codex may autonomously inspect, write, save and verify ordinary reversible profile fields using the repository source of truth.
- Legal identity fields come only from `.codex/private/freelancehunt_owner.local.yaml` and must never be inferred or committed.
- Public brand copy comes from `ops/freelancehunt/profile_source.yaml`.
- Portfolio items are published only when factual evidence and required assets exist.
- The repository skill is `.agents/skills/freelancehunt-profile-operator/SKILL.md`.

## 2026-08-31 — Canonical repository

- Preserve the history of `optidigitalagent/-` as the canonical repository.
- Target name: `antonov-digital-freelance-revenue-engine`.
- Target visibility: private.
- Project-brain work uses branch `setup/project-brain-v1` and a draft pull request.
- No production code, merge or deployment is part of Stage 0.

## 2026-08-31 — Repository privacy

- The current repository is public.
- Do not commit literal mailbox addresses, secrets, client-private data or recovery information until visibility is private.
- Public-safe aliases and environment-variable names are used in documentation.

## 2026-08-31 — Stage 0 Draft PR

- Draft PR #1 was opened from `setup/project-brain-v1` into `main`.
- The change is documentation and project-governance only.
- Existing production code and Railway deployment were not changed.
- The previous Gmail/Telegram agent instructions were preserved in `docs/LEGACY_AGENT_ARCHITECTURE.md`.
