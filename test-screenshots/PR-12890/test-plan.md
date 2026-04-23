# Test Plan: PR #12890 — feat(platform/copilot): message timestamps + accurate thought-for time

## What the PR does
- DB: new `ChatMessage.reasoningDurationMs` column + migration.
- Backend: `publish_chunk` accumulates `reasoning-start`/`reasoning-end` elapsed ms into Redis session-meta `reasoning_ms_total`. `mark_session_completed` persists it via `set_turn_duration(...)`. `ChatMessage` model now carries `created_at` and `reasoning_duration_ms`.
- Frontend: `convertChatSessionMessagesToUiMessages` returns `{ durations, reasoningDurations, timestamps }`. `useLoadMoreMessages` + `useChatSession` + `useCopilotPage` merge these maps and pass them down to `ChatMessagesContainer`, which forwards to `TurnStatsBar`. `TurnStatsBar` prefers `reasoningDurationMs` over `durationMs` when available, and wraps the "Thought for X" label in a tooltip that shows the full local date/time.

## Scenarios

### Backend / API
1. Migration applied — `ChatMessage.reasoningDurationMs` column exists.
2. New assistant turn with extended-thinking model — after completion, the `ChatMessage` row has both `durationMs` and a non-null `reasoningDurationMs`, and the API returns `reasoning_duration_ms` and `created_at` in the session messages payload.
3. Redis session meta hash accumulates `reasoning_ms_total` across the turn.

### Frontend / UI
4. Send message to copilot with extended-thinking model → assistant responds → "Thought for X" label appears.
5. The "Thought for X" value is populated from reasoning-only time, not the whole-turn wall clock. To verify: trigger a turn with tool-use that adds obvious wall-clock time but little reasoning — the label should reflect reasoning-only duration (smaller than turn wall clock).
6. Hover "Thought for X" label → tooltip shows local date/time for the assistant message.
7. Reload page → label and tooltip persist (hydrated from server).
8. Old/legacy messages (no `reasoning_duration_ms`) still show the fallback whole-turn `duration_ms` label.
9. Paged/old messages loaded via Load More also carry reasoning duration + timestamp through the merged maps.

## Negative / edge cases
10. When a turn fails/errors, no partial reasoning_duration_ms is written (error path skips `set_turn_duration` by design — verify no crash).
11. When timestamp ISO is malformed, `formatLocalTimestamp` returns the raw string (don't crash).
