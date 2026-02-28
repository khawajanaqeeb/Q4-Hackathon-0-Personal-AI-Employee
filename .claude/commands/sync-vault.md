# Sync Vault — Git Vault Synchronisation (Platinum Tier)

Trigger a vault sync: pull latest changes from the Git remote, then push any
local changes. Reports what was pulled/pushed and lists any new items that
arrived from the Cloud Agent.

## Instructions

Run this when you want to:
- Pull Cloud Agent drafts from the remote (CLOUD_DRAFT_* in Pending_Approval/)
- Push your local approvals/completions to the remote
- Check what the Cloud Agent has been working on

## Steps

1. Run a single vault sync (pull + push):

```bash
python3 scripts/vault_sync.py --vault AI_Employee_Vault --once
```

2. Merge any new Cloud signals into Dashboard.md:

```bash
python3 scripts/merge_signals.py --vault AI_Employee_Vault
```

3. Report results:
   - Show what files changed (from pull output)
   - List new items in Needs_Action/ (from Cloud Agent)
   - List new CLOUD_DRAFT_* files in Pending_Approval/ (ready for your review)
   - Show current sync status from Signals/SYNC_STATUS.md

4. If there are new CLOUD_DRAFT_* files in Pending_Approval/, prompt:
   "There are N cloud draft(s) awaiting your approval. Run /approve-pending to review them."

## Expected Output Format

```
## Vault Sync Report — <timestamp>

### Pull
- Files updated: N
- Conflicts resolved: N

### Push
- Files pushed: N

### New Items from Cloud
- Needs_Action/: N new files
- Pending_Approval/: N cloud drafts

### Cloud Agent Drafts Ready for Approval
- CLOUD_DRAFT_EMAIL_*.md — Re: Partnership Opportunity
- CLOUD_DRAFT_SOCIAL_*.md — LinkedIn draft

Run `/approve-pending` to review and approve.
```
