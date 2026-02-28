# Cloud Status — Cloud Agent Activity Monitor (Platinum Tier)

Read and display the current status of the Cloud Agent, including last activity
time, in-progress tasks, pending approvals from Cloud, and vault sync status.

## Instructions

1. Read all signal files:
   - `AI_Employee_Vault/Signals/CLOUD_STATUS_*.md` — Cloud Agent activity signals
   - `AI_Employee_Vault/Signals/SYNC_STATUS.md` — Vault sync status

2. List items in `AI_Employee_Vault/In_Progress/cloud/`:
   - Files currently being worked on by the Cloud Agent

3. List `CLOUD_DRAFT_*` files in `AI_Employee_Vault/Pending_Approval/`:
   - Email drafts: `CLOUD_DRAFT_EMAIL_*.md`
   - Social drafts: `CLOUD_DRAFT_SOCIAL_*.md`

4. Run merge_signals to update Dashboard.md:

```bash
python3 scripts/merge_signals.py --vault AI_Employee_Vault
```

5. Display a formatted status report.

## Expected Output Format

```
## ☁️ Cloud Agent Status — <timestamp>

### Agent Health
- Status: active / stopped / unknown
- Last Active: <timestamp>
- Tasks Processed (session): N
- Poll Interval: 30s

### Vault Sync
- Status: pushed / pulled / up-to-date
- Last Sync: <timestamp>
- Files Updated: N

### In-Progress (Cloud)
- <filename> (claimed <time> ago)

### Pending Your Approval (Cloud Drafts)
N draft(s) waiting:
- [ ] CLOUD_DRAFT_EMAIL_20260301_143022_EMAIL_LEAD.md
      From: Jane Smith | Subject: Re: Partnership Opportunity
- [ ] CLOUD_DRAFT_SOCIAL_LINKEDIN_20260301_150001.md
      Platform: LinkedIn | Topic: business growth

Run `/approve-pending` to review and approve cloud drafts.
Run `/sync-vault` to pull the latest from Cloud Agent.
```

## No Signals Case

If no signal files exist:
```
## ☁️ Cloud Agent Status

No cloud signals received yet.

This means either:
1. Cloud Agent has not been started (AGENT_MODE=cloud)
2. Vault has not been synced (run /sync-vault)
3. Cloud Agent is running but has not processed any tasks

To start cloud simulation locally:
  AGENT_MODE=cloud python3 scripts/cloud_agent.py --vault AI_Employee_Vault --once
```
