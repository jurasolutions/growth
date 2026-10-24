# crew-log — growth PRD audit

## 2026-10-24T21:35+08:00 reviewer (04 app factory)
status:    done
artifacts: reviews/code-review-04-app-factory.md
decisions: verdict approve; 9 should-fix; worst: unquoted copy skips brand gate (S1), "None. Not ..." official-source bypass (S2), AI PRDs not held to 2 tries (S3), digest lacks §5.5 usage (S4), prds_per_day 0 crashes precheck (T2)
questions: Made-with line (§6.4)?; Time-saved calculator vs no-saving-claims rule?; accept any *.gov.sg plus abs.org.sg?
evidence:  pytest tests/test_apps.py -> 67 passed

## 2026-10-24T21:40+08:00 reviewer (01 foundation)
status:    done
artifacts: reviews/code-review-01-foundation.md
decisions: verdict changes-requested; B1 headless run can print .env via `check --file` and upload files via `discord post --file` (runner.py:226-238, cli.py:51-82); B2 auto-pause never fires when Discord unreachable (runner.py:133-135, discord.py:151-170); B3 spelled-out figures pass the numbers rule (brand_check.py:387-393); 11 should-fix, 11 nits
questions: Q2 Keychain or .env? rec Keychain. Q1 brief runner? rec confirm Cowork in PRD
evidence:  pytest test_core + test_brand_check (4 repo-writing tests deselected) -> 120 passed; repros for B1-B3 confirmed

## 2026-10-24T21:45+08:00 infra-engineer (setup inventory)
status:    needs-human
artifacts: reviews/infra.md
decisions: read growth.db only via scratch copies (stale journal); no wizard yet (sending-domain and Keychain choices change its steps)
questions: live site lacks /unsubscribe, /api/resend-webhook, /privacy, /apps; website toolbox branch has 6 unpushed commits (rec merge+deploy before live send). Stale growth.db journal (rec run jura-growth only on the Mac). Frozen-clock social rows dated 2026-10-26 (rec delete before installing jobs). Mac sleeps after 1 idle min (rec pmset -c sleep 0 + daily wake). Sending domain? rec jurasolutions.sg
evidence:  .env missing; no jura-* Keychain items; no LaunchAgents; 2 rendered plists came from pytest; 0/8 webhooks; dig -> Resend records present, MX Zoho; pytest (scratch clone) -> 515 passed

## 2026-10-24T21:50+08:00 reviewer (03 social + community)
status:    done
artifacts: reviews/code-review-03-social-community.md; verify/test_verify_social_community.py
decisions: changes-requested; C-B1 rules.py:142-163 reads "No promotion on weekends"/"No posts on Sundays" as the only allowed days; C-B2 settings.yaml:93-99 denies 6 exact hosts, other facebook subdomains, fb.watch, fbcdn.net, facebook.net, messenger.com stay fetchable. Social: no blockers, block 3 absent as planned; should-fix: 07:15 never checked, grant detector gaps. Security: image_path can upload any file (.env) to Discord; headless runs can call `community set joined=yes`
questions: Monday news window 7 days vs PRD 48h (rec amend PRD); weekends, post_as, 3 groups/week defaulted (rec Ting Yu confirms)
evidence:  pytest test_social*.py test_community.py -> 134 passed; reproductions (temp dirs) -> 9 passed

## 2026-10-24T21:55+08:00 reviewer (02 scout + outreach)
status:    needs-human
artifacts: reviews/code-review-02-scout.md; repro-scout/
decisions: verdict changes-requested; 5 blocking (still shadow mode): B1 complaint after unsubscribe never pauses (suppression.py:66-103); B2 warmup_start lifts day-1 cap to 20 (send.py:172-177); B3 headless run can loop send-due, run requeue-shadow (runner.py:226-238); B4 check --file .env --json echoes secrets, WebFetch can exfiltrate (cli.py:59-83); B5 address domain not tied to company (leads.py:304-351)
questions: D1 suppression append-only? rec yes; "two brand failures" = two emails? rec yes; require 3 shadow business days in live_problems? rec yes; drop hint list/auto-substitution? rec yes
evidence:  pytest full -> 515 passed; repro harness -> 10 passed
