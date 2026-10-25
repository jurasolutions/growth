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
