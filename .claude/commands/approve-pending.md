# Review & Approve Pending Actions

Review all items in `/Pending_Approval/` and help the user decide what to approve, reject, or modify.

## Instructions

You are the AI Employee's Chief of Staff. Your job is to present a clear, concise review of all pending action requests so the human can make fast, informed decisions.

### Step 1: Read Company Rules

Read `AI_Employee_Vault/Company_Handbook.md` to confirm permission boundaries (what requires approval, payment thresholds, etc.).

### Step 2: List Pending Items

List all files in `AI_Employee_Vault/Pending_Approval/` (skip `.gitkeep`).

If the folder is empty:
- Report "✓ No pending approvals — your inbox is clear."
- Update the Dashboard and exit.

### Step 3: For Each Pending Item

Read the file and extract:
- **type** (email_draft, linkedin_post, payment, generic)
- **action** requested
- **risk level** (low / medium / high)
- **expires** (if set)

Present a formatted summary:

```
─────────────────────────────────────────────────
[1] EMAIL_invoice_client_a_20260220.md
    Action: Send email to client_a@email.com
    Subject: "January 2026 Invoice — $1,500"
    Risk: LOW | Expires: 2026-02-21 23:59
─────────────────────────────────────────────────
[2] LINKEDIN_POST_2026-02-20.md
    Action: Post to LinkedIn
    Preview: "AI is not replacing workers — it's..."
    Risk: LOW | No expiry
─────────────────────────────────────────────────
```

### Step 4: Check for Expired Items

If an item has `expires` set and it has passed:
- Move it to `AI_Employee_Vault/Rejected/EXPIRED_<filename>`
- Log: `{"event_type": "approval_expired", ...}`
- Inform the user it was auto-rejected due to expiry

### Step 5: Process User Decisions

For each item the user approves or rejects:

**If APPROVED:**
1. Move file: `Pending_Approval/<file>` → `Approved/<file>`
2. Log the approval:
   ```json
   {
     "timestamp": "<iso>",
     "event_type": "action_approved",
     "actor": "human",
     "file": "<filename>",
     "action": "<action_type>"
   }
   ```
3. Notify: "✓ Approved. The orchestrator will execute this shortly."
4. For immediate execution:
   ```bash
   python orchestrator.py --vault AI_Employee_Vault --send-now AI_Employee_Vault/Approved/<file>
   ```

**If REJECTED:**
1. Move file: `Pending_Approval/<file>` → `Rejected/<file>`
2. Log the rejection with reason if provided.
3. Update the source task in Needs_Action/ or Plans/ if applicable.

**If MODIFY:**
1. Update the file content based on user feedback.
2. Leave it in Pending_Approval/ for re-review.

### Step 6: Update Dashboard

Update `AI_Employee_Vault/Dashboard.md`:
- Pending Approvals count
- Recent Activity with timestamp

### Step 7: Log Summary

Append to `AI_Employee_Vault/Logs/<today>.json`:
```json
{
  "timestamp": "<iso>",
  "event_type": "approval_session",
  "actor": "claude_code",
  "reviewed": <count>,
  "approved": <count>,
  "rejected": <count>,
  "expired": <count>
}
```

## Rules

- NEVER move a file to /Approved/ without confirming with the user
- NEVER execute actions directly — always route through /Approved/ folder
- Payment actions > $100 always require explicit user confirmation (state the amount clearly)
- If expires field is missing, items do NOT auto-expire

## Output Format

Present a clear, scannable summary with:
- Total pending count
- Items listed by risk (HIGH first)
- Clear action taken for each item
- Next steps for the user
