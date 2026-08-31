---
name: freelancehunt-profile-operator
description: Use the Codex built-in browser/computer-use capability, or Playwright/Chrome DevTools MCP as a fallback, to inspect, fill, save, and verify the one legitimate adult-owned Antonov Digital freelancer profile on Freelancehunt. Use only for one-time profile setup or an explicitly requested reversible profile update. Do not use for bids, client messages, payments, verification bypasses, or the deactivated minor-owned account.
---

# Freelancehunt Profile Operator

## Objective

Complete the truthful adult-owned Antonov Digital freelancer profile with minimal manual work while protecting the account and preserving a verifiable record of what was entered.

This skill is for browser-based profile setup only. It does not authorize automated bidding, platform messaging, contracts, payments, identity verification, or continuous account operation.

## Required reading

Before opening the browser, read:

1. `AGENTS.md`
2. `.codex/project_brain/PROJECT_BRAIN.md`
3. `.codex/project_brain/BUSINESS_RULES.md`
4. `.codex/project_brain/PLATFORM_RULES.md`
5. `.codex/project_brain/PORTFOLIO_REGISTRY.md`
6. `docs/FREELANCEHUNT_ACCOUNT_STRATEGY.md`
7. `docs/START_PROFILE_SETUP_NO_TERMINAL.md`
8. `ops/freelancehunt/profile_source.yaml`
9. `ops/freelancehunt/OWNER_INPUT.txt` when present
10. `.codex/private/freelancehunt_owner.local.yaml` when present

If only `OWNER_INPUT.txt` exists, create the private YAML locally from `ops/freelancehunt/freelancehunt_owner.local.example.yaml`. Never commit the private YAML or owner input.

If required identity values are absent, stop before editing identity-bound fields and report exactly which local fields are missing. Never infer legal identity, age, phone, location, payment, or verification data.

## Account gate

Proceed only when all conditions are true:

- The browser is signed in to the sole legitimate Freelancehunt account owned by the genuine adult founder.
- The visible account name matches the adult owner's local source-of-truth data.
- The deactivated minor-owned account is not active in the browser session.
- The adult owner has personally completed login, password entry, CAPTCHA, 2FA, and recovery confirmation.

If the visible profile is the minor founder's account, stop immediately without changing anything.

## Browser method

Use this preference order:

1. Codex built-in browser/computer-use capability in the ChatGPT desktop app.
2. `$playwright-interactive`.
3. Configured Playwright or Chrome DevTools MCP browser tool.

Prefer the existing authenticated browser session. Do not ask for, read, store, print, export, or commit passwords, recovery codes, cookies, session files, OTPs, or identity documents.

If login, CAPTCHA, OTP, 2FA, phone verification, or identity verification is required, pause and ask the adult account owner to take control. Resume only after the owner confirms the authenticated page is open.

## Truthful public model

Use `ops/freelancehunt/profile_source.yaml` as the source of truth:

- adult owner: founder, profile owner, client/operational responsibility
- Artem Antonov: co-founder and partner; management, marketing, acquisition, communication, selected development
- Vadim: developer responsible for the main technical implementation
- primary profile language: Ukrainian
- pricing: project or milestone; do not invent an hourly rate
- availability: fully available
- Polish: written AI-assisted communication only unless real oral proficiency is separately verified

Do not describe the adult owner as the primary developer.

## Operating phases

### Phase 1 — inspect before writing

1. Open the adult-owned public profile and every editable profile section.
2. Record exact visible field labels, current values, validation rules, character limits, category options, and save behavior.
3. Take local screenshots before edits under `artifacts/private/freelancehunt-profile/before/`.
4. Build `artifacts/private/freelancehunt-profile/field-map.md`.
5. Do not save during discovery unless the UI requires a reversible navigation state.

### Phase 2 — construct truthful values

Use sources in this order:

1. Adult identity, phone, location and photo: local private owner data only.
2. Brand, positioning, services, skills, languages, team description, pricing model and portfolio order: `ops/freelancehunt/profile_source.yaml`.
3. Case facts: `.codex/project_brain/PORTFOLIO_REGISTRY.md` plus direct evidence in the repository.
4. Current field names and limits: the live Freelancehunt UI.

Autonomously adapt wording to field limits and language while preserving factual meaning.

Never invent:

- years of experience
- completed-project counts
- revenue, conversion, ranking, or SEO results
- client testimonials
- employees, founders, or contractors beyond the approved team model
- certifications
- technologies not supported by evidence
- adult-owner identity facts
- the minor founder as the account owner or operator
- Polish oral fluency

### Phase 3 — fill and save

Fill in this order:

1. Public professional title/headline.
2. About/summary.
3. Main and additional specializations.
4. Skills and technologies.
5. Languages and availability.
6. Project/milestone pricing or negotiable option; do not invent hourly or salary values.
7. Team description where the UI permits it.
8. Real adult-owner photo from the approved local path.
9. Portfolio items only when each item has factual copy, required images, a working link or demo when claimed, and clear evidence of Antonov Digital's role.

Save one section at a time. After each save:

- verify success
- reopen the section and confirm persisted values
- capture a local screenshot
- record the action in `artifacts/private/freelancehunt-profile/action-log.md`

Do not purchase Plus, activate paid options, submit a bid, send a client message, accept a contract, alter payment details, or start identity verification.

### Phase 4 — public-profile QA

1. Open the public profile in a fresh tab.
2. Check desktop and mobile-width rendering.
3. Verify the adult owner's identity is not contradicted by team wording.
4. Verify Artem appears only as the disclosed co-founder/partner and Vadim only in the approved developer role.
5. Check spelling, truncation, broken links, duplicate skills, unsupported claims, and empty required sections.
6. Capture final screenshots under `artifacts/private/freelancehunt-profile/after/`.
7. Write `artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md` containing:
   - account-owner name shown
   - sections completed
   - exact text entered
   - categories selected
   - languages and pricing presentation
   - portfolio items published or deferred
   - blockers requiring the adult owner
   - unresolved missing assets
   - final public profile URL

## Autonomy policy

Do not ask the user to approve ordinary copy, category selection, spelling, ordering, or reversible profile edits when sources are complete. Choose the strongest truthful version and proceed.

Stop only for:

- mismatch between signed-in account and adult owner
- missing legal identity data required by a field
- login, CAPTCHA, OTP, 2FA, phone or identity verification, or document upload
- payment or paid-plan action
- an irreversible contractual/platform action
- contradictory source data that would cause a false statement

## Completion condition

The task is complete when all safely editable profile fields are saved and verified, the public profile passes QA, and the local report identifies any identity, verification, photo, or portfolio asset step that still requires the adult owner.
