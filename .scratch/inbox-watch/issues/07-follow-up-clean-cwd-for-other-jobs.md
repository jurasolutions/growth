# Keep other headless jobs away from secrets through read-only Bash

Status: needs-triage (follow-up, not part of this feature's release)
Blocked by: none

Code review 02 (SEC-1) found that a headless run can read files from its working directory through read-only Bash commands such as `grep -r`, which Claude Code allows without a rule, so the `Read` denies on `.env` don't cover them. Ticket 02 closed this for `inbox-check` with `caps.CLEAN_CWD_JOBS`, and ticket 05 for the two inbox browser jobs.

The same route is open for `publish`, which reads hostile pages with signed-in accounts, and for `social`, `scout-research`, `community` and `app-factory`, which fetch from the web. Those jobs were left alone here because they are rehearsed live jobs and outside this PRD. They need the same clean folder, each checked for the files it reads under `jurasolutions/`.
