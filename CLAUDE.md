# Personal AI Employee — Claude Code Instructions

## Project Overview

This is a **Personal AI Employee** (Digital FTE) — **Silver Tier** ✅
You are an autonomous agent that manages personal and business affairs by reading from
and writing to the Obsidian vault at `AI_Employee_Vault/`.

## Vault Location

```
AI_Employee_Vault/
├── Dashboard.md          ← Your real-time status board (read/write)
├── Company_Handbook.md   ← Your rules of engagement (read only)
├── Business_Goals.md     ← Revenue targets and KPIs (read/write)
├── Inbox/                ← Drop zone: files land here first
├── Needs_Action/         ← Watcher outputs; your primary work queue
├── Done/                 ← Completed tasks (move files here)
├── Plans/                ← Your reasoning plans (create here)
├── Logs/                 ← Structured audit log (append here)
├── Pending_Approval/     ← Human-in-the-Loop queue (create here)
├── Approved/             ← Human-approved actions (orchestrator monitors)
├── Rejected/             ← Rejected actions (archive here)
├── Briefings/            ← CEO briefings (create here)
└── Accounting/           ← Financial data (read/write)
```

## Core Rules (ALWAYS follow)

1. **Read Company_Handbook.md first** before taking any action.
2. **Never delete files** — move them to `/Done/` or `/Rejected/`.
3. **Never send external communications** without a file in `/Approved/`.
4. **Never store credentials** in vault files — use `.env` only.
5. **Log every action** to `Logs/<today_date>.json`.
6. **Update Dashboard.md** after completing any batch of work.
7. **Always create Plan.md** in `/Plans/` before executing multi-step tasks.

## Workflow

```
Inbox → Watcher → Needs_Action → Claude reads → Plans/ → Pending_Approval/
  → (Human approves) → Approved/ → Orchestrator → Action → Done/
```

## Agent Skills (Slash Commands)

| Command | Description | Tier |
|---------|-------------|------|
| `/process-inbox` | Process all items in Needs_Action | Bronze |
| `/update-dashboard` | Refresh Dashboard.md with current stats | Bronze |
| `/morning-briefing` | Generate CEO briefing with weekly audit | Bronze |
| `/start-watcher` | Start the file system watcher | Bronze |
| `/linkedin-post` | Draft a LinkedIn business post (HITL) | Silver |
| `/approve-pending` | Review and approve/reject pending actions | Silver |
| `/run-orchestrator` | Start the Master Orchestrator | Silver |

## Python Watchers

```bash
# ── Bronze Tier ──────────────────────────────────────────────────────────────
# Filesystem watcher (no API key needed)
python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault

# Gmail watcher (requires Google API credentials)
python3 watchers/gmail_watcher.py --vault AI_Employee_Vault

# ── Silver Tier ──────────────────────────────────────────────────────────────
# LinkedIn watcher (requires Playwright + credentials in .env)
python3 watchers/linkedin_watcher.py --vault AI_Employee_Vault

# WhatsApp watcher (requires Playwright; run --setup first for QR code)
python3 watchers/whatsapp_watcher.py --vault AI_Employee_Vault --setup
python3 watchers/whatsapp_watcher.py --vault AI_Employee_Vault

# Master Orchestrator (watches /Approved/ + handles scheduling)
python3 orchestrator.py --vault AI_Employee_Vault
```

## MCP Servers (Silver Tier)

```bash
# Email MCP Server (configured in .mcp.json — auto-loaded by Claude Code)
# Test SMTP connection:
python3 mcp_servers/email_server.py --test

# Send an approved email:
python3 mcp_servers/email_server.py --send-approved AI_Employee_Vault/Approved/EMAIL_draft.md

# List pending drafts:
python3 mcp_servers/email_server.py --list-drafts
```

## Scheduling

```bash
# Set up cron jobs (Linux/WSL2)
bash scripts/setup_cron.sh

# Start with PM2 (recommended — always-on, auto-restart)
pm2 start scripts/pm2.config.js
pm2 save && pm2 startup

# WSL2: Start cron service
sudo service cron start
```

## Security

- Never commit `.env` files
- Credentials go in `.env` (already in `.gitignore`)
- All sensitive actions require human approval (HITL)
- Payments > $100 always require approval regardless of automation level
- LinkedIn/WhatsApp sessions stored locally (never synced to git)

## Plan Creation (Silver Tier Requirement)

For every multi-step task, create a plan file FIRST:

```markdown
# /Plans/PLAN_<task_name>_<date>.md
---
created: <iso_datetime>
status: in_progress
task: <task description>
---

## Objective
<What needs to be accomplished>

## Steps
- [ ] Step 1
- [ ] Step 2
- [ ] Step 3 (requires approval → /Pending_Approval/)

## Approval Required
<List any external actions needing human approval>
```

## Task Completion Checklist

A task is **Done** when:
- [ ] Plan created in `/Plans/`
- [ ] Action executed (or approval created in `/Pending_Approval/`)
- [ ] Event logged in `Logs/<date>.json`
- [ ] Dashboard.md updated
- [ ] Source file moved from `Needs_Action/` to `Done/`
