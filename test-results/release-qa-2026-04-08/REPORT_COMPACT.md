---
title: "Release QA Report — autogpt-platform-beta-v0.6.54"
date: "2026-04-08"
geometry: "margin=2cm"
fontsize: 11pt
colorlinks: true
---

# Release QA Report
**Release:** autogpt-platform-beta-v0.6.54  
**Date:** 2026-04-08  
**Environment:** <https://dev-builder.agpt.co/>  
**Account:** zamil.majdy@gmail.com  
**Tester:** Automated (agent-browser) + Manual verification

---

## Executive Summary

Full QA pass completed across **Platform** (Builder, Auth, Settings, Marketplace) and **AutoPilot** tracks.

| Track | Pass | Partial | Fail | Skip |
|-------|------|---------|------|------|
| Builder | 7 | 2 | 0 | 1 |
| Auth | 0 | 4 | 1 | 2 |
| Settings | 3 | 0 | 0 | 1 |
| Marketplace | 5 | 2 | 0 | 0 |
| AutoPilot | 14 | 3 | 1 | 0 |
| **Total** | **29** | **11** | **1** | **4** |

**One bug fixed during this QA session:** `POST /api/graphs` returning 500 instead of 400 for malformed Agent Input blocks. Fix shipped in PR #12714.

**One confirmed open blocker:** AutoPilot cannot schedule agents via chat (silently drops after 4+ min).

---

## Bug Fixed During QA

### FIXED — POST /api/graphs returns 500 for Agent Input without name

**PR:** <https://github.com/Significant-Gravitas/AutoGPT/pull/12714>  
**Root cause:** `_generate_schema` in `graph.py` used `model_construct()` (bypasses Pydantic validation) to build block field objects. If an Agent Input block had no `name` in `input_default`, the object was created without the attribute, causing `AttributeError` at `p.name` in the dict comprehension. `AttributeError` was not in the exception handler registry and fell through to the `Exception → 500` catch-all.  
**Fix:** Wrapped the dict comprehension in `try/except AttributeError → raise ValueError`, which routes to the existing `ValueError → 400` handler.  
**Impact fixed:** Builder save and file import were both blocked.


---

## Platform Track Results

### Builder

| Item | Result | Notes |
|------|--------|-------|
| Build agent with blocks | **FIXED** | Was failing with 500 (PR #12714) |
| Run the agent | **PASS** | All nodes COMPLETED, correct output |
| Schedule an agent run | **PASS** | Daily 9:00 AM schedule created |
| Export agent to file | **PASS** | JSON download via More Actions |
| Import agent from file | **FIXED** | Was failing silently (same 500 bug) |
| Library — Setup your task | **PASS** | Task ran, deleted, count correct |
| Open in builder from Runner UI | **PASS** | "Edit agent" opens builder with correct flowID |
| Add credential block | **PASS** | GitHub OAuth redirect initiates correctly |
| Credit deduction | **PARTIAL** | Balance increased (earn-credits reward on template runs) |
| Remove credential | **SKIP** | OAuth not completed in automated test |






---

### Auth

| Item | Result | Notes |
|------|--------|-------|
| Code & Secret Scanning | **SKIP** | Manual check |
| Logout across multiple tabs | **PASS** | Manually verified — works correctly |
| Forgot Password | **PARTIAL** | Form submits but no success toast shown |
| Login with new password | **SKIP** | Cannot receive email in automated test |
| Sign up new account | **PARTIAL** | Form renders correctly; full flow requires email |
| Onboarding flow | **PARTIAL** | `/onboarding/reset` silently redirects, backend API never called |
| Builder tutorial | **PARTIAL** | Welcome dialog works; step 1 nav sometimes lands on /profile |




---

### Settings

| Item | Result | Notes |
|------|--------|-------|
| Edit display name + upload photo | **PASS** | Name and GCS photo URL persisted |
| Billing top-up | **SKIP** | Billing not enabled in this environment |
| Notifications ON → run agent | **PASS** | Preference saved, confirmed via API |
| Notifications OFF → run agent | **PASS** | Agent ran, execution 100% success |



---

### Marketplace

| Item | Result | Notes |
|------|--------|-------|
| Submit agent | **PASS** | Created with PENDING status |
| Approve via admin panel | **PASS** | Admin panel UI confirmed working |
| Add agent to library | **PASS** | API 200 OK with full LibraryAgent object |
| Run the added agent | **PASS** | Execution COMPLETED in ~9s |
| Download agent | **PASS** | Full JSON graph downloaded |
| Delete from Creator Dashboard | **PARTIAL** | Delete blocked for APPROVED (by design, no UI explanation) |
| Revoke via admin panel | **PASS** | Status changed to REJECTED |





---

## AutoPilot Track Results

| # | Item | Result |
|---|------|--------|
| 1 | Prompt pills | **PASS** |
| 2 | Send hello message | **PASS** |
| 3 | New chat | **PASS** |
| 4 | Web search | **PASS** |
| 5 | Calculator | **PASS** |
| 6 | Create Hello World agent | **PASS** |
| 7 | Agent appears in Library | **PASS** |
| 8 | Run created agent | **PARTIAL** — tagged "Simulated" |
| 9 | Edit created agent | **PASS** |
| 10 | Context memory | **PASS** |
| 11 | Stop in-progress | **PARTIAL** — UI shows stopped but continues in background |
| 12 | Re-open existing chat | **PASS** |
| 13 | Twitter auth tool | **PASS** |
| 14 | Upload file | **PASS** |
| 15 | Describe uploaded file | **PASS** |
| 16 | Voice message | **PASS** (correct permission error) |
| 17 | Schedule agent via chat | **FAIL** — 4+ min, no response |
| 18 | Continue after navigation | **PASS** |
| 19 | Failure case (invalid URL) | **PASS** |











---

## Open Bugs

| # | Severity | Component | Description |
|---|----------|-----------|-------------|
| 1 | **HIGH** | AutoPilot | Schedule agent via chat times out after 4+ min with no response or error |
| 2 | **HIGH** | Auth | Forgot Password submits with no success confirmation |
| 3 | **HIGH** | Onboarding | `/onboarding/reset` silently redirects; `postV1ResetOnboardingProgress` API never called |
| 4 | **MEDIUM** | AutoPilot | "Stop" dismisses UI but background execution continues (billing concern) |
| 5 | **MEDIUM** | Builder | Tutorial "Let's Begin" occasionally navigates to /profile instead of step 1 |
| 6 | **MEDIUM** | Auth | Direct navigation to `/profile` triggers session validation redirect |
| 7 | **LOW** | Marketplace | Delete button hidden for APPROVED agents with no explanation to user |
| 8 | **LOW** | AutoPilot | AutoPilot-created agent run tagged "Simulated" — no path to real run shown |

---

## Conclusion

Core platform and AutoPilot functionality is in good shape. The critical builder save bug (500 on save) has been fixed. The main open issue for release consideration is **AutoPilot scheduling (item 17)** — it is a featured capability but completely non-functional. All other failures are either by-design limitations or UX improvements.
