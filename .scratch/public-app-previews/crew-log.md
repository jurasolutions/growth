# Crew log: public-app-previews

## 2026-10-31T20:00:00+08:00 conductor
status:    done
persona:   conductor
ticket:    01
artifacts: issues/01-open-app-previews.md, spec.md; amended MC §6 Q4, Dispatch PRD AC-D8.4 and P8, setup steps §7, ticket 16
decisions: G0 taken under Ting Yu's standing "don't ask, decide" rule: infra route. Ting Yu's request replaces MC §6 Q4.
decisions: This repo is public, so the steps and the infra and code reviews live in jurasolutions/outputs/growth/setup/public-previews-2026-10-31/, not here.
questions: -
evidence:  curl preview -> 302 to Cloudflare Access; pytest -> 3982 passed; code review -> approved after one fix round
