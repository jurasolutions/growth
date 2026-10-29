-- Only an SSH decision counts (MC AC-M6.4, ADR 0004; final code review Sp4,
-- follow-ups review Sp-S1).
--
-- Terminal decisions were turned off on 2026-10-26, and approvals.decide()
-- accepts only Origin.ssh(). From this migration on, no row that is inserted,
-- and no decision that is written, carries a 'terminal' origin or a
-- 'terminal:' actor:
--   approvals: an INSERT with either, or an UPDATE that sets either anew;
--   approval_decisions: an INSERT with either.
-- Raw SQL can still forge an SSH decision (ADR 0004 accepts that), but not a
-- Terminal one.
--
-- Forward-only: no row changes. A Terminal decision already on record stays
-- as it was, and can still lapse or be superseded, since neither touches its
-- decided_origin or decided_by; a revoke over SSH replaces both. use() never
-- claims such a record (not-ssh).

CREATE TRIGGER approvals_insert_ssh_only BEFORE INSERT ON approvals
WHEN NEW.decided_origin = 'terminal' OR NEW.decided_by LIKE 'terminal:%'
BEGIN
  SELECT RAISE(ABORT, 'only an SSH decision is recorded: Terminal decisions are off');
END;

CREATE TRIGGER approvals_ssh_only BEFORE UPDATE OF decided_origin, decided_by ON approvals
WHEN (NEW.decided_origin = 'terminal' AND OLD.decided_origin IS NOT 'terminal')
  OR (NEW.decided_by LIKE 'terminal:%' AND NEW.decided_by IS NOT OLD.decided_by)
BEGIN
  SELECT RAISE(ABORT, 'only an SSH decision is recorded: Terminal decisions are off');
END;

CREATE TRIGGER approval_decisions_ssh_only BEFORE INSERT ON approval_decisions
WHEN NEW.origin = 'terminal' OR NEW.actor LIKE 'terminal:%'
BEGIN
  SELECT RAISE(ABORT, 'only an SSH decision is recorded: Terminal decisions are off');
END;
