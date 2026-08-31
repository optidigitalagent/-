# Email Channels

## Security decision

The repository is currently public. Literal mailbox addresses, passwords, OAuth tokens and recovery data are therefore not committed. Exact addresses are held in the private ChatGPT project context and later runtime secret configuration.

## Mailbox A — blocked Freelancehunt account mailbox

- Current purpose: account recovery and archival notices only
- Operational status: `DISCONNECTED_BLOCKED_UNTIL_18`
- Client-facing: no
- Agent ingestion: prohibited
- Gmail OAuth/forwarding: prohibited while tied to the blocked under-18 account
- Runtime variable: none until a lawful platform route exists
- Exact address: stored outside this public repository

This mailbox must not feed Freelancehunt alerts, projects or account activity into the revenue agent.

## Mailbox B — direct sales and agent processing

- Purpose: direct outreach, client replies, proposals, call scheduling, documents and lead processing
- Client-facing: yes when used for direct clients
- Internal source tag: `direct_sales`
- Runtime variable: `SALES_MAILBOX_ADDRESS`
- Exact address: selected and stored outside this public repository

## Future approved platform mailbox

If Freelancehunt explicitly approves a genuine adult-founder/team format, that legitimate adult account must use an account controlled by its real adult owner. Its mailbox and OAuth authorization must be configured separately and only after written approval.

Do not reuse the blocked minor account as a workaround.

## Excluded mailbox

The previously used `newartem855` mailbox is excluded from this project’s email flow.

## Stage 0 connection strategy

1. Keep the blocked Freelancehunt mailbox disconnected.
2. Enable two-factor authentication and recovery on the direct-sales mailbox.
3. Connect the direct-sales mailbox through Gmail OAuth; never store passwords in ChatGPT, GitHub or source code.
4. Tag direct client mail `source/direct`.
5. Add a platform mailbox only after a lawful and platform-approved owner/format exists.

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

- One platform account per real owner, truthful details and explicit permission for any team model.
- No blocked-account ingestion.
- No duplicate replies when the same lead appears through multiple lawful channels.
- OAuth tokens live only in Railway secrets or another approved encrypted store.
