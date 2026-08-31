# Freelancehunt Browser Profile Automation

## Purpose

Use Codex with an interactive browser to inspect and complete the one legitimate adult-owned Freelancehunt profile for Antonov Digital without using a Freelancehunt write API.

This is a one-time profile-setup workflow. It is not a bidding bot, message bot, verification bypass, or shared-account workflow.

## Operating model

```text
Adult owner authenticates the legitimate account
        ↓
Codex inspects the live profile UI through Playwright
        ↓
Codex fills reversible profile fields from project sources
        ↓
Adult owner handles CAPTCHA, OTP, identity verification and documents
        ↓
Codex verifies the public profile and writes a local report
```

The adult cofounder remains the real account owner, login controller, verification subject, platform communicator, contracting party, and payment recipient. Artem may be truthfully disclosed as an Antonov Digital partner but does not impersonate the adult owner.

## Recommended surface

Use the Codex desktop app opened at the repository root. The IDE extension or CLI can also be used when the same project and MCP configuration are available.

The interactive browser requirement is satisfied by either:

- the built-in/installed `$playwright-interactive` skill; or
- a configured Playwright or Chrome DevTools MCP server.

## One-time local setup

### 1. Open the repository

Open the repository root that contains `AGENTS.md` and use branch:

```text
setup/project-brain-v1
```

Do not run this task against `main` until the project brain is approved and merged.

### 2. Prepare the adult-owner local file

Copy:

```text
ops/freelancehunt/freelancehunt_owner.local.example.yaml
```

to:

```text
.codex/private/freelancehunt_owner.local.yaml
```

Fill only truthful adult-owner information. The target path is ignored by Git and must never be committed.

### 3. Prepare approved local assets

Place any real profile photo and portfolio media under:

```text
artifacts/private/freelancehunt-profile/input/
```

The adult owner must approve the real profile photo. Do not generate or alter a face to represent the account owner.

### 4. Enable the browser tool

In Codex, verify that `$playwright-interactive` is available through `/skills`, or verify a Playwright/Chrome DevTools MCP server through `/mcp`.

If the skill was added while Codex was already open, restart Codex so it detects the repository skill.

### 5. Adult owner signs in

Open Freelancehunt in the interactive browser. The adult owner personally enters credentials and completes CAPTCHA, OTP, 2FA, recovery prompts, or other authentication.

Do not paste passwords, cookies, recovery codes, or identity documents into a prompt or repository file.

## Execution prompt

Use:

```text
$freelancehunt-profile-operator

Complete the one legitimate adult-owned Antonov Digital Freelancehunt profile in the currently authenticated browser session.

Use `ops/freelancehunt/profile_source.yaml` for all public business copy and `.codex/private/freelancehunt_owner.local.yaml` for adult identity-bound fields. Inspect the current live UI before writing. Autonomously choose and save the strongest truthful wording that fits each field. Do not ask for approval on ordinary reversible profile edits.

Stop only for account mismatch, missing legal owner data, login/CAPTCHA/OTP/2FA, identity verification or document upload, payment/paid plan, a contractual action, or contradictory source facts.

Do not submit bids, message clients, buy Plus, change payment details, or operate the minor-owned account. Save screenshots and a complete local report under `artifacts/private/freelancehunt-profile/`.
```

## Expected behavior

Codex should:

1. Confirm that the visible account belongs to the adult owner.
2. Inspect all editable sections and current limits.
3. Map live field names to project source values.
4. Fill and save one reversible section at a time.
5. Reopen each section to verify persistence.
6. Complete specializations and skills using exact current platform labels.
7. Publish only portfolio items whose evidence and assets are ready.
8. Verify the public profile in a fresh tab and at mobile width.
9. Produce:

```text
artifacts/private/freelancehunt-profile/field-map.md
artifacts/private/freelancehunt-profile/action-log.md
artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md
artifacts/private/freelancehunt-profile/before/
artifacts/private/freelancehunt-profile/after/
```

## Manual checkpoints that remain with the adult owner

Codex must pause for:

- account login
- CAPTCHA
- phone OTP
- two-factor authentication
- identity/passport verification
- identity-document upload
- financial/payment configuration
- acceptance of legal or contractual terms that were not already approved

These checkpoints do not prevent Codex from autonomously completing the rest of the profile.

## Prohibited actions

- Using the deactivated minor-owned account
- Sharing or storing the adult owner's password
- Exporting browser cookies or session state into the repository
- Creating a duplicate freelancer account
- Buying Plus without a separate commercial decision
- Automated bidding or platform messages
- Inventing projects, metrics, experience, education, certifications, or testimonials
- Publishing a portfolio item without evidence and approved assets

## Completion definition

The run is successful when the adult-owned public profile is coherent, truthful, complete across all safely editable sections, and every deferred item is listed with an exact missing-input reason in the local report.
