# 01: Open app previews to anyone

Status: ready-for-agent
Route: infra

## What changes

Ting Yu decided on 2026-10-31: "after app is done, the url for preview should be accessible to anyone, it should not prompt a cloudflare signin". This replaces MC PRD §6 Q4, which put previews behind Cloudflare Access.

The gate is a Cloudflare Access application on the landing page's Pages previews. It is a dashboard setting and only Ting Yu changes it. The repo work is to stop saying previews are protected, and to give exact steps for the setting.

## Acceptance criteria

- [ ] `docs/app-factory.md` and the `dispatch_builds` comment in `config/settings.yaml` say app previews are public by decision, dated 2026-10-31, and state what that means.
- [ ] The Cloudflare steps, checked against current Cloudflare docs, are in `jurasolutions/outputs/growth/setup/public-previews-2026-10-31/`, outside this public repo.
- [ ] Opened in a private window, `https://claude-t-0001-invoice-builde.landing-page-eq7.pages.dev/` returns 200 with no Access redirect (Ting Yu's step, then checked with curl).
- [ ] The full test suite still passes.
