-- Only an SSH decision counts (MC AC-M6.4, ADR 0004; final code review Sp4).
--
-- Terminal decisions were turned off on 2026-10-26, and approvals.decide()
-- accepts only Origin.ssh(). These triggers refuse any new decision written
-- with a 'terminal' origin, so raw SQL can't record one either. Forward-only:
-- no row changes, and a decision already on record with a 'terminal' origin
-- stays as it was. Such a record can still lapse, be superseded or be
-- revoked over SSH, but approvals.use() never claims it.

CREATE TRIGGER approvals_ssh_only BEFORE UPDATE OF decided_origin ON approvals
WHEN NEW.decided_origin = 'terminal' AND OLD.decided_origin IS NOT 'terminal'
BEGIN
  SELECT RAISE(ABORT, 'only an SSH decision is recorded: Terminal decisions are off');
END;

CREATE TRIGGER approval_decisions_ssh_only BEFORE INSERT ON approval_decisions
WHEN NEW.origin = 'terminal'
BEGIN
  SELECT RAISE(ABORT, 'only an SSH decision is recorded: Terminal decisions are off');
END;
