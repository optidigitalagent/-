# Email Channels

## Security decision

The repository is currently public. Literal mailbox addresses, passwords, OAuth tokens and recovery data are therefore not committed. Exact addresses remain in private project context and later runtime secret configuration.

## Current decision: one operational Freelancehunt mailbox

Use one adult-owned mailbox for all current Freelancehunt functions:

- registration of the sole active adult-owned account
- account and security notices
- new-project notifications
- client-thread notifications
- operational correspondence controlled by the adult owner
- permitted Gmail ingestion by the internal revenue agent

There is no alert-mirror mailbox in the current architecture.

## Mailbox A — adult-owned operational Freelancehunt mailbox

- Purpose: the sole active Freelancehunt account and its notification stream
- Ownership: personally owned and controlled by the genuine adult account owner
- Account state before registration: `ADULT_ACCOUNT_NOT_REGISTERED`
- Account state after truthful registration: `ACTIVE_ADULT_OWNER`
- Platform actions: performed only by the adult account owner
- Internal source tag: `freelancehunt_platform`
- Runtime variable: `PLATFORM_OWNER_MAILBOX_ADDRESS`
- Agent access: minimum Gmail permissions needed to read permitted platform notifications; sending email does not authorize any on-platform action
- OAuth authorization: completed by the adult mailbox owner when implementation begins
- Exact address: selected and stored outside this public repository

The adult owner remains the verification subject, account controller, bidder, platform communicator, contracting party and payment recipient.

## Excluded mailboxes

- The mailbox formerly tied to the minor founder's deactivated Freelancehunt account is excluded from the current operational flow.
- The previously used `newartem855` mailbox is excluded from this project.
- No forwarding mirror is configured at this stage.

## Approved mail flow

```text
Freelancehunt adult-owned account
        ↓
adult-owned operational Gmail mailbox
        ↓ minimum-permission Gmail ingestion
Revenue agent / Telegram / CRM
```

The revenue agent may analyze notification emails, normalize opportunities, detect duplicates, score relevance and draft proposals. The adult owner remains responsible for every action inside Freelancehunt.

## Direct-sales channel

A separate direct-sales mailbox is not assigned by this decision. It can be added later if direct outreach requires separation from platform operations. Do not silently use an excluded mailbox or create another Freelancehunt identity.

## Stage 0 connection strategy

1. Keep the minor-owned Freelancehunt account deactivated.
2. Confirm the adult owner's control, recovery methods and two-factor protection for the selected operational mailbox.
3. Register the sole active Freelancehunt account using the adult owner's truthful identity.
4. Do not store passwords in ChatGPT, GitHub, prompts or source code.
5. When implementation begins, connect the operational mailbox through Gmail OAuth with the minimum scope required for permitted notification ingestion.
6. Tag ingested mail `source/freelancehunt`.
7. Deduplicate by original Gmail message/thread identifiers and parsed platform opportunity identifiers.

## Runtime data model

Every ingested message must record:

- source mailbox ID
- source/platform
- original message/thread ID
- lead ID
- direction
- received/sent time
- client identity when present
- opportunity ID
- state
- next action

## Controls

- One active Freelancehunt freelancer account, owned and controlled by the adult founder.
- No second platform account, alert mirror or forwarding chain in the current architecture.
- The minor founder may be disclosed as a partner but does not use the adult owner's platform login.
- Gmail ingestion does not grant permission to submit bids, send platform messages or change the profile.
- No duplicate alerts or replies.
- OAuth tokens live only in Railway secrets or another approved encrypted store.
