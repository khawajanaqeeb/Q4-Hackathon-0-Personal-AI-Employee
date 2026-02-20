# Start Orchestrator

Start the AI Employee's Master Orchestrator — the Silver Tier "nervous system" that watches for approved actions and runs scheduled tasks.

## What the Orchestrator Does

1. **Watches `/Approved/`** — When you move a file here, it automatically:
   - Sends `EMAIL_*.md` files via the Email MCP server
   - Posts `LINKEDIN_POST_*.md` files to LinkedIn
   - Logs all actions to `/Logs/`
   - Moves processed files to `/Done/`

2. **Runs Scheduled Tasks:**
   - Every 30 min → `/process-inbox`
   - Every hour → `/update-dashboard`
   - Daily @ 8 AM → `/morning-briefing`
   - Sunday @ 7 PM → Weekly audit

## Instructions

### Option 1: Start via Terminal (Recommended)

```bash
# Standard mode (watch + schedule)
python orchestrator.py --vault AI_Employee_Vault

# Watch only (no auto-scheduling)
python orchestrator.py --vault AI_Employee_Vault --no-schedule

# Dry-run (log only, no real actions)
python orchestrator.py --vault AI_Employee_Vault --dry-run
```

### Option 2: Start with PM2 (Always-on, auto-restart)

```bash
# Install PM2 (one-time)
npm install -g pm2

# Start all watchers + orchestrator
pm2 start scripts/pm2.config.js

# View status
pm2 status

# View logs
pm2 logs orchestrator

# Enable startup on boot
pm2 save && pm2 startup
```

### Option 3: Set Up Cron Jobs

```bash
# Install cron schedule
bash scripts/setup_cron.sh

# View installed jobs
bash scripts/setup_cron.sh --list

# Remove jobs
bash scripts/setup_cron.sh --remove
```

### Option 4: WSL2 — Start Cron Service

If running in WSL2, cron needs to be started manually each session:
```bash
sudo service cron start
```

Or add to `/etc/wsl.conf` for auto-start:
```ini
[boot]
command = service cron start
```

## Verify Everything is Working

After starting the orchestrator:

1. Drop a test file in `AI_Employee_Vault/Inbox/` → should appear in `/Needs_Action/` within 5 seconds
2. Run `/process-inbox` → should create files in `/Plans/` and `/Pending_Approval/`
3. Move a file from `/Pending_Approval/` to `/Approved/` → orchestrator should process it

## Current Status

Check `AI_Employee_Vault/Dashboard.md` for system status.
Check `AI_Employee_Vault/Logs/<today>.json` for recent events.

## Stopping

Press `Ctrl+C` in the terminal running the orchestrator.
Or via PM2: `pm2 stop orchestrator`
