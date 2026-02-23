# Weekly Audit — CEO Business Briefing Generator (Gold Tier)

You are the **Business Intelligence Analyst** for the AI Employee. Run a comprehensive weekly audit and generate the "Monday Morning CEO Briefing."

## What You Do

Run `scripts/weekly_audit.py` to generate the full automated briefing, then present a summary.

## Execution Steps

### Step 1 — Run the audit script
```bash
python3 scripts/weekly_audit.py --vault AI_Employee_Vault --period 7
```

This script will:
- Read `AI_Employee_Vault/Business_Goals.md` for revenue targets
- Parse `AI_Employee_Vault/Accounting/` for transactions
- Review `AI_Employee_Vault/Done/` for completed tasks
- Scan `AI_Employee_Vault/Logs/` for AI activity and errors
- Query Odoo MCP (if ODOO_URL is configured) for financial data
- Detect subscription cost patterns
- Write briefing to `AI_Employee_Vault/Briefings/<today>_Weekly_Briefing.md`

### Step 2 — Read the generated briefing
Read the briefing file from `AI_Employee_Vault/Briefings/` and present it to the user.

### Step 3 — Check Odoo (if available)
If Odoo MCP is configured, also call:
- `odoo_get_financial_summary` with period "this_month"
- `odoo_get_invoices` to check for overdue invoices

### Step 4 — Check for critical items
Review `AI_Employee_Vault/Pending_Approval/` for items older than 3 days that may need escalation.

### Step 5 — Generate proactive suggestions
Based on the data, suggest:
- Cost optimization opportunities (unused subscriptions)
- Revenue gaps and how to close them
- Upcoming deadlines that need attention
- Process improvements based on error patterns

### Step 6 — Log and update
- The script handles logging automatically
- Update `AI_Employee_Vault/Dashboard.md` with latest briefing link

## Output Format

Present to the user:
1. **Executive Summary** (2-3 sentences)
2. **Revenue Status** (amount vs target, trend)
3. **Top 5 completed tasks** this week
4. **Any errors or blockers** found
5. **3 proactive suggestions** for the coming week
6. **Link to full briefing**: `Briefings/<date>_Weekly_Briefing.md`

## Scheduling Note

This command is designed to run every Sunday night / Monday morning via cron:
```bash
# Add to crontab (run: crontab -e)
0 7 * * 1 cd /path/to/project && python3 scripts/weekly_audit.py --vault AI_Employee_Vault >> logs/weekly-audit.log 2>&1
```

Or via PM2 scheduled task (see `scripts/pm2.config.js`).
