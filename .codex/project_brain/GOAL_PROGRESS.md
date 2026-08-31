# Goal Progress

## North-star goal

Create a repeatable system that produces funded Antonov Digital client work with minimal manual sales effort.

## Current stage

**Stage 0 — Project brain and governance**

## Completed

- [x] Brand selected: Antonov Digital
- [x] Two-founder team model defined
- [x] Service-neutral discovery policy defined
- [x] No-minimum-price policy defined
- [x] Supported languages and availability defined
- [x] Duplicate/fake Freelancehunt account strategy rejected
- [x] Existing repository selected as canonical base
- [x] Branch `setup/project-brain-v1` created
- [x] Project-brain scaffold committed without production code changes
- [x] Legacy Gmail/Telegram agent architecture preserved
- [x] Draft PR #1 opened against `main`
- [x] Freelancehunt support consulted about the under-18 account
- [x] Support outcome recorded: no platform use before age 18; account must be deactivated
- [x] Under-18 account excluded from all profile and platform activity
- [x] Follow-up sent about a genuine adult-cofounder account and disclosed partner role
- [x] Support approved independent operation by the adult cofounder and disclosure of the minor founder as a partner in client correspondence
- [x] Adult-owner route recorded as `APPROVED_ADULT_OWNER_WITH_DISCLOSED_PARTNER`
- [x] Email architecture clarified: one adult-owned operational Freelancehunt mailbox plus one adult-managed read-only alert mirror
- [x] Clarified that the mirror mailbox is not a second platform account and only receives forwarded copies from the adult-owned account
- [x] Repository-local Codex skill added for one-time adult-owned Freelancehunt profile setup
- [x] Truthful public profile source and private adult-owner template added
- [x] Browser automation runbook added with Playwright, authentication and verification boundaries

## Remaining in Stage 0

- [ ] Deactivate the under-18 Freelancehunt account through security settings
- [ ] Preserve a screenshot or note confirming deactivation
- [ ] Confirm the adult cofounder's full legal name, age eligibility and ownership/control of the operational mailbox
- [ ] Confirm adult management and recovery control of the alert-mirror mailbox
- [ ] Enable two-factor authentication and recovery on both mailboxes
- [ ] Register or configure one truthful Freelancehunt account on the adult-owned operational mailbox
- [ ] Confirm that the alert-mirror mailbox has no active Freelancehunt account attached
- [ ] Create `.codex/private/freelancehunt_owner.local.yaml` locally from the example and fill truthful adult-owner data
- [ ] Enable `$playwright-interactive` or a Playwright/Chrome DevTools MCP browser in Codex
- [ ] Run `$freelancehunt-profile-operator` against the authenticated adult-owned account
- [ ] Preserve the local profile setup report and final screenshots
- [ ] Configure a narrow forwarding rule from the adult-owned operational mailbox to the alert mirror
- [ ] Decide the separate direct-sales mailbox role; do not repurpose the alert mirror for outbound sales by default
- [ ] Review and approve Draft PR #1; do not merge yet
- [ ] Rename repository to `antonov-digital-freelance-revenue-engine`
- [ ] Change repository visibility to private
- [ ] Confirm Railway/GitHub deployment linkage after rename
- [ ] Create or finish the ChatGPT Project and chat structure
- [ ] When implementation begins, connect the alert mirror to the agent with minimum read-only Gmail permissions

## Stage 1 entry criteria

Stage 1 begins when:

1. the repository brain is approved;
2. the minor founder's Freelancehunt account is deactivated;
3. the adult-owned operational account and mailbox are confirmed;
4. the alert mirror is separated from any active platform identity and forwarding is ready; and
5. the adult-owned profile is ready for truthful Codex-assisted construction or has been completed and verified.
