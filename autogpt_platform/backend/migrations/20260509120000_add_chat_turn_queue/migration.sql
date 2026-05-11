-- ChatMessage: row lifecycle + generic per-row metadata bag.
-- ``chatStatus`` is ``'idle'`` on every existing row (the 99% case) and
-- ``'queued'`` only on user rows waiting for a running slot.  Open
-- enum: future states (``'errored'``, ``'paused'``, etc.) can be added
-- without another migration.  ``metadata`` carries the dispatcher's
-- submit-time payload on queued rows today and is generic so future
-- per-row state can land in it too.
ALTER TABLE "ChatMessage"
    ADD COLUMN "chatStatus" TEXT NOT NULL DEFAULT 'idle',
    ADD COLUMN "metadata"   JSONB;

-- Partial index for the dispatcher's FIFO scan.  Only non-idle rows
-- carry an entry, so the index stays tiny on a hot table.
CREATE INDEX "ChatMessage_queue_dispatch_idx"
    ON "ChatMessage" ("chatStatus", "createdAt")
    WHERE "chatStatus" <> 'idle';

-- ChatSession: running-turn tracker for the per-user cap count.
ALTER TABLE "ChatSession"
    ADD COLUMN "currentTurnStartedAt" TIMESTAMP(3);

-- Partial index for the per-user running-turn count.  Stays tiny since
-- currentTurnStartedAt is NULL on every idle session (the 99% case).
CREATE INDEX "ChatSession_running_turns_idx"
    ON "ChatSession" ("userId", "currentTurnStartedAt")
    WHERE "currentTurnStartedAt" IS NOT NULL;
