-- Shadow emails can be requeued for live sending after the shadow trial
-- (`jura-growth outreach requeue-shadow`). The shadow row keeps its record
-- (mode 'shadow', sent_at) with status 'requeued'; a new queued row points
-- back to it. A shadow send never contacted anyone, so 'requeued' no longer
-- holds the company's one first email.

DROP INDEX outreach_messages_one_per_kind;
CREATE UNIQUE INDEX outreach_messages_one_per_kind ON outreach_messages (lead_id, kind)
  WHERE status NOT IN ('dropped', 'cancelled', 'skipped', 'failed', 'requeued');

ALTER TABLE outreach_messages ADD COLUMN requeued_from INTEGER;
