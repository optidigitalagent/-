# Codex Execution Reporting Standard

## Purpose

Codex reports must make it possible to determine whether the project moved closer to funded work, what actually changed, what evidence proves it, and what exact action remains.

More text alone is not enough. Reports must be structured, evidence-based, and explicit about assumptions, blockers, and browser/account state.

## Required report format

Every execution report must contain all sections below. Do not replace them with a one-line status code.

### 1. Objective

- Exact task requested
- Funnel stage affected
- Expected commercial result

### 2. Outcome

Use one status:

- `COMPLETED`
- `PARTIALLY_COMPLETED`
- `BLOCKED`
- `FAILED_VALIDATION`

Then state in plain language what was and was not achieved.

### 3. Actions performed

List every material action actually performed, including:

- files read
- files created or changed
- pages opened
- fields inspected
- fields edited
- settings changed
- validations run

Do not claim an action that was only planned.

### 4. Evidence

Provide concrete evidence for every important claim:

- exact file paths
- exact browser URL when available
- visible account name
- section or field labels
- before/after values without exposing secrets
- screenshot paths
- saved-report paths
- validation output

If evidence is unavailable, say `NOT VERIFIED`.

### 5. Source-of-truth validation

Explicitly compare the live state against the approved source of truth:

- account owner
- public name
- team roles
- profile language
- categories
- skills
- pricing model
- portfolio claims

For every mismatch, show:

`expected -> observed -> required correction`

Never mark a source as ready merely because placeholders were removed. The actual person and role must be correct.

### 6. Changes made

For repository/local-file tasks, report:

- number of files changed
- exact list of changed files
- key changes per file
- whether any placeholder remains
- whether any contradiction remains

For browser tasks, report:

- exact sections saved
- exact fields persisted after reopening
- exact sections left unchanged

### 7. Unchanged / prohibited actions

Confirm what was deliberately not changed, especially:

- identity
- date of birth
- phone ownership
- documents
- verification
- payments
- bids
- client messages
- contracts

### 8. Blockers

For each blocker include:

- blocker code
- exact observed condition
- why it blocks only the affected action
- what work continued despite the blocker
- single minimum owner action needed

Do not stop the whole task if safe offline or non-identity work remains.

### 9. Commercial progress

Report:

- previous readiness percentage
- new readiness percentage
- what increased or decreased readiness
- which revenue milestone is now closer
- whether the result enables profile publication, alerts, proposals, or funded work

Do not increase readiness for cosmetic or internally contradictory changes.

### 10. Next action

Give exactly one next action, written so it can be executed immediately.

If owner input is required, specify the exact field or browser action without requesting passwords, OTPs, documents, or payment data in chat.

## Mandatory validation rules

Before returning any `*_READY` status:

1. Re-read the changed files from disk.
2. Search the full relevant workspace for old placeholder and contradictory values.
3. Compare the selected account-owner name against the approved adult owner, not against Artem or a temporary nickname.
4. For browser work, reopen saved sections and confirm persistence.
5. If a live URL cannot be determined, state that explicitly and validate using visible page state.
6. Do not infer ownership from a nickname, photo, email alias, or local placeholder.

## Profile-specific completion report

For Freelancehunt live profile work, always include:

- connected browser status
- authenticated status
- current URL or `URL_NOT_AVAILABLE`
- visible public name
- whether the name matches the genuine adult owner
- visible avatar status
- profile sections edited
- exact specializations selected
- exact skills selected
- languages published
- pricing presentation
- portfolio items published and deferred
- email notifications enabled
- final public profile URL
- remaining adult-owner actions

## Invalid report examples

Insufficient:

```text
OWNER_SOURCE_READY
Changed files: 10
Contradictions: 0
```

This is invalid when the selected owner is the wrong person.

Sufficient:

```text
Outcome: FAILED_VALIDATION
Expected adult owner: [local approved name]
Observed owner source: Artem Antonov
Mismatch: account owner is still the minor co-founder
Files changed: ...
Workspace search: ...
Browser changes: none
Readiness: 80% -> 76%
Next action: replace only the adult-owner public name in OWNER_INPUT and four about files, then rerun ownership validation.
```
