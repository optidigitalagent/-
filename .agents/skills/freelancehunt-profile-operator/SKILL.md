---
name: freelancehunt-profile-operator
description: Use the Codex built-in browser/computer-use capability, or Playwright/Chrome DevTools MCP as a fallback, to inspect, fill, save, and verify the one legitimate adult-owned Antonov Digital freelancer profile on Freelancehunt. Use only for one-time profile setup or an explicitly requested reversible profile update. Do not use for bids, client messages, payments, verification bypasses, account transfer, or a minor-owned account.
---

# Freelancehunt Profile Operator

## Objective

Complete the truthful adult-owned Antonov Digital freelancer profile with minimal manual work while protecting the account and preserving a verifiable record of what was entered.

This skill is for browser-based profile setup only. It does not authorize automated bidding, platform messaging, contracts, payments, identity verification, account transfer, or continuous account operation.

## Required reading

Before opening the browser, read:

1. `AGENTS.md`
2. `.codex/project_brain/PROJECT_BRAIN.md`
3. `.codex/project_brain/BUSINESS_RULES.md`
4. `.codex/project_brain/PLATFORM_RULES.md`
5. `.codex/project_brain/PORTFOLIO_REGISTRY.md`
6. `docs/FREELANCEHUNT_ACCOUNT_STRATEGY.md`
7. `docs/FREELANCEHUNT_LIVE_PROFILE_AUDIT_2026-09-01.md`
8. `docs/CODEX_EXECUTION_REPORTING_STANDARD.md`
9. `ops/freelancehunt/profile_source.yaml`

Local files such as `OWNER_INPUT.txt`, `.codex/private/freelancehunt_owner.local.yaml`, or `owner-photo.jpg` are optional aids, not launch blockers for ordinary non-identity profile fields.

Never infer, invent, replace, or transfer legal identity, date of birth, phone ownership, payment ownership, verification data, or account ownership.

## Account ownership gate

Before editing, distinguish two cases.

### Case A — legitimate adult-owned account

Proceed only when the genuine adult owner personally confirms that:

- this exact account was created for and belongs to them;
- they control the login, mailbox, phone, verification, contracts, and payments;
- the account is not being transferred from another person;
- they personally completed login, CAPTCHA, OTP/2FA, and recovery confirmation in the browser connected to Codex.

The live profile must show the adult owner’s real identity before identity-dependent publication or verification. The adult owner may manually correct their own editable identity fields when the account has always belonged to them.

### Case B — account belongs to Artem, another minor, or another person

Stop immediately with `ACCOUNT_OWNER_MISMATCH`.

Do not rename, re-photo, re-verify, or otherwise repurpose the account for an adult. Do not continue through a transferred or shared login. The genuine adult owner must use their own separately created account.

A public nickname by itself is not enough to decide ownership. Use the adult owner’s explicit confirmation plus the actual account history and control model. When ownership is uncertain, stop and request a one-line answer from the adult owner.

## Authentication gate

Codex must operate in the browser session it can actually control.

If the user is logged in only in an unrelated normal Chrome window, report `AUTH_REQUIRED_IN_CONNECTED_BROWSER` rather than repeating file checks.

The adult owner personally completes:

- login and password entry;
- CAPTCHA;
- email/SMS OTP;
- 2FA;
- phone confirmation;
- identity verification and document upload;
- payment or legal confirmations.

Codex must not ask for, read, store, export, print, or commit passwords, recovery codes, cookies, session files, OTPs, or identity documents.

## Browser method

Use this preference order:

1. Codex built-in browser/computer-use capability in the ChatGPT desktop app.
2. `$playwright-interactive`.
3. Configured Playwright or Chrome DevTools MCP browser tool.

Open Freelancehunt inside the selected connected browser and let the adult owner authenticate there. Do not assume access to a separate Chrome session.

## Truthful public model

Use `ops/freelancehunt/profile_source.yaml` as the business-copy source of truth:

- adult owner: real profile owner and client/operational responsibility;
- Artem Antonov: co-founder and partner; management, marketing, acquisition, communication, selected development;
- Vadim: developer responsible for the main technical implementation when participating;
- primary profile language: Ukrainian;
- pricing: project or milestone; do not invent an hourly rate;
- availability: fully available;
- Polish: written AI-assisted communication only unless real oral proficiency is separately verified.

Do not describe the adult owner as the primary developer unless that is factually true and separately approved.

## Operating phases

### Phase 1 — inspect before writing

1. Open the authenticated adult-owned public profile and every editable profile section.
2. Record exact visible field labels, current values, validation rules, character limits, category options, and save behavior.
3. Capture before screenshots when the browser tool supports them.
4. Build `artifacts/private/freelancehunt-profile/field-map.md` when local file access is available.
5. Do not change identity, verification, phone, payment, or legal-status fields.

### Phase 2 — construct truthful values

Use sources in this order:

1. Live adult-owned account identity as manually confirmed and corrected by the adult owner.
2. Brand, positioning, services, skills, languages, team description, pricing model, and portfolio order: `ops/freelancehunt/profile_source.yaml`.
3. Case facts: `.codex/project_brain/PORTFOLIO_REGISTRY.md` plus direct evidence in the repository.
4. Current field names and limits: the live Freelancehunt UI.

Autonomously adapt wording to field limits and language while preserving factual meaning.

Never invent:

- years of experience;
- completed-project counts;
- revenue, conversion, ranking, or SEO results;
- client testimonials;
- employees, founders, or contractors beyond the approved team model;
- certifications;
- technologies not supported by evidence;
- adult-owner identity facts;
- the minor founder as the account owner or operator;
- Polish oral fluency.

### Phase 3 — fill and save ordinary reversible fields

Fill in this order:

1. Public professional title/headline when the field exists.
2. About/summary in Ukrainian and other approved languages.
3. Main and additional specializations.
4. Skills and technologies.
5. Languages and availability.
6. Project/milestone pricing or negotiable option; do not invent hourly or salary values.
7. Team description where the UI permits it.
8. Portfolio items only when each item has factual copy, required images, a working link or demo when claimed, and clear evidence of Antonov Digital’s role.

A missing local `owner-photo.jpg` is not a blocker for the fields above. Leave the photo unchanged and list `adult owner must upload/confirm real current photo` in the report. Codex may upload a photo only when the adult owner has supplied and approved a real current photo in the connected local workspace.

Save one section at a time. After each save:

- verify success;
- reopen the section and confirm persisted values;
- capture a screenshot when available;
- record the action in `artifacts/private/freelancehunt-profile/action-log.md` when local file access is available.

Do not purchase Plus, activate paid options, submit a bid, send a client message, accept a contract, alter payment details, or start identity verification.

### Phase 4 — public-profile QA

1. Open the public profile in a fresh tab.
2. Check desktop and mobile-width rendering when supported.
3. Verify the adult owner’s identity is not contradicted by team wording.
4. Verify Artem appears only as the disclosed co-founder/partner and Vadim only in the approved developer role.
5. Check spelling, truncation, broken links, duplicate skills, unsupported claims, and empty required sections.
6. Capture final screenshots when available.
7. Write `artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md` when local file access is available, including:
   - account-owner name shown;
   - ownership confirmation status;
   - authentication status;
   - sections completed;
   - exact text entered;
   - categories selected;
   - languages and pricing presentation;
   - portfolio items published or deferred;
   - blockers requiring the adult owner;
   - final public profile URL.

## Autonomy policy

Do not ask the user to approve ordinary copy, category selection, spelling, ordering, or reversible profile edits when sources are complete. Choose the strongest truthful version and proceed.

Do not repeatedly block on absent local identity files or a missing local photo when the task is limited to non-identity fields.

Stop only for:

- confirmed or unresolved account-owner mismatch;
- no authenticated session in the browser Codex can control;
- login, CAPTCHA, OTP, 2FA, phone or identity verification, or document upload;
- payment or paid-plan action;
- an irreversible contractual/platform action;
- contradictory source data that would cause a false statement.

Use these precise blocker codes:

- `ACCOUNT_OWNER_MISMATCH`
- `ACCOUNT_OWNERSHIP_UNCONFIRMED`
- `AUTH_REQUIRED_IN_CONNECTED_BROWSER`
- `ADULT_OWNER_ACTION_REQUIRED`

## Mandatory execution report

Never return only a status code, a changed-file count, or a short blocker sentence.

Every response must follow `docs/CODEX_EXECUTION_REPORTING_STANDARD.md` and include:

1. Objective and revenue milestone.
2. Outcome: `COMPLETED`, `PARTIALLY_COMPLETED`, `BLOCKED`, or `FAILED_VALIDATION`.
3. Actions actually performed.
4. Evidence: file paths, URL or `URL_NOT_AVAILABLE`, visible account name, exact sections and screenshots when available.
5. Source-of-truth comparison using:
   `expected -> observed -> required correction`.
6. Exact files and browser fields changed.
7. Exact fields deliberately left unchanged.
8. Every blocker, continued work, and the minimum adult-owner action.
9. Readiness change and commercial impact.
10. Exactly one next action.

Before returning `OWNER_SOURCE_READY`, `LIVE_SETUP_READY`, or any other `*_READY` status:

- re-read all changed files from disk;
- search the relevant workspace for stale owner names, placeholders, and contradictory roles;
- verify that the owner is the genuine adult owner and not Artem Antonov or a temporary nickname;
- do not mark the source ready merely because contradiction counters equal zero;
- include the actual expected and observed owner names in the report, without exposing sensitive private data beyond the approved public display name.

For browser work, the report must additionally include:

- connected-browser status;
- authenticated status;
- current URL or `URL_NOT_AVAILABLE`;
- visible public name;
- owner-name match result;
- sections saved and persistence verification;
- specializations and skills selected;
- languages and pricing presentation;
- portfolio items published/deferred;
- notifications enabled;
- final public profile URL;
- remaining adult-owner actions.

## Completion condition

The task is complete when all safely editable ordinary profile fields are saved and verified, the public profile passes QA, and any remaining identity, verification, photo, payment, or portfolio-asset actions are listed clearly for the adult owner.
