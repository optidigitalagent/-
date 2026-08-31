---
name: freelancehunt-profile-operator
description: Use Playwright interactively to inspect, fill, save, and verify the one legitimate adult-owned Antonov Digital freelancer profile on Freelancehunt. Use only for one-time profile setup or an explicitly requested profile update. Do not use for bids, client messages, payments, verification bypasses, or the deactivated minor-owned account.
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
7. `docs/FREELANCEHUNT_BROWSER_PROFILE_AUTOMATION.md`
8. `ops/freelancehunt/profile_source.yaml`
9. `.codex/private/freelancehunt_owner.local.yaml`

If the private owner file is absent, stop before editing identity-bound fields and report exactly which local fields are missing. Never infer legal identity, age, phone, location, payment, or verification data.

## Account gate

Proceed only when all conditions are true:

- The browser is signed in to the sole legitimate Freelancehunt account owned by the genuine adult cofounder.
- The visible account name matches the adult owner's private source-of-truth file.
- The minor-owned account is not active in the browser session.
- The adult owner has personally completed login, password entry, CAPTCHA, 2FA, and any recovery confirmation.

If the visible profile is the minor founder's account, stop immediately without changing anything.

## Browser method

Use `$playwright-interactive` or the configured Playwright/Chrome DevTools MCP browser tool.

Prefer the existing authenticated browser session. Do not ask for, read, store, print, or commit passwords, recovery codes, cookies, session files, OTPs, or identity documents.

If login, CAPTCHA, OTP, or identity verification is required, pause and ask the adult account owner to take control. Resume only after the owner confirms the authenticated page is open.

## Operating phases

### Phase 1 — inspect before writing

1. Open the adult-owned public profile and every editable profile section.
2. Record the exact visible field labels, current values, validation rules, character limits, category options, and save behavior.
3. Take local screenshots before edits under `artifacts/private/freelancehunt-profile/before/`.
4. Build a local field map at `artifacts/private/freelancehunt-profile/field-map.md`.
5. Do not save changes during discovery unless the UI requires a reversible navigation state.

### Phase 2 — construct truthful values

Use sources in this order:

1. Adult identity and location fields: `.codex/private/freelancehunt_owner.local.yaml` only.
2. Brand, positioning, services, skills, languages, team description, and portfolio order: `ops/freelancehunt/profile_source.yaml`.
3. Case facts: `.codex/project_brain/PORTFOLIO_REGISTRY.md` plus direct evidence in the repository.
4. Current field names and limits: the live Freelancehunt UI.

Autonomously adapt wording to field limits and language, but preserve factual meaning.

Never invent:

- years of experience
- completed project counts
- revenue, conversion, ranking, or SEO results
- client testimonials
- employees or contractors
- certifications
- technologies not supported by project evidence
- adult-owner identity facts
- the minor founder as the account owner or operator

### Phase 3 — fill and save

Fill profile sections in this order:

1. Public professional title/headline.
2. About/summary.
3. Main and additional specializations.
4. Skills and technologies.
5. Languages and availability.
6. Rate/salary only when a truthful value is present in the private source file or the field supports a neutral negotiable value.
7. Employment/team description where the UI permits it.
8. Portfolio items only when each item has a factual case description, required images, a working link or demo, and clear evidence of Antonov Digital's role.

Save one section at a time. After each save:

- verify the success state
- reopen the section and confirm persisted values
- capture a local screenshot
- record the action in `artifacts/private/freelancehunt-profile/action-log.md`

Do not purchase Plus, activate paid options, submit a bid, send a client message, accept a contract, alter payment details, or start identity verification.

### Phase 4 — public-profile QA

1. Open the public profile in a fresh tab.
2. Check desktop and mobile-width rendering.
3. Verify the adult owner's identity is not contradicted by the Antonov Digital team wording.
4. Verify the minor founder appears only as a disclosed partner where relevant.
5. Check spelling, truncation, broken links, duplicate skills, unsupported claims, and empty required sections.
6. Capture final screenshots under `artifacts/private/freelancehunt-profile/after/`.
7. Write `artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md` containing:
   - account-owner name shown
   - sections completed
   - exact text entered
   - categories selected
   - portfolio items published or deferred
   - blockers requiring the adult owner
   - unresolved missing assets
   - final public profile URL

## Autonomy policy

Do not ask the user to approve ordinary copy, category selection, spelling, ordering, or reversible profile edits when the source-of-truth files are complete. Choose the strongest truthful version and proceed.

Stop only for:

- mismatch between the signed-in account and adult owner
- missing legal identity data required by a field
- login, CAPTCHA, OTP, 2FA, identity verification, or document upload
- payment or paid-plan action
- an irreversible contractual/platform action
- contradictory source data that would cause a false statement

## Completion condition

The task is complete when all safely editable profile fields are saved and verified, the public profile passes QA, and the local report clearly identifies any identity, verification, photo, or portfolio asset step that still requires the adult owner.