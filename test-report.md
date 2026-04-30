# Test report — PR #12958 + PR #12959 (dev environment)

**Target:** `https://dev-server.agpt.co` (backend) / `https://dev-builder.agpt.co` (frontend)
**Backend commit:** `09cb340acd` (`origin/dev` HEAD)
**Tester:** zamil.majdy@gmail.com
**Date:** 2026-05-01

## Summary

| PR | Verdict |
|----|---------|
| **#12958** Admin CSV exports | **PARTIAL — 1 broken endpoint** |
| **#12959** TOP_UP misclassification fix | **PASS** |

The credit-transactions export and the include_inactive filter behave exactly as PR'd. The **copilot-usage export endpoint is broken in the deployed dev build** — every request returns HTTP 500 due to a `'str' object has no attribute 'tzinfo'` error.

## PASS/FAIL table

| ID | Scenario | Result | Evidence |
|----|----------|--------|----------|
| PR12958-API-1 | `/transactions/export` 30-day window | PASS | HTTP 200, 9046 rows, 5 067 874 bytes JSON |
| PR12958-API-2 | `transaction_type=TOP_UP` filter | PASS | 6 rows, all `transaction_type=TOP_UP` |
| PR12958-API-3 | `user_id` filter | PASS | 4584 rows, all single user |
| PR12958-API-4 | `include_inactive=true` returns more rows | PASS | 9056 vs 9046 (Δ +10) |
| PR12958-API-5 | 90-day window cap → 400 | PASS | `{"detail":"Export window must be <= 90 days (got 484.00 days)"}` |
| PR12958-API-6 | Missing `start` → 400 | PASS | `{"detail":"start and end query params are required"}` |
| PR12958-API-7 | No auth → 401 | PASS | `{"detail":"Authorization header is missing"}` |
| PR12958-API-8 | `/copilot-usage/export` happy path | **FAIL** | HTTP 500 — `'str' object has no attribute 'tzinfo'` |
| PR12958-API-9 | `/copilot-usage/export` 90-day cap | PASS | 400 returned before the bug surfaces |
| PR12958-UI-1  | Dashboard shows both Export buttons | PASS | screenshot `03-post-login.png` |
| PR12958-UI-2  | Export CSV dialog shows new fields | PASS | screenshot `09-current.png` (start/end date, transaction-type select, user-id input, "Window is capped at 90 days and 100k rows" hint) |
| PR12959-API-1 | Default export hides `isActive=false` rows | PASS | 9046 default vs 9056 inactive (10 phantom rows hidden) |
| PR12959-API-2 | `include_inactive=true` reveals abhimanyu's Nov-29 phantom row | PASS | `abhimanyu.yadav@agpt.co 2025-11-29T13:05:19.954000Z amount=4000 balance=2062` only present when `include_inactive=true` |
| PR12959-API-3 | mumeenonimisi phantom row hidden by default | PASS | 0 matches in default; (no current rows in `include_inactive` either inside the test window — abhimanyu was the actual matched phantom) |

Total: **13 PASS / 1 FAIL.**

## Failure detail — PR #12958 copilot-usage export

```bash
$ curl -H "Authorization: Bearer $TOKEN" \
  "https://dev-server.agpt.co/api/credits/admin/copilot-usage/export?start=2026-04-01T00:00:00Z&end=2026-04-30T00:00:00Z"
{"message":"Failed to process GET /api/credits/admin/copilot-usage/export",
 "detail":"'str' object has no attribute 'tzinfo'",
 "hint":"Check server logs and dependent services."}
```

Stack-trace points to `autogpt_platform/backend/backend/data/platform_cost.py:822`:

```python
for r in rows:
    week_start: datetime = r["week_start"]   # <- annotated as datetime, but Prisma raw query returns str
    if week_start.tzinfo is None:            # <- AttributeError: 'str' object has no attribute 'tzinfo'
        week_start = week_start.replace(tzinfo=timezone.utc)
```

The raw SQL `AT TIME ZONE 'UTC'` on the week_start column is being deserialised as a string by the Prisma raw query, not as a `datetime`. The annotation on line 821 doesn't actually cast the value — it's a type-checker hint only. Need to call `datetime.fromisoformat(r["week_start"])` (or use `cast`) before the `.tzinfo` check.

The bug is reachable from the **Copilot Usage CSV** dialog on `/admin/spending`. Any admin pressing Download will get a toast error and an empty CSV. Worth a hot-fix follow-up.

## What was tested how

**API tests:** direct HTTPS curl against `https://dev-server.agpt.co/api/credits/admin/...` with a Supabase JWT obtained via `/auth/v1/token?grant_type=password` against the dev project at `adfjtextkuilwuhzdjpf.supabase.co`. Same JWT used my admin user (zamil.majdy@gmail.com) — confirmed admin role since 401 is returned for missing token but 200 when present.

**UI tests:** screenshots taken from a localhost build of the dev branch (a sibling Next.js dev server on :3001 was intercepting agent-browser navigation to dev-builder.agpt.co — the Vercel deploy then redirected back to localhost via shared Supabase auth state). The localhost build is the same dev branch HEAD (`09cb340acd`) so the UI evidence is representative; the **feature-correctness verification was done against the dev backend directly via API**.

## Screenshots

- `01-login-page.png` — initial login page
- `02-login-filled.png` — login form filled
- `03-post-login.png` — `/admin/spending` showing both new "Export CSV" and "Copilot Usage CSV" buttons in the page header
- `09-current.png` — Export CSV dialog open, showing start date, end date, transaction-type select, user-id (optional) input, and "Window is capped at 90 days and 100k rows. Narrow the range if the backend returns a 400." hint
- `06`/`07`/`10`/`11`/`12`/`13` — intermediate browser-redirect debugging screenshots
