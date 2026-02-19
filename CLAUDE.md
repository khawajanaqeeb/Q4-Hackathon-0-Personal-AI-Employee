# Personal AI Employee — Claude Code Instructions

## Project Overview

This is a **Personal AI Employee** (Digital FTE) — Bronze Tier.
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
├── Approved/             ← Human-approved actions (watcher monitors)
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

## Workflow

```
Inbox → Watcher → Needs_Action → Claude reads → Plans/ → Pending_Approval/ → (Human approves) → Approved/ → Action → Done/
```

## Agent Skills (Slash Commands)

| Command | Description |
|---------|-------------|
| `/process-inbox` | Process all items in Needs_Action |
| `/update-dashboard` | Refresh Dashboard.md with current stats |
| `/morning-briefing` | Generate weekly CEO briefing |
| `/start-watcher` | Start the file system watcher |

## Python Watchers

```bash
# Start filesystem watcher (Bronze Tier — no API key needed)
python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault

# Start with dry-run (logs only, no file operations)
python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault --dry-run

# Gmail watcher (requires Google API credentials)
python3 watchers/gmail_watcher.py --vault AI_Employee_Vault
```

## Security

- Never commit `.env` files
- Credentials go in `.env` (already in `.gitignore`)
- All sensitive actions require human approval (HITL)
- Payments > $100 always require approval regardless of automation level

## Task Completion Checklist

A task is **Done** when:
- [ ] Action executed (or approval created)
- [ ] Event logged in `Logs/<date>.json`
- [ ] Dashboard.md updated
- [ ] Source file moved from `Needs_Action/` to `Done/`
