# Next Action

## Immediate objective

Finish Stage 0 without production development, deactivate the blocked minor-owned account, establish the approved one-account plus alert-mirror architecture, and complete the adult-owned profile through Codex-assisted browser setup.

## Exact sequence

1. Deactivate the under-18 Freelancehunt account through `Settings → Security`.
2. Preserve a screenshot or written note confirming deactivation.
3. Confirm that the mailbox formerly used by that account will be used only as an adult-managed notification mirror and has no active Freelancehunt account attached.
4. Confirm the genuine adult cofounder's full legal name, age eligibility and ownership/control of the operational platform mailbox.
5. Enable two-factor authentication and recovery on the adult-owned operational mailbox and the alert-mirror mailbox.
6. The adult cofounder registers or configures the sole active Freelancehunt account on the operational mailbox using truthful personal data.
7. The adult cofounder remains the sole account controller, verification subject, bidder, platform communicator, contracting party and payment recipient.
8. Locally copy `ops/freelancehunt/freelancehunt_owner.local.example.yaml` to `.codex/private/freelancehunt_owner.local.yaml` and fill only truthful adult-owner data.
9. Enable `$playwright-interactive` or a Playwright/Chrome DevTools MCP server in Codex.
10. The adult owner signs in to Freelancehunt in the interactive browser and personally completes CAPTCHA, OTP and 2FA.
11. Invoke `$freelancehunt-profile-operator` using the prompt in `docs/FREELANCEHUNT_BROWSER_PROFILE_AUTOMATION.md`.
12. Let Codex inspect, fill, save and verify ordinary reversible profile fields from `ops/freelancehunt/profile_source.yaml` without asking for approval on each field.
13. The adult owner personally handles identity verification, document upload, payment configuration and any legal confirmation.
14. Preserve the local field map, action log, before/after screenshots and `PROFILE_SETUP_REPORT.md`.
15. Configure Gmail forwarding or a narrow filter so relevant Freelancehunt notification copies flow from the adult-owned operational mailbox to the read-only alert mirror.
16. Do not create or keep a second active Freelancehunt freelancer account on the mirror mailbox.
17. Review the Draft PR containing this project brain; do not merge yet.
18. Rename the canonical repository to `antonov-digital-freelance-revenue-engine`.
19. Change repository visibility to private before committing exact mailbox mappings or sensitive commercial data.
20. Confirm that Railway still points to the correct repository, branch and service after the rename.
21. Finish the ChatGPT Project structure described in `docs/CHATGPT_PROJECT_SETUP.md`.
22. Decide the direct-sales mailbox role separately; the alert mirror is read-only by default.
23. When implementation begins, connect only the alert mirror to the agent with minimum read-only Gmail permissions. Keep the adult operational mailbox under the adult owner's direct control.

## Constraints

- Do not use the registered under-18 Freelancehunt account for any purpose before age 18.
- Do not create a replacement account for the minor founder with another email.
- Do not use a false birth date, borrowed identity, transferred account or staged weak bid.
- The adult cofounder's account is not a shared team login.
- The minor founder may be disclosed as a partner but may not operate or impersonate the adult owner.
- The notification mirror is not a freelancer account and cannot send platform messages or bids.
- Codex may edit only ordinary reversible profile fields from approved source data.
- Codex must pause for account mismatch, login, CAPTCHA, OTP, 2FA, identity verification, document upload, payments, paid plans and contractual actions.
- Automatic bidding, mass messaging and other prohibited automation remain forbidden.
- Do not merge, deploy or modify production during Stage 0.
- Do not publish literal mailbox addresses while the repository is public.

## Stop condition

Stage 0 is complete when the brain is approved, repository identity/privacy are correct, the blocked account is deactivated, the genuine adult-owned Freelancehunt account is ready and truthfully completed, and its notifications can lawfully flow to the separate read-only alert mirror.
