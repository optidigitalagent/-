# Email Channels

## Security decision

The repository is currently public. Literal mailbox addresses, passwords, OAuth tokens and recovery data are therefore not committed. Exact addresses are held in the private ChatGPT project context and later runtime secret configuration.

## Mailbox 0 — blocked minor-account mailbox

- Current purpose: account recovery and archival notices only
- Operational status: `DISCONNECTED_BLOCKED_UNTIL_18`
- Client-facing: no
- Agent ingestion: prohibited
- Gmail OAuth/forwarding: prohibited while tied to the blocked under-18 account
- Runtime variable: none
- Exact address: stored outside this public repository

This mailbox must not feed Freelancehunt alerts, projects or account activity into the revenue agent.

## Mailbox A — approved adult-owned Freelancehunt mailbox

- Purpose: adult cofounder’s account registration, platform notices, project alerts and client-thread notifications
- Ownership: personally owned and controlled by the genuine adult account owner
- Client-facing outside the platform: no by default
- Internal source tag: `platform_alert`
- Runtime variable: `PLATFORM_MAILBOX_ADDRESS`
- OAuth authorization: completed by the adult mailbox owner when implementation begins
- Exact address: to be selected and stored outside this public repository

The adult cofounder must control this mailbox, its recovery methods and the Freelancehunt account tied to it. Do not reuse the blocked minor-account mailbox as a workaround.

## Mailbox B — direct sales and agent processing

- Purpose: direct outreach, client replies, proposals, call scheduling, documents and lead processing
- Client-facing: yes when used for direct clients
- Internal source tag: `direct_sales`
- Runtime variable: `SALES_MAILBOX_ADDRESS`
- Exact address: selected and stored outside this public repository

## Excluded mailbox

The previously used `newartem855` mailbox is excluded from this project’s email flow.

## Stage 0 connection strategy

1. Keep the blocked minor-account mailbox disconnected.
2. Select an adult-owned platform mailbox that the adult cofounder personally controls.
3. Enable two-factor authentication and recovery on the adult-owned platform mailbox.
4. Enable two-factor authentication and recovery on the direct-sales mailbox.
5. Do not store passwords in ChatGPT, GitHub or source code.
6. When implementation begins, connect the adult-owned platform mailbox and direct-sales mailbox through separate Gmail OAuth authorizations.
7. Tag adult-owned platform mail `source/freelancehunt`.
8. Tag direct client mail `source/direct`.

## Runtime data model

Every ingested message must record:

- mailbox ID
- source/platform
- message/thread ID
- lead ID
- direction: inbound/outbound
- received/sent time
- client identity
- opportunity ID
- state
- next action

## Controls

- One platform account per real owner, with truthful identity and ownership.
- The adult cofounder remains the account and platform-mailbox controller.
- The minor founder may be disclosed as a partner but does not use the adult owner’s login.
- No blocked-account ingestion.
- No duplicate replies when the same lead appears through multiple lawful channels.
- OAuth tokens live only in Railway secrets or another approved encrypted store.
