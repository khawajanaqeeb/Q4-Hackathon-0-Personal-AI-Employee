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
      - `linkedin_message` / `facebook_notification` / `facebook_message` → Draft a reply (see accounting detection below)
      - `file_drop` → Summarize the file contents and determine the required action
      - `urgent` → Immediately create a plan and flag for human review
   d. **Accounting/Money Detection** — Before drafting a reply, scan the message content for any of these keywords:
      `price, pricing, quote, quotation, invoice, payment, cost, fee, budget, rate, package, plan, how much, amount`

      **If ANY keyword is found** → this is an **ACCOUNTING QUERY**. Do BOTH of the following:

      **A. Draft a reply** — create `AI_Employee_Vault/Pending_Approval/APPROVAL_<PLATFORM>_REPLY_<sender>_<date>.md`:
      ```yaml
      ---
      type: <platform>_message_reply
      action: send_<platform>_reply
      platform: <platform>
      sender: <sender name>
      priority: high
      status: pending_approval
      created: <iso_datetime>
      expires: <iso_datetime + 24h>
      ---

      ## Reply

      <Professional reply — ask for project requirements before quoting, or confirm pricing>
      ```

      **B. Create an Odoo action file** — create `AI_Employee_Vault/Pending_Approval/APPROVAL_ODOO_<sender>_<date>.md`:
      ```yaml
      ---
      type: odoo_action
      action: create_client_and_invoice
      partner_name: <sender name>
      amount: <amount if known, else 0>
      description: <brief service description from message>
      odoo_action: invoice
      priority: high
      status: pending_approval
      created: <iso_datetime>
      ---

      ## Odoo Action

      Create a new client record and draft invoice in Odoo for this prospect.
      ```
      Note: Per Handbook, amounts > $100 always require approval — these files are already in Pending_Approval/ so the rule is satisfied.

      **If NO accounting keywords** → draft reply only (no Odoo file needed).

   e. **Create a Plan** in `AI_Employee_Vault/Plans/PLAN_<item_name>.md` with:
      - Objective
      - Step-by-step checklist (use `- [ ]` checkboxes)
      - Required approvals (if any)
   f. **Update the action file's frontmatter** to set `status: in_progress`
   g. If the action requires human approval → create file in `AI_Employee_Vault/Pending_Approval/APPROVAL_<item>.md`
   h. If no approval needed → complete the action and move file to `AI_Employee_Vault/Done/`

4. **Update Dashboard**: After processing all items, update `AI_Employee_Vault/Dashboard.md`:
   - Update the Quick Stats table (items processed, pending, done)
   - Append to the "Recent Activity" section with timestamp and summary

5. **Log** all actions taken in `AI_Employee_Vault/Logs/<today_date>.json`

## Approval File Naming Conventions

| Platform | Reply approval file | Odoo file (if accounting) |
|----------|--------------------|-----------------------------|
| LinkedIn | `APPROVAL_LINKEDIN_REPLY_<sender>_<YYYYMMDD_HHMMSS>.md` | `APPROVAL_ODOO_<sender>_<date>.md` |
| Facebook | `APPROVAL_FACEBOOK_REPLY_<sender>_<YYYYMMDD_HHMMSS>.md` | `APPROVAL_ODOO_<sender>_<date>.md` |
| Gmail    | `EMAIL_REPLY_<subject>_<date>.md` | `APPROVAL_ODOO_<sender>_<date>.md` |
| Instagram | Manual only — no automated REPLY approval | `APPROVAL_ODOO_<sender>_<date>.md` |

## Rules

- NEVER execute external actions (send email, make payment) without creating an approval file first
- NEVER delete files — move them to `/Done/` or `/Rejected/`
- Always respect the priority order: P0 > P1 > P2 > P3
- If unsure about an action, default to creating a Pending_Approval file
- For LinkedIn/Facebook replies: always put reply text under a `## Reply` markdown heading in the approval file
- For Odoo actions: always set `action: create_client_and_invoice` (or `create_client_and_quotation`) in frontmatter

## Output

After processing, summarize:
- How many items were processed
- How many require approval
- Any urgent items found
