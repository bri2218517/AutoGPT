# Test plan — PR #12958 + PR #12959 (dev environment)

**Target:** `https://dev-builder.agpt.co` / `https://dev-server.agpt.co`
**Commit:** `09cb340acd` (top of `origin/dev`)
**Tester:** zamil.majdy@gmail.com
**Date:** 2026-05-01

## PR #12958 — Admin CSV exports
- [PR12958-API-1] `GET /api/credits/admin/transactions/export` returns 200 with JSON `{transactions: [...], ...}` for a 30-day window.
- [PR12958-API-2] `transaction_type=TOP_UP` filter returns rows with only that type.
- [PR12958-API-3] `user_id` filter returns rows for only that user.
- [PR12958-API-4] `include_inactive=true` returns more rows than default (proves PR #12959 isActive default-false filter).
- [PR12958-API-5] `start − end > 90 days` returns HTTP 400 with `Export window must be <= 90 days`.
- [PR12958-API-6] Missing `start` returns HTTP 400.
- [PR12958-API-7] No auth header returns HTTP 401.
- [PR12958-API-8] `GET /api/credits/admin/copilot-usage/export` returns 200 with rows for a 30-day window.
- [PR12958-API-9] Same 90-day cap on `/copilot-usage/export`.
- [PR12958-UI-1] `/admin/spending` shows two header buttons: "Export CSV" and "Copilot Usage CSV".
- [PR12958-UI-2] Export CSV dialog includes start date, end date, transaction-type select, user-id input, and a 90-day/100k-row hint.

## PR #12959 — TOP_UP misclassification + dashboard polish
- [PR12959-API-1] Default export hides `isActive=false` ledger rows (phantom TOP_UPs from abandoned Stripe checkouts).
- [PR12959-API-2] `include_inactive=true` reveals abhimanyu.yadav@agpt.co's Nov-29 phantom TOP_UP row from the bug report.
- [PR12959-API-3] mumeenonimisi@gmail.com's phantom row not present in default TOP_UP export.

## Method
- Auth via Supabase REST `/auth/v1/token?grant_type=password` against `https://adfjtextkuilwuhzdjpf.supabase.co` (the dev project) → JWT.
- Bearer token sent to `dev-server.agpt.co` API.
- UI screenshots taken from a localhost build of the same dev branch (the agent-browser session kept getting redirected from dev-builder.agpt.co to localhost:3001 due to a sibling `next dev` listener; the **actual feature verification was done against dev-server.agpt.co directly**).
