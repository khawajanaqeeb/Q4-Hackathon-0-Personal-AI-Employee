# Process Inbox

Process all pending items in the AI Employee's `/Needs_Action/` folder.

## Instructions

You are the AI Employee. Follow the Company_Handbook.md rules strictly.

1. **Read** `AI_Employee_Vault/Company_Handbook.md` to confirm your current rules of engagement.

2. **List** all `.md` files in `AI_Employee_Vault/Needs_Action/` (skip `.gitkeep`).

3. **For each file**, in order of priority (P0 first, then P1, P2, P3):
   a. Read the file's frontmatter to determine `type`, `priority`, and `status`
   b. Skip files where `status` is not `pending`
   c. **Analyze** the item based on its type:
      - `email` → Draft a reply and create an approval file in `/Pending_Approval/`
      - `file_drop` → Summarize the file contents and determine the required action
      - `urgent` → Immediately create a plan and flag for human review
   d. **Create a Plan** in `AI_Employee_Vault/Plans/PLAN_<item_name>.md` with:
      - Objective
      - Step-by-step checklist (use `- [ ]` checkboxes)
      - Required approvals (if any)
   e. **Update the action file's frontmatter** to set `status: in_progress`
   f. If the action requires human approval → create file in `AI_Employee_Vault/Pending_Approval/APPROVAL_<item>.md`
   g. If no approval needed → complete the action and move file to `AI_Employee_Vault/Done/`

4. **Update Dashboard**: After processing all items, update `AI_Employee_Vault/Dashboard.md`:
   - Update the Quick Stats table (items processed, pending, done)
   - Append to the "Recent Activity" section with timestamp and summary

5. **Log** all actions taken in `AI_Employee_Vault/Logs/<today_date>.json`

## Rules

- NEVER execute external actions (send email, make payment) without creating an approval file first
- NEVER delete files — move them to `/Done/` or `/Rejected/`
- Always respect the priority order: P0 > P1 > P2 > P3
- If unsure about an action, default to creating a Pending_Approval file

## Output

After processing, summarize:
- How many items were processed
- How many require approval
- Any urgent items found
