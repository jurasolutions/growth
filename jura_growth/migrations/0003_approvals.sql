-- Approval requests (MC §4.6, ADR 0003). Approval state lives only here:
-- plug-in tables hold their item's own lifecycle and never a copy of a decision.
--
-- One row per request, shown to Ting Yu as A-nnnn (the id, zero-padded).
-- AUTOINCREMENT so an id he has seen never comes back for another request.

CREATE TABLE approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,             -- an approval kind a plug-in declares
  subject TEXT NOT NULL,          -- internal, for example outreach_message:412
  content_hash TEXT NOT NULL,     -- sha256 of what the kind's content() returned
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'skipped', 'expired', 'superseded')),
  reason TEXT NOT NULL,           -- why the engine is asking
  raised_by_run INTEGER REFERENCES runs (id),
  supersedes INTEGER REFERENCES approvals (id), -- the request this one replaced
  requested_at TEXT NOT NULL,     -- growth's clock, as every time here
  decide_by TEXT NOT NULL,        -- a pending request expires here
  use_by TEXT,                    -- set on approval; an unclaimed yes expires here
  decided_at TEXT,
  decided_by TEXT,                -- attribution: discord:<id> or terminal:<user>
  decided_origin TEXT CHECK (decided_origin IN ('terminal', 'ssh')),
  decision_ref TEXT,              -- Dispatch's --ref for the decision, if any
  used_at TEXT,                   -- the claim (approvals.use)
  used_by_run INTEGER REFERENCES runs (id),
  closed_at TEXT,                 -- when it expired or was superseded
  close_reason TEXT,
  posted_at TEXT,                 -- the card in #approvals (ticket 04b)
  message_id TEXT,
  CHECK (status NOT IN ('approved', 'skipped') OR (decided_at IS NOT NULL AND decided_by IS NOT NULL AND decided_origin IS NOT NULL)),
  CHECK (status <> 'pending' OR (decided_at IS NULL AND decided_by IS NULL AND decided_origin IS NULL AND decision_ref IS NULL
                                 AND use_by IS NULL AND used_at IS NULL AND used_by_run IS NULL)),
  CHECK (used_at IS NULL OR status = 'approved'),
  CHECK ((status IN ('expired', 'superseded')) = (closed_at IS NOT NULL))
);

-- One live request (pending, or approved and not yet claimed) per subject.
CREATE UNIQUE INDEX approvals_one_live ON approvals (kind, subject)
  WHERE status IN ('pending', 'approved') AND used_at IS NULL;
CREATE INDEX approvals_status_deadline ON approvals (status, decide_by);
CREATE INDEX approvals_raised_by_run ON approvals (raised_by_run);

-- A7: the transitions a record may make. Everything else aborts:
--   pending  -> approved or skipped (a decision), expired or superseded
--   approved -> skipped (a revoke), expired or superseded, while unused
--   approved -> used, once: used_at (and used_by_run) set by the claim
-- A used, skipped, expired or superseded record never changes, except that
-- a card not yet marked posted can be marked once on a record that isn't
-- used (ticket 04b's sweep may post after a decision or a lapse).
CREATE TRIGGER approvals_transitions BEFORE UPDATE ON approvals
BEGIN
  SELECT RAISE(ABORT, 'a used approval never changes')
    WHERE OLD.used_at IS NOT NULL;
  SELECT RAISE(ABORT, 'an approval''s kind, subject, content and request never change')
    WHERE NEW.id IS NOT OLD.id OR NEW.kind IS NOT OLD.kind OR NEW.subject IS NOT OLD.subject
       OR NEW.content_hash IS NOT OLD.content_hash OR NEW.reason IS NOT OLD.reason
       OR NEW.raised_by_run IS NOT OLD.raised_by_run OR NEW.supersedes IS NOT OLD.supersedes
       OR NEW.requested_at IS NOT OLD.requested_at OR NEW.decide_by IS NOT OLD.decide_by;
  SELECT RAISE(ABORT, 'an approval card is marked posted once')
    WHERE (OLD.posted_at IS NOT NULL AND NEW.posted_at IS NOT OLD.posted_at)
       OR (OLD.message_id IS NOT NULL AND NEW.message_id IS NOT OLD.message_id);
  SELECT RAISE(ABORT, 'an approval never returns to pending')
    WHERE OLD.status <> 'pending' AND NEW.status = 'pending';
  SELECT RAISE(ABORT, 'a skipped, expired or superseded approval never changes')
    WHERE OLD.status IN ('skipped', 'expired', 'superseded')
      AND (NEW.status IS NOT OLD.status OR NEW.decided_at IS NOT OLD.decided_at
        OR NEW.decided_by IS NOT OLD.decided_by OR NEW.decided_origin IS NOT OLD.decided_origin
        OR NEW.decision_ref IS NOT OLD.decision_ref OR NEW.use_by IS NOT OLD.use_by
        OR NEW.used_at IS NOT OLD.used_at OR NEW.used_by_run IS NOT OLD.used_by_run
        OR NEW.closed_at IS NOT OLD.closed_at OR NEW.close_reason IS NOT OLD.close_reason);
  SELECT RAISE(ABORT, 'only an approved request can be used, once')
    WHERE NEW.used_at IS NOT NULL AND (OLD.status <> 'approved' OR NEW.status <> 'approved');
  SELECT RAISE(ABORT, 'an approval''s used_by_run is set only by its claim')
    WHERE NEW.used_by_run IS NOT OLD.used_by_run AND NEW.used_at IS NULL;
  SELECT RAISE(ABORT, 'an approval''s decision is written only by a decision')
    WHERE NEW.status NOT IN ('approved', 'skipped')
      AND (NEW.decided_at IS NOT OLD.decided_at OR NEW.decided_by IS NOT OLD.decided_by
        OR NEW.decided_origin IS NOT OLD.decided_origin OR NEW.decision_ref IS NOT OLD.decision_ref);
  SELECT RAISE(ABORT, 'an approved request''s decision never changes while it stays approved')
    WHERE OLD.status = 'approved' AND NEW.status = 'approved'
      AND (NEW.decided_at IS NOT OLD.decided_at OR NEW.decided_by IS NOT OLD.decided_by
        OR NEW.decided_origin IS NOT OLD.decided_origin OR NEW.decision_ref IS NOT OLD.decision_ref);
  SELECT RAISE(ABORT, 'an approval''s use-by is set only by its approval')
    WHERE NEW.use_by IS NOT OLD.use_by AND NOT (OLD.status = 'pending' AND NEW.status = 'approved');
  SELECT RAISE(ABORT, 'an approval is closed only when it expires or is superseded')
    WHERE (NEW.closed_at IS NOT OLD.closed_at OR NEW.close_reason IS NOT OLD.close_reason)
      AND NOT (OLD.status IN ('pending', 'approved') AND NEW.status IN ('expired', 'superseded'));
END;

CREATE TRIGGER approvals_keep_decided BEFORE DELETE ON approvals
WHEN OLD.status <> 'pending'
BEGIN
  SELECT RAISE(ABORT, 'a decided or closed approval is never deleted');
END;

-- A9: every recorded decision, keyed by its delivery. The same --ref twice
-- returns the first answer. Append-only, like events.
CREATE TABLE approval_decisions (
  id INTEGER PRIMARY KEY,
  approval_id INTEGER NOT NULL REFERENCES approvals (id),
  source_ref TEXT,
  decision TEXT NOT NULL CHECK (decision IN ('approve', 'skip')),
  actor TEXT NOT NULL,
  origin TEXT NOT NULL CHECK (origin IN ('terminal', 'ssh')),
  decided_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  args_json TEXT NOT NULL DEFAULT '{}',
  answer TEXT NOT NULL,
  text TEXT NOT NULL
);
CREATE UNIQUE INDEX approval_decisions_ref ON approval_decisions (approval_id, source_ref);

CREATE TRIGGER approval_decisions_no_update BEFORE UPDATE ON approval_decisions
BEGIN SELECT RAISE(ABORT, 'approval decisions are append-only'); END;
CREATE TRIGGER approval_decisions_no_delete BEFORE DELETE ON approval_decisions
BEGIN SELECT RAISE(ABORT, 'approval decisions are append-only'); END;
