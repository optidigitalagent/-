# Email Channels

## Security decision

The repository is currently public. Literal mailbox addresses, passwords, OAuth tokens and recovery data are therefore not committed. Exact addresses are held in the private ChatGPT project context and later runtime secret configuration.

## Critical distinction: Freelancehunt account vs Gmail mailbox

The blocked object is the Freelancehunt account registered in the minor founder's identity. That account cannot be used for browsing, alerts, profile work, bids, messages or automation and must be deactivated.

The Gmail address itself is a separate mailbox. After the minor-owned Freelancehunt account is deactivated, that mailbox may be used as an adult-managed read-only notification mirror that receives forwarded copies from the legitimate adult-owned Freelancehunt mailbox.

The mirror mailbox must not remain attached to, reactivate or operate a second Freelancehunt freelancer account.

## Mailbox A — adult-owned operational Freelancehunt mailbox

- Purpose: the sole active Freelancehunt account, account registration, platform notices, project alerts, client-thread notifications and operational correspondence
- Ownership: personally owned and controlled by the genuine adult account owner
- Account state: `ACTIVE_ADULT_OWNER`
- Platform actions: performed only by the adult account owner
- Internal source tag: `platform_owner`
- Runtime variable: `PLATFORM_OWNER_MAILBOX_ADDRESS`
- OAuth authorization: completed by the adult mailbox owner when implementation begins
- Exact address: selected and stored outside this public repository

The adult cofounder controls this mailbox, its recovery methods and the Freelancehunt account tied to it. The adult owner remains the verification subject, bidder, platform communicator, contracting party and payment recipient.

## Mailbox B — notification mirror and agent-ingestion mailbox

- Purpose: receive forwarded copies of permitted notification emails from Mailbox A
- Ownership/management: controlled by an adult
- Freelancehunt account: none active
- Account state: `READ_ONLY_ALERT_MIRROR`
- Outbound platform communication: prohibited
- Bids, profile changes and platform login: prohibited
- Agent access: read-only ingestion when implementation begins
- Internal source tag: `platform_alert_mirror`
- Runtime variable: `ALERT_MIRROR_MAILBOX_ADDRESS`
- Exact address: selected and stored outside this public repository

Mailbox B exists only to make alerts available to the internal agent without turning it into a second platform identity.

## Approved mail flow

```text
Freelancehunt adult-owned account
        ↓
Mailbox A — adult operational mailbox
        ↓ Gmail forwarding/filter
Mailbox B — read-only alert mirror
        ↓ read-only ingestion
Revenue agent / Telegram / CRM
```

The revenue agent may analyze the forwarded notification, classify the opportunity and draft a proposal. The adult owner remains responsible for every on-platform action.

## Direct-sales channel

The direct-sales mailbox role is not assigned by this correction. It may later use a separate mailbox or an explicitly approved existing mailbox. Do not silently repurpose the alert mirror for outbound sales.

## Excluded mailbox

The previously used `newartem855` mailbox is excluded from this project's email flow.

## Stage 0 connection strategy

1. Deactivate the minor-owned Freelancehunt account.
2. Confirm that Mailbox B is no longer tied to any active Freelancehunt account.
3. Register or configure the sole active Freelancehunt account on Mailbox A using the adult owner's truthful identity.
4. Enable two-factor authentication and recovery on both mailboxes.
5. Configure Gmail forwarding or a narrow filter from Mailbox A to Mailbox B for relevant Freelancehunt notifications.
6. Do not store passwords in ChatGPT, GitHub or source code.
7. When implementation begins, connect Mailbox B to the agent with the minimum read-only Gmail scope needed.
8. Keep Mailbox A under the adult owner's direct control; do not share its login.
9. Tag mirrored mail `source/freelancehunt` and deduplicate by original message/thread identifiers.

## Runtime data model

Every ingested message must record:

- source mailbox ID
- original mailbox ID
- source/platform
- original message/thread ID
- forwarding/mirror message ID
- lead ID
- direction
- received/sent time
- client identity
- opportunity ID
- state
- next action

## Controls

- One active Freelancehunt freelancer account, owned and controlled by the adult cofounder.
- One read-only notification mirror, not a second platform account.
- The minor founder may be disclosed as a partner but does not use the adult owner's platform login.
- No ingestion from the deactivated minor-owned Freelancehunt account.
- No bids, platform messages or profile changes from the mirror mailbox or agent.
- No duplicate alerts or replies when the same message exists in both mailboxes.
- OAuth tokens live only in Railway secrets or another approved encrypted store.
