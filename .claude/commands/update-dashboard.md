# Update Dashboard

Refresh the `AI_Employee_Vault/Dashboard.md` with current system status.

## Instructions

1. **Count items** in each vault folder:
   - `AI_Employee_Vault/Needs_Action/` — count `.md` files (excluding `.gitkeep`)
   - `AI_Employee_Vault/Pending_Approval/` — count `.md` files
   - `AI_Employee_Vault/Done/` — count files from this week
   - `AI_Employee_Vault/Plans/` — count active (non-archived) plans
   - `AI_Employee_Vault/Inbox/` — count files

2. **Read recent logs**: Check `AI_Employee_Vault/Logs/<today>.json` for the last 5 events.

3. **Read Business_Goals.md**: Extract current MTD revenue and key metrics.

4. **Rewrite Dashboard.md** with:
   - Updated `last_updated` frontmatter timestamp
   - Accurate Quick Stats table
   - Inbox Status section with real counts
   - Recent Activity (last 5 events from logs, most recent first)
   - Active Plans list (from /Plans/ folder)
   - System Health status table

5. **Format the timestamp** as: `YYYY-MM-DD HH:MM`

## Dashboard Template

Preserve the existing structure. Update only the dynamic sections:
- Quick Stats table values
- Inbox Status values
- Recent Activity list
- Active Plans list
- System Health statuses

## Output

Confirm the dashboard has been updated with the current counts and timestamp.
