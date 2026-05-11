-- Session-level lifecycle for the per-user soft running cap +
-- cross-session queue.  ``chatStatus`` is ``'idle'`` on every existing
-- row (the 99% case), ``'queued'`` while waiting for a running slot,
-- and ``'running'`` while a turn is being processed.  Open enum:
-- future states can be added without another migration.
ALTER TABLE "ChatSession"
    ADD COLUMN "chatStatus" TEXT NOT NULL DEFAULT 'idle';

-- Covers BOTH the cap-count (count by userId + chatStatus) and the
-- queue-list ORDER BY updatedAt asc in one B-tree.  The pre-existing
-- (userId, updatedAt) index handles the sidebar list which filters on
-- userId alone.
CREATE INDEX "ChatSession_user_status_idx"
    ON "ChatSession" ("userId", "chatStatus", "updatedAt");

-- ChatMessage carries an optional per-row JSONB metadata bag for the
-- dispatcher's submit-time payload on the user row that triggered a
-- queued turn (file_ids, mode, model, permissions, context,
-- request_arrival_at).  Cleared / unused on every history row.
ALTER TABLE "ChatMessage"
    ADD COLUMN "metadata" JSONB;
