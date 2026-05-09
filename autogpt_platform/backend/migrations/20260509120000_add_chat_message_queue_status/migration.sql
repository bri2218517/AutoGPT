-- AlterTable
ALTER TABLE "ChatMessage"
    ADD COLUMN "queueStatus" TEXT,
    ADD COLUMN "queueBlockedReason" TEXT,
    ADD COLUMN "queueMetadata" JSONB,
    ADD COLUMN "queueStartedAt" TIMESTAMP(3);

-- Partial index for the dispatcher's FIFO scan: only queued rows count,
-- so the index stays tiny on a hot table where queueStatus is NULL on
-- every chat-history row.
CREATE INDEX "ChatMessage_queue_dispatch_idx"
    ON "ChatMessage" ("queueStatus", "createdAt")
    WHERE "queueStatus" IS NOT NULL;
