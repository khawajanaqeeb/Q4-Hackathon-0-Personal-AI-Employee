# Personal AI Employee — Gold Tier ✅

> *Your life and business on autopilot. Local-first, agent-driven, human-in-the-loop.*

A **Digital FTE (Full-Time Equivalent)** powered by Claude Code and Obsidian. The Gold Tier adds Twitter/X, Facebook, Instagram, Odoo accounting, Ralph Wiggum autonomous loop, error recovery, process watchdog, and weekly CEO briefing — transforming the Silver assistant into a fully **Autonomous Employee**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│              PERSONAL AI EMPLOYEE (Gold Tier)                   │
└─────────────────────────────────────────────────────────────────┘

External Sources (Gmail, LinkedIn, WhatsApp, Twitter/X, Facebook, Instagram, Files)
         │
         ▼
  ┌──────────────────────────────────────────────────┐
  │               PERCEPTION LAYER                   │
  │  filesystem_watcher.py  (Bronze)                │
  │  gmail_watcher.py       (Bronze/Silver)         │
  │  linkedin_watcher.py    (Silver)                │
  │  whatsapp_watcher.py    (Silver)                │
  │  twitter_watcher.py     (Gold) ← NEW            │
  │  facebook_watcher.py    (Gold) ← NEW            │
  │  instagram_watcher.py   (Gold) ← NEW            │
  └──────────────────────────────────────────────────┘
         │ creates .md action files
         ▼
  AI_Employee_Vault/Needs_Action/
         │
         ▼ (Claude Code reads, Ralph Wiggum loops)
  AI_Employee_Vault/Plans/          ← reasoning plans
         │
         ▼
  AI_Employee_Vault/Pending_Approval/   ← human reviews (HITL)
         │
         ▼ (human moves to /Approved/)
  ┌──────────────────────────────────────────────────┐
  │              ORCHESTRATOR                        │
  │  Watches /Approved/ → routes actions             │
  │  • Email    → Email MCP Server                  │
  │  • Social   → Social Media MCP Server ← NEW     │
  │  • Odoo     → Odoo MCP Server ← NEW             │
  │  Scheduled: Weekly Audit (Mon 7am) ← NEW        │
  └──────────────────────────────────────────────────┘
         │
         ▼
  External Actions (email, social posts, invoices)
         │
         ▼
  AI_Employee_Vault/Done/ + Logs/<date>.json
         │
  ┌──────────────────────────────────────────────────┐
  │          HEALTH & RECOVERY LAYER (Gold)          │
  │  watchdog.py      — monitors/restarts processes  │
  │  retry_handler.py — exponential backoff          │
  │  ralph_wiggum_hook.py — autonomous loop (Stop hook) │
  └──────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install dependencies

```bash
pip3 install watchdog python-dotenv playwright google-auth-oauthlib google-api-python-client --break-system-packages
playwright install chromium
```

### 2. Configure `.env`

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Set up social media sessions (Gold Tier)

```bash
# Twitter/X
python3 watchers/twitter_watcher.py --vault AI_Employee_Vault --setup

# Facebook
python3 watchers/facebook_watcher.py --vault AI_Employee_Vault --setup

# Instagram
python3 watchers/instagram_watcher.py --vault AI_Employee_Vault --setup
```

### 4. Configure Odoo (optional but recommended)

```bash
# Docker (easiest):
docker run -d -p 8069:8069 --name odoo odoo:17

# Then visit http://localhost:8069, create database, add to .env:
# ODOO_URL=http://localhost:8069
# ODOO_DB=your_db
# ODOO_USERNAME=admin
# ODOO_PASSWORD=your_password

# Test Odoo MCP:
python3 mcp_servers/odoo_server.py --test
```

### 5. Start everything with PM2

```bash
npm install -g pm2
pm2 start scripts/pm2.config.js
pm2 save && pm2 startup
```

### 6. Set up Gold Tier cron jobs

```bash
bash scripts/setup_cron_gold.sh
```

---

## Agent Skills (Slash Commands)

| Command | Description | Tier |
|---------|-------------|------|
| `/process-inbox` | Process all items in Needs_Action | Bronze |
| `/update-dashboard` | Refresh Dashboard.md | Bronze |
| `/morning-briefing` | Generate CEO briefing | Bronze |
| `/start-watcher` | Start file system watcher | Bronze |
| `/linkedin-post` | Draft LinkedIn post (HITL) | Silver |
| `/approve-pending` | Review pending approvals | Silver |
| `/run-orchestrator` | Start Master Orchestrator | Silver |
| `/social-post` | Draft multi-platform social post (HITL) | **Gold** |
| `/weekly-audit` | Generate weekly CEO business briefing | **Gold** |
| `/ralph-loop` | Autonomous multi-step task loop | **Gold** |
| `/odoo-query` | Query Odoo accounting/ERP | **Gold** |

---

## Component Reference

### Watchers

| File | Platform | Interval |
|------|----------|----------|
| `watchers/filesystem_watcher.py` | File drops | Real-time |
| `watchers/gmail_watcher.py` | Gmail | 2 min |
| `watchers/linkedin_watcher.py` | LinkedIn | 5 min |
| `watchers/whatsapp_watcher.py` | WhatsApp | 30 sec |
| `watchers/twitter_watcher.py` | Twitter/X | 2 min |
| `watchers/facebook_watcher.py` | Facebook | 3 min |
| `watchers/instagram_watcher.py` | Instagram | 3 min |

### MCP Servers

| File | Tools | Notes |
|------|-------|-------|
| `mcp_servers/email_server.py` | send_email, draft_email, list_drafts | SMTP |
| `mcp_servers/social_media_server.py` | post_to_twitter, post_to_facebook, post_to_instagram, get_social_summary | Playwright sessions |
| `mcp_servers/odoo_server.py` | odoo_authenticate, get_invoices, create_invoice, get_partners, get_financial_summary | Odoo JSON-RPC; mock mode by default |

### Gold Tier Scripts

| File | Purpose |
|------|---------|
| `watchers/retry_handler.py` | Exponential backoff, circuit breaker, rate limiter |
| `scripts/watchdog.py` | Process health monitor — monitors all watchers |
| `scripts/ralph_wiggum_hook.py` | Stop hook — keeps Claude looping until work is done |
| `scripts/weekly_audit.py` | Weekly business + accounting audit → CEO briefing |
| `scripts/setup_cron_gold.sh` | Installs Gold Tier cron jobs |

---

## Ralph Wiggum Loop

The Ralph Wiggum pattern keeps Claude Code working autonomously until a task is complete:

```
Claude works → tries to exit → Stop hook fires → checks Needs_Action/ →
  items remain? → block exit, re-inject prompt → Claude keeps working →
  Needs_Action/ empty? → allow exit
```

Activate with `/ralph-loop` or manually:
```bash
python3 -c "
import json
from pathlib import Path
Path('/tmp/ralph_wiggum_state.json').write_text(json.dumps({
  'active': True, 'max_iterations': 10, 'iteration': 0,
  'vault_path': 'AI_Employee_Vault',
  'task_prompt': 'Process all items in /Needs_Action until empty.'
}))
"
```

---

## Odoo Accounting Integration

The Odoo MCP server works in two modes:

**Mock mode** (default, DRY_RUN=true): Returns sample data — no Odoo required. Perfect for demos.

**Live mode**: Set in `.env`:
```
ODOO_URL=http://localhost:8069
ODOO_DB=mydb
ODOO_USERNAME=admin
ODOO_PASSWORD=mypassword
DRY_RUN=false
```

Odoo API reference: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html

---

## Security

| Rule | Detail |
|------|--------|
| No credentials in vault | Use `.env` only |
| HITL for all external sends | Email, social, payments need approval |
| Payments > $100 | Always manual approval |
| Rate limits | 10 emails/hr, 3 social posts/hr |
| Sessions never synced | `.gitignore` covers all session dirs |
| Audit trail | Every action logged to `Logs/<date>.json` |

---

## Tier Checklist

### Bronze ✅
- [x] Obsidian vault with Dashboard.md and Company_Handbook.md
- [x] File system watcher
- [x] Basic folder structure
- [x] Agent Skills: /process-inbox, /update-dashboard, /morning-briefing, /start-watcher

### Silver ✅
- [x] Gmail watcher
- [x] LinkedIn watcher + HITL poster
- [x] WhatsApp watcher
- [x] Email MCP server
- [x] Master Orchestrator with scheduler
- [x] PM2 config + cron setup
- [x] Agent Skills: /linkedin-post, /approve-pending, /run-orchestrator

### Gold ✅
- [x] Twitter/X watcher + poster (Playwright)
- [x] Facebook watcher + poster (Playwright)
- [x] Instagram watcher (API note)
- [x] Social Media MCP server
- [x] Odoo Community MCP server (JSON-RPC, mock + live modes)
- [x] Weekly Business & Accounting Audit + CEO Briefing
- [x] Error recovery: retry_handler.py (exponential backoff, circuit breaker, rate limiter)
- [x] Process watchdog: watchdog.py (auto-restart, health logging)
- [x] Ralph Wiggum loop (Stop hook for autonomous multi-step completion)
- [x] Multiple MCP servers (Email + Social Media + Odoo)
- [x] Comprehensive audit logging (all events to Logs/<date>.json)
- [x] Agent Skills: /social-post, /weekly-audit, /ralph-loop, /odoo-query
- [x] CLAUDE.md + README.md updated to Gold Tier

---

*Built with Claude Code · Obsidian · Python · Playwright · PM2*
