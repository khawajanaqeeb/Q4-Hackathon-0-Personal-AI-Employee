---
last_updated: 2026-02-20 03:09
auto_refresh: true
owner: AI Employee v0.1
---

# AI Employee Dashboard

> **Status:** 🟢 Operational | **Mode:** Local-First | **Tier:** Bronze

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Needs Action | 0 items |
| Pending Approval | 0 items |
| Done This Week | 3 tasks |
| Active Plans | 0 active, 2 closed |
| Invoiced (MTD) | $1,500.00 |

---

## Inbox Status

- **Items in /Inbox:** 0 files (cleared)
- **Items in /Needs_Action:** 0 actionable files
- **Items in /Pending_Approval:** 0 — all clear

---

## Recent Activity

| Time | Event | Detail |
|------|-------|--------|
| 2026-02-20 03:09 | ✅ Invoice generated | INV-2026-001 — $1,500.00 — Client A |
| 2026-02-20 03:09 | 👤 Human approved | APPROVAL_invoice_client_a → Approved |
| 2026-02-20 03:09 | 📒 Transaction logged | Accounting/2026-02_transactions.md updated |
| 2026-02-20 02:00 | 📋 Inbox reviewed | 2 files processed by AI Employee |
| 2026-02-20 02:00 | ⏳ Approval requested | APPROVAL_invoice_client_a — $1,500 invoice |

---

## Active Plans

| Plan | Priority | Status |
|------|----------|--------|
| [PLAN_invoice_client_a.md](Plans/PLAN_invoice_client_a.md) | P1 | ✅ Complete — invoice ready to send |
| [PLAN_task_test.md](Plans/PLAN_task_test.md) | P3 | ✅ Completed |

---

## System Health

| Component | Status |
|-----------|--------|
| File System Watcher | ✅ Tested & working |
| Obsidian Vault | ✅ Ready |
| Claude Code | ✅ Connected |
| Pending Approval Queue | ✅ All clear |

---

## How to Use

1. **Drop files** into `/Inbox/` — the watcher detects them and creates action items
2. **Review** `/Needs_Action/` — Claude processes and creates plans
3. **Approve** items in `/Pending_Approval/` by moving them to `/Approved/`
4. **Monitor** completed work in `/Done/`

---

## Agent Skills Available

| Skill | Command | Description |
|-------|---------|-------------|
| Process Inbox | `/process-inbox` | Process all items in Needs_Action |
| Update Dashboard | `/update-dashboard` | Refresh this dashboard |
| Morning Briefing | `/morning-briefing` | Generate CEO briefing |

---

_Last updated by: AI Employee v0.1 · Bronze Tier_
