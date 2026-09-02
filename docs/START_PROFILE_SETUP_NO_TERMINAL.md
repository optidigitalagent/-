# Start Freelancehunt Profile Setup Without Terminal Commands

## Recommended surface

Use Codex in the ChatGPT desktop app with the project folder open.

Why this surface:

- it can work with the local project files and repository instructions
- it discovers `AGENTS.md` and repository skills from the opened folder
- it can use the built-in browser/computer-use capability
- Playwright or Chrome DevTools MCP can remain a fallback

## What the adult owner must do first

1. Register the sole active Freelancehunt account using the adult owner's real identity and personally controlled operational mailbox.
2. Enable mailbox recovery and two-factor authentication.
3. Keep the minor-owned Freelancehunt account deactivated.
4. Prepare the adult owner's real profile photo.

## Prepare the project folder

Use the ready-to-open project package supplied from the Stage 0 branch, or download/extract the repository branch into a normal folder.

The folder must contain at least:

```text
AGENTS.md
.codex/project_brain/
.agents/skills/freelancehunt-profile-operator/SKILL.md
ops/freelancehunt/profile_source.yaml
ops/freelancehunt/OWNER_INPUT_TEMPLATE_RU.txt
ops/freelancehunt/CODEX_PROFILE_PROMPT_RU.txt
```

## Fill only four local values

Copy:

```text
ops/freelancehunt/OWNER_INPUT_TEMPLATE_RU.txt
```

to:

```text
ops/freelancehunt/OWNER_INPUT.txt
```

Fill:

```text
FULL_LEGAL_NAME=
PUBLIC_DISPLAY_NAME=
ADULT_PHONE=
PROFILE_PHOTO_PATH=
```

Do not add passwords, OTPs, passport files, banking data, cookies or recovery codes.

`ops/freelancehunt/OWNER_INPUT.txt` is ignored by Git through the project privacy rules and must remain local.

## Open the folder

1. Open the ChatGPT desktop app.
2. Select Codex.
3. Open the extracted project folder.
4. Start a new Codex chat in that folder.
5. Allow the browser/computer-use plugin for `freelancehunt.com` when prompted.

## Adult owner signs in

The adult owner personally:

- opens Freelancehunt in the Codex browser
- enters login and password
- completes CAPTCHA
- enters SMS/OTP/2FA
- confirms recovery prompts

Never paste authentication secrets into the Codex prompt or project files.

## Run the operator

Open:

```text
ops/freelancehunt/CODEX_PROFILE_PROMPT_RU.txt
```

Copy its full contents into the Codex chat and send it.

Codex will inspect, fill, save and verify all ordinary reversible profile fields. It will stop only for identity, authentication, verification, payment, contractual or contradictory-data checkpoints.

## Expected local output

```text
artifacts/private/freelancehunt-profile/field-map.md
artifacts/private/freelancehunt-profile/action-log.md
artifacts/private/freelancehunt-profile/PROFILE_SETUP_REPORT.md
artifacts/private/freelancehunt-profile/before/
artifacts/private/freelancehunt-profile/after/
```

## Never allow during this run

- bids
- client messages
- Plus purchase
- payment changes
- identity verification performed by AI
- document upload by AI
- use of the deactivated minor-owned account
- invented experience, metrics, certificates, clients or technologies
