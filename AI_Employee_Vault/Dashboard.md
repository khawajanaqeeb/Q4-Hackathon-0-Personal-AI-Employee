---
last_updated: 2026-02-20 15:47
auto_refresh: true
owner: AI Employee v0.1
---

# AI Employee Dashboard

> **Status:** 🟢 Operational | **Mode:** Local-First | **Tier:** Silver ✅

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Needs Action | 0 items |
| Pending Approval | 1 item |
| Done This Week | 6 tasks |
| Active Plans | 1 active, 3 closed |
| Invoiced (MTD) | $1,500.00 |

---

## Inbox Status

- **Items in /Inbox:** 0 files (cleared)
- **Items in /Needs_Action:** 0 actionable files ✅ Clear
- **Items in /Pending_Approval:** 1 — awaiting your review 👤
  - `EMAIL_INV-2026-001_Client_A_20260220.md` — Invoice email to client_a@email.com ($1,500)

---

## Recent Activity

| Time | Event | Detail |
|------|-------|--------|
| 2026-02-20 15:47 | 📧 Email approval created | EMAIL_INV-2026-001 → Pending_Approval/ (Silver Tier email send ready) |
| 2026-02-20 15:47 | 🗂️ P3 files archived | FILE_PLAN_task_test + FILE_task-test → Done/ (stale files) |
| 2026-02-20 15:47 | 📋 Inbox processed | 3 items reviewed — 1 approval created, 2 archived |
| 2026-02-20 03:09 | ✅ Invoice generated | INV-2026-001 — $1,500.00 — Client A |
| 2026-02-20 03:09 | 👤 Human approved | APPROVAL_invoice_client_a → Approved |
| 2026-02-20 03:09 | 📒 Transaction logged | Accounting/2026-02_transactions.md updated |
| 2026-02-20 02:00 | 📋 Inbox reviewed | 2 files processed by AI Employee |

---

## Active Plans

| Plan | Priority | Status |
|------|----------|--------|
| [PLAN_invoice_client_a.md](Plans/PLAN_invoice_client_a.md) | P1 | ⏳ Awaiting email send approval |
| [PLAN_inbox_triage_20260220.md](Plans/PLAN_inbox_triage_20260220.md) | P3 | ✅ Completed |
| [PLAN_task_test.md](Plans/PLAN_task_test.md) | P3 | ✅ Completed |

---

## Pending Approvals — Action Required 👤

| File | Action | Amount | Expires |
|------|--------|--------|---------|
| `EMAIL_INV-2026-001_Client_A_20260220.md` | Send invoice email to client_a@email.com | $1,500 | 2026-02-21 |

**To approve:** Move file from `/Pending_Approval/` → `/Approved/`
**To review:** Run `/approve-pending` in Claude Code

---

## System Health

| Component | Status |
|-----------|--------|
| File System Watcher | ✅ Tested & working |
| Gmail Watcher | ⚙️ Ready (needs credentials) |
| LinkedIn Watcher | ⚙️ Ready (needs credentials) |
| WhatsApp Watcher | ⚙️ Ready (run --setup for QR) |
| Orchestrator | ✅ Running |
| Email MCP Server | ✅ Ready (needs SMTP config) |
| Obsidian Vault | ✅ Ready |
| Claude Code | ✅ Connected |

---

## Agent Skills Available

| Skill | Command | Tier |
|-------|---------|------|
| Process Inbox | `/process-inbox` | Bronze |
| Update Dashboard | `/update-dashboard` | Bronze |
| Morning Briefing | `/morning-briefing` | Bronze |
| Start Watcher | `/start-watcher` | Bronze |
| LinkedIn Post | `/linkedin-post` | Silver |
| Approve Pending | `/approve-pending` | Silver |
| Run Orchestrator | `/run-orchestrator` | Silver |

---

_Last updated by: AI Employee v0.1 · Silver Tier · /process-inbox_
