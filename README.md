# Personal AI Employee — Bronze Tier

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A **Digital FTE (Full-Time Equivalent)** powered by Claude Code and Obsidian. This Bronze Tier implementation provides the foundational layer: an Obsidian vault, a working file system watcher, and Claude Code agent skills.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              PERSONAL AI EMPLOYEE (Bronze)          │
└─────────────────────────────────────────────────────┘

External Input (you drop files)
         │
         ▼
  AI_Employee_Vault/Inbox/
         │
         ▼ (FileSystemWatcher detects)
  AI_Employee_Vault/Needs_Action/   ← .md action files
         │
         ▼ (Claude Code reads)
  AI_Employee_Vault/Plans/          ← reasoning plans
         │
    ┌────┴────┐
    ▼         ▼
 Auto-OK  Needs Approval
    │         │
    │    Pending_Approval/ ← human reviews
    │         │
    ▼         ▼ (human moves to /Approved)
  Done/    Action Executed → Done/
```

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.12+
python3 --version

# Install dependencies
pip install watchdog python-dotenv
# or with uv:
uv sync
```

### 2. Open Vault in Obsidian

Open Obsidian → "Open folder as vault" → select `AI_Employee_Vault/`

### 3. Start the Watcher

```bash
# From project root
python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault
```

Or use the agent skill in Claude Code:
```
/start-watcher
```

### 4. Drop a File

Drop any file into `AI_Employee_Vault/Inbox/`. Within 3 seconds you'll see:
- A `.md` action file in `Needs_Action/`
- A log entry in `Logs/<today>.json`

### 5. Process with Claude Code

Run Claude Code from the project root:
```bash
claude
```

Then use the agent skills:
```
/process-inbox          # Process all pending items
/update-dashboard       # Refresh your dashboard
/morning-briefing       # Generate CEO briefing
```

---

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md              ← Real-time status (open in Obsidian)
├── Company_Handbook.md       ← AI Employee rules of engagement
├── Business_Goals.md         ← Revenue targets & KPIs
├── Inbox/                    ← Drop files here
├── Needs_Action/             ← Watcher creates .md files here
├── Done/                     ← Completed tasks
├── Plans/                    ← Claude's reasoning plans
├── Logs/                     ← Structured JSON audit logs
├── Pending_Approval/         ← Awaiting your approval
├── Approved/                 ← Move files here to approve
├── Rejected/                 ← Move files here to reject
├── Briefings/                ← CEO briefings
└── Accounting/               ← Financial data
```

---

## Agent Skills

| Skill | Command | Purpose |
|-------|---------|---------|
| Process Inbox | `/process-inbox` | Read Needs_Action, create plans, handle tasks |
| Update Dashboard | `/update-dashboard` | Refresh Dashboard.md stats |
| Morning Briefing | `/morning-briefing` | Weekly CEO briefing |
| Start Watcher | `/start-watcher` | Launch filesystem watcher |

---

## Watcher Scripts

| Script | Description | API Key? |
|--------|-------------|----------|
| `filesystem_watcher.py` | Monitors /Inbox for dropped files | No |
| `gmail_watcher.py` | Monitors Gmail for important emails | Yes (Google) |

### Filesystem Watcher Options

```bash
python3 watchers/filesystem_watcher.py --help

Options:
  --vault PATH     Path to AI_Employee_Vault (default: ./AI_Employee_Vault)
  --dry-run        Log actions without creating files

Environment:
  DRY_RUN=true     Same as --dry-run
```

### Gmail Watcher Setup (Optional)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Enable Gmail API
3. Create OAuth 2.0 credentials (Desktop app)
4. Download `credentials.json` to `watchers/`
5. Run: `python3 watchers/gmail_watcher.py --vault AI_Employee_Vault`
6. Authorize in browser on first run

---

## Security

- **Credentials**: Never stored in the vault. Use `.env` file only.
- **HITL**: All external actions (email, payments) require human approval.
- **Audit Trail**: Every action logged to `Logs/<date>.json`.
- **Local-First**: All data stays on your machine.

```bash
# .env template (never commit this)
cp .env.example .env
# Edit .env with your credentials
```

---

## Human-in-the-Loop Workflow

1. Claude creates `Pending_Approval/APPROVAL_<action>.md`
2. You review it in Obsidian
3. Move the file to `Approved/` to proceed, or `Rejected/` to cancel
4. Claude detects the move and executes (or cancels)

---

## Bronze Tier Checklist

- [x] Obsidian vault with `Dashboard.md` and `Company_Handbook.md`
- [x] Folder structure: `/Inbox`, `/Needs_Action`, `/Done`
- [x] Working filesystem watcher (no API key required)
- [x] Claude Code reads from and writes to the vault
- [x] All AI functionality implemented as Agent Skills

---

## Tier Roadmap

| Tier | Status | Features |
|------|--------|---------|
| **Bronze** | ✅ Complete | Vault + Watcher + Agent Skills |
| Silver | 🔲 Next | Gmail + WhatsApp + LinkedIn + MCP |
| Gold | 🔲 Future | Full autonomy + Odoo + CEO briefings |
| Platinum | 🔲 Future | Cloud 24/7 + multi-agent |

---

## Tech Stack

- **Brain**: Claude Code (`claude-sonnet-4-6`)
- **Memory/GUI**: Obsidian (local Markdown)
- **Senses**: Python watchdog (filesystem), Google Gmail API
- **Project**: UV / pip

---

*Personal AI Employee Hackathon 0 — Bronze Tier — Built with Claude Code*
