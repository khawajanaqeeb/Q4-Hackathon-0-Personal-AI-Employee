# Personal AI Employee — Silver Tier ✅

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A **Digital FTE (Full-Time Equivalent)** powered by Claude Code and Obsidian. The Silver Tier adds LinkedIn automation, WhatsApp monitoring, an Email MCP Server, an Orchestrator, and full scheduling — transforming the Bronze foundation into a **Functional Assistant**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              PERSONAL AI EMPLOYEE (Silver Tier)                 │
└─────────────────────────────────────────────────────────────────┘

External Sources (Gmail, LinkedIn, WhatsApp, File drops)
         │
         ▼
  ┌──────────────────────────────────────────┐
  │           PERCEPTION LAYER               │
  │  filesystem_watcher.py (Bronze)          │
  │  gmail_watcher.py      (Bronze/Silver)   │
  │  linkedin_watcher.py   (Silver) ← NEW    │
  │  whatsapp_watcher.py   (Silver) ← NEW    │
  └──────────────────────────────────────────┘
         │ creates .md action files
         ▼
  AI_Employee_Vault/Needs_Action/
         │
         ▼ (Claude Code reads)
  AI_Employee_Vault/Plans/     ← reasoning plans
         │
         ▼
  AI_Employee_Vault/Pending_Approval/   ← human reviews
         │
         ▼ (human moves to /Approved/)
  ┌──────────────────────────────────────────┐
  │         ORCHESTRATOR  ← NEW             │
  │  Watches /Approved/ → routes actions     │
  │  • Email → Email MCP Server             │
  │  • LinkedIn post → linkedin_watcher     │
  │  • Generic → log + move to Done/        │
  └──────────────────────────────────────────┘
         │
         ▼
  External Actions (email sent, LinkedIn posted)
         │
         ▼
  AI_Employee_Vault/Done/   + Logs/<date>.json
```

---

## Quick Start

### 1. Prerequisites

```bash
# Python 3.12+
python3 --version

# Install core dependencies
pip3 install watchdog python-dotenv --break-system-packages

# Optional: Playwright (for LinkedIn/WhatsApp watchers)
pip3 install playwright --break-system-packages
playwright install chromium

# Optional: Node.js + PM2 (for always-on process management)
npm install -g pm2
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your SMTP, LinkedIn, Gmail credentials
```

### 3. Open Vault in Obsidian

Open Obsidian → "Open folder as vault" → select `AI_Employee_Vault/`

### 4. Start the Orchestrator

```bash
# Start orchestrator (watches /Approved/ + handles scheduling)
python3 orchestrator.py --vault AI_Employee_Vault
```

Or use PM2 for always-on operation:
```bash
pm2 start scripts/pm2.config.js
pm2 save && pm2 startup
```

### 5. Run Agent Skills in Claude Code

```bash
claude
```

```
/process-inbox       # Process all pending items
/update-dashboard    # Refresh your dashboard
/morning-briefing    # Generate CEO briefing
/linkedin-post       # Draft a LinkedIn business post
/approve-pending     # Review all items awaiting approval
/run-orchestrator    # Start the Orchestrator (instructions)
```

---

## Vault Structure

```
AI_Employee_Vault/
├── Dashboard.md              ← Real-time status (open in Obsidian)
├── Company_Handbook.md       ← AI Employee rules of engagement
├── Business_Goals.md         ← Revenue targets & KPIs
├── Inbox/                    ← Drop files here (FileSystemWatcher monitors)
├── Needs_Action/             ← Watchers create .md files here
├── Done/                     ← Completed tasks
├── Plans/                    ← Claude's reasoning plans (REQUIRED per task)
├── Logs/                     ← Structured JSON audit logs
├── Pending_Approval/         ← Awaiting your approval
├── Approved/                 ← Move files here to approve → Orchestrator acts
├── Rejected/                 ← Move files here to reject
├── Briefings/                ← CEO briefings
└── Accounting/               ← Financial data
```

---

## Agent Skills

| Skill | Command | Tier |
|-------|---------|------|
| Process Inbox | `/process-inbox` | Bronze |
| Update Dashboard | `/update-dashboard` | Bronze |
| Morning Briefing | `/morning-briefing` | Bronze |
| Start Watcher | `/start-watcher` | Bronze |
| **LinkedIn Post** | **`/linkedin-post`** | **Silver** |
| **Approve Pending** | **`/approve-pending`** | **Silver** |
| **Run Orchestrator** | **`/run-orchestrator`** | **Silver** |

---

## Watcher Scripts

| Script | Description | Credentials |
|--------|-------------|-------------|
| `filesystem_watcher.py` | Monitors /Inbox for dropped files | None |
| `gmail_watcher.py` | Monitors Gmail for important emails | Google OAuth |
| `linkedin_watcher.py` | Monitors LinkedIn + posts content | LinkedIn login |
| `whatsapp_watcher.py` | Monitors WhatsApp Web messages | QR scan (once) |

### Quick Start per Watcher

```bash
# Filesystem (Bronze — always-on, no credentials)
python3 watchers/filesystem_watcher.py --vault AI_Employee_Vault

# Gmail (requires credentials.json from Google Cloud Console)
python3 watchers/gmail_watcher.py --vault AI_Employee_Vault

# LinkedIn (requires LINKEDIN_EMAIL + LINKEDIN_PASSWORD in .env)
python3 watchers/linkedin_watcher.py --vault AI_Employee_Vault

# Post an approved LinkedIn post
python3 watchers/linkedin_watcher.py \
  --vault AI_Employee_Vault \
  --post-file AI_Employee_Vault/Approved/LINKEDIN_POST_2026-02-20.md

# WhatsApp (scan QR code once)
python3 watchers/whatsapp_watcher.py --vault AI_Employee_Vault --setup
python3 watchers/whatsapp_watcher.py --vault AI_Employee_Vault
```

---

## MCP Server: Email (Silver Tier)

The Email MCP Server exposes email tools to Claude Code via the Model Context Protocol (JSON-RPC 2.0 over stdio).

**Tools:**
- `send_email` — Send via SMTP (requires prior human approval)
- `draft_email` — Save to /Pending_Approval/ (no approval needed)
- `list_drafts` — List pending drafts

**Setup:**
```bash
# 1. Configure SMTP in .env (Gmail App Password recommended)
# 2. Test connection
python3 mcp_servers/email_server.py --test

# 3. Register with Claude Code (project-level .mcp.json already configured)
# Claude Code will auto-load this when you run 'claude' from the project root

# 4. Send an approved email
python3 mcp_servers/email_server.py --send-approved AI_Employee_Vault/Approved/EMAIL_draft.md
```

---

## Scheduling

### Option A: Orchestrator (built-in)
The Orchestrator runs all scheduled tasks internally:
- Every 30 min: `/process-inbox`
- Every hour: `/update-dashboard`
- Daily @ 8 AM: `/morning-briefing`
- Sunday @ 7 PM: Weekly audit

### Option B: Cron (Linux/WSL2)
```bash
bash scripts/setup_cron.sh        # Install
bash scripts/setup_cron.sh --list # View
bash scripts/setup_cron.sh --remove # Remove

# WSL2: Start cron
sudo service cron start
```

### Option C: PM2 (Recommended for always-on)
```bash
npm install -g pm2
pm2 start scripts/pm2.config.js
pm2 save && pm2 startup
pm2 status    # View all processes
pm2 logs      # Tail logs
```

---

## Security

- **Credentials**: Stored in `.env` only (`.gitignore`d). Never in the vault.
- **HITL**: All external actions require a file in `/Approved/` first.
- **Audit Trail**: Every action logged to `Logs/<date>.json`.
- **Local-First**: All data stays on your machine.
- **Sessions**: LinkedIn/WhatsApp browser sessions never synced to git.
- **Payment Rule**: Any payment > $100 always requires explicit approval.

---

## Human-in-the-Loop Workflow

```
1. Claude creates:     Pending_Approval/ACTION_<name>.md
2. You review it:      Open in Obsidian or run /approve-pending
3. You approve:        Move file → Approved/
   Or reject:          Move file → Rejected/
4. Orchestrator acts:  Detects /Approved/ → executes → moves to Done/
5. Logged:             Logs/<date>.json + Dashboard.md updated
```

---

## Silver Tier Checklist

- [x] All Bronze requirements
- [x] LinkedIn Watcher (`linkedin_watcher.py`) — monitors + posts
- [x] WhatsApp Watcher (`whatsapp_watcher.py`) — monitors messages
- [x] Gmail Watcher (`gmail_watcher.py`) — monitors email
- [x] Auto-post to LinkedIn (HITL-gated)
- [x] Claude reasoning loop creates `Plan.md` files (enforced in all skills)
- [x] Email MCP Server (`mcp_servers/email_server.py`) — JSON-RPC 2.0 over stdio
- [x] Human-in-the-Loop approval workflow (`/approve-pending`)
- [x] Scheduling: cron (`scripts/setup_cron.sh`) + PM2 (`scripts/pm2.config.js`)
- [x] Orchestrator (`orchestrator.py`) — routes approved actions
- [x] All AI functionality as Agent Skills

---

## Tier Roadmap

| Tier | Status | Features |
|------|--------|---------|
| **Bronze** | ✅ Complete | Vault + FileSystem Watcher + Agent Skills |
| **Silver** | ✅ Complete | 4 Watchers + LinkedIn Posting + Email MCP + Orchestrator + Scheduling |
| Gold | 🔲 Next | Odoo accounting + Facebook/Instagram + Ralph Wiggum loop |
| Platinum | 🔲 Future | Cloud 24/7 + multi-agent + A2A protocol |

---

## Tech Stack

- **Brain**: Claude Code (`claude-sonnet-4-6`)
- **Memory/GUI**: Obsidian (local Markdown)
- **Senses**: filesystem_watcher, gmail_watcher, linkedin_watcher, whatsapp_watcher
- **Hands**: Email MCP Server (SMTP) + LinkedIn Playwright poster
- **Nervous System**: Orchestrator (approved-file router + scheduler)
- **Process Management**: PM2 or cron

---

*Personal AI Employee Hackathon 0 — Silver Tier — Built with Claude Code*
