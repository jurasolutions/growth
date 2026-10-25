# Decisions and control commands come only from a human origin

Status: proposed (2026-10-25). Referenced from ticket MC-04 and accepted in ticket MC-11a of
`prd-jura-mission-control-2026-10-25.md`.

Approvals and control commands enter in two ways only. One is `jura-growth approve|skip` in a real
terminal, with the first six characters of the request's content hash typed. The other is
`jura-growth remote`, reached through an SSH forced command (`restrict`, `from=`, over Tailscale)
whose key lives only with Dispatch's gateway user. `JURA_GROWTH_JOB` and `headless.NEVER` refuse
headless runs, but an environment variable is a label, not a credential: interactive Claude
sessions, crew agents and Dispatch tasks carry no such label. So the code also checks the origin: a
TTY, or an `sshd` ancestor with `SSH_ORIGINAL_COMMAND`, and never a `claude` ancestor. The Discord
user id is attribution, not authentication. Dispatch never runs on the growth Mac (Ting Yu,
2026-10-25), and no model rewrites a command between Ting Yu and `remote`.

A known limit: anything that can write `growth.db` directly can forge a decision. The `approvals`
trigger refuses the transitions A7 doesn't allow, but no trigger can tell who wrote a row. Headless
runs reach the database only through `jura-growth` commands (`Bash(jura-growth …)` rules); an
interactive session on the Mac is outside these guards, so don't open `growth.db` for writing from
one.

The audit trail has a known gap too. A decision's `approval.*` events are rows in `growth.db`,
committed with the decision, and lines in the JSONL mirror, written only after that commit, so a
decision or claim that rolls back leaves no trace in either. A crash between the commit and the
mirror write loses those lines while the rows stay. We accept that: `growth.db` is the log of
record, and the opposite order would leave the append-only mirror holding a decision or a claim
that never happened (`jura_growth/log.py`).
