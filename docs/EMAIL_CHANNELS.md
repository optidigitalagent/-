# Email Channels

## Security decision

The repository is currently public. Literal mailbox addresses, passwords, OAuth tokens and recovery data are therefore not committed. Exact addresses are held in the private ChatGPT project context and later runtime secret configuration.

## Mailbox A — Freelancehunt account and platform alerts

- Purpose: primary Freelancehunt registration, account notices, project alerts and platform notifications
- Client-facing outside the platform: no
- Internal source tag: `platform_alert`
- Runtime variable: `PLATFORM_MAILBOX_ADDRESS`
- Exact address: selected and stored outside this public repository

## Mailbox B — Direct sales and agent processing

- Purpose: direct outreach, client replies, proposals, call scheduling, documents and optional processing of forwarded alerts
- Client-facing: yes when used for direct clients
- Internal source tag: `direct_sales`
- Runtime variable: `SALES_MAILBOX_ADDRESS`
- Exact address: selected and stored outside this public repository

## Excluded mailbox

The previously used `newartem855` mailbox is excluded from this project’s email flow.

## Stage 0 connection strategy

1. Keep the two mailboxes logically separate.
2. Enable two-factor authentication and recovery before OAuth connection.
3. Use Gmail OAuth; never store passwords in ChatGPT, GitHub or source code.
4. Forward platform notifications only when needed, tagging them `source/freelancehunt`.
5. Tag direct client mail `source/direct`.
6. Later connect both accounts independently if the runtime needs separate read/send access.

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

- One platform account, one real owner, truthful details.
- No duplicate replies when the same alert appears in both mailboxes.
- OAuth tokens live only in Railway secrets or another approved encrypted store.
