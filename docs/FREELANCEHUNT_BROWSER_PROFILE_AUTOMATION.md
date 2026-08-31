# Freelancehunt Browser Profile Automation

## Purpose

Use Codex in the ChatGPT desktop app to inspect and complete the one legitimate adult-owned Freelancehunt profile for Antonov Digital without using a Freelancehunt write API.

This is a one-time profile-setup workflow. It is not a bidding bot, message bot, verification bypass, or shared-account workflow.

## Operating model

```text
Adult owner registers and authenticates the legitimate account
        ↓
Codex reads repository instructions and local owner input
        ↓
Codex inspects the live profile in the built-in browser
        ↓
Codex fills and verifies ordinary reversible profile fields
        ↓
Adult owner handles CAPTCHA, OTP, identity, documents and payments
        ↓
Codex checks the public profile and writes a local report
```

The adult founder remains the real account owner, login controller, verification subject, platform communicator, contracting party, and payment recipient. Artem may be truthfully disclosed as co-founder/partner. Vadim may be disclosed as the developer responsible for the main technical implementation. Neither role changes who owns or operates the account.

## Recommended surface

Use Codex in the ChatGPT desktop app with the repository folder open. The desktop app is preferred because it works with local project files, automatically discovers `AGENTS.md` and repository skills from the opened folder, and can use the built-in browser/computer-use capability.

Fallback browser methods:

- `$playwright-interactive`
- configured Playwright MCP
- configured Chrome DevTools MCP

The no-terminal instructions are in:

```text
docs/START_PROFILE_SETUP_NO_TERMINAL.md
```

## Local source files

Public business source:

```text
ops/freelancehunt/profile_source.yaml
```

Simple local owner input:

```text
ops/freelancehunt/OWNER_INPUT.txt
```

Private structured owner file:

```text
.codex/private/freelancehunt_owner.local.yaml
```

Both local owner files are ignored by Git. They must never contain passwords, OTPs, recovery codes, cookies, passport files or banking data.

## Required owner input

Only four local values remain mandatory before full autonomous profile completion:

```text
FULL_LEGAL_NAME=
PUBLIC_DISPLAY_NAME=
ADULT_PHONE=
PROFILE_PHOTO_PATH=
```

All other business decisions are already stored in `profile_source.yaml`:

- adult owner: founder and operational/account responsibility
- Artem: co-founder/partner; management, marketing, acquisition, communication and selected development
- Vadim: main technical implementation
- Ukrainian primary profile language
- Ukrainian, Russian and English communication; Polish written with AI assistance only
- fully available
- project/milestone pricing
- broad truthful service coverage
- all factual portfolio cases allowed when evidence and assets are ready
- no logo required for launch

## Authentication boundary

The adult owner personally enters:

- email/login
- password
- CAPTCHA
- phone code
- OTP/2FA
- recovery confirmation

The adult owner also personally handles:

- phone verification
- passport/identity verification
- document upload
- financial/payment configuration
- legal or contractual acceptance

Codex does not ask for, read, store, print, export or commit those secrets or documents.

## Execution prompt

Use the complete prompt in:

```text
ops/freelancehunt/CODEX_PROFILE_PROMPT_RU.txt
```

The prompt instructs Codex to:

1. verify the adult-owned account identity
2. inspect all live fields and limits before editing
3. create the private local YAML when only `OWNER_INPUT.txt` exists
4. fill and save each reversible section autonomously
5. use Ukrainian as the main profile language
6. present the approved team roles truthfully
7. select broad but truthful specializations
8. use project/milestone pricing without inventing an hourly rate
9. publish only evidence-backed portfolio cases
10. verify the public profile at desktop and mobile widths
11. produce a full local report and before/after screenshots

## Expected local output

```text
artifacts/private/freelancehunt-profile/field-map.md
artifacts/private/freelancehunt-profile/action-log.md
artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md
artifacts/private/freelancehunt-profile/before/
artifacts/private/freelancehunt-profile/after/
```

## Prohibited actions

- using the deactivated minor-owned account
- sharing or storing the adult owner's password
- exporting cookies or session state into the repository
- creating a duplicate freelancer account
- buying Plus without a separate commercial decision
- submitting bids or platform messages
- changing payment details
- identity verification by AI
- inventing projects, metrics, experience, education, certifications, language fluency or testimonials
- publishing portfolio items without evidence and approved assets

## Completion definition

The run is successful when the adult-owned public profile is coherent, truthful, complete across all safely editable sections, and every deferred identity, verification, photo or portfolio step is listed with an exact missing-input reason in the local report.
