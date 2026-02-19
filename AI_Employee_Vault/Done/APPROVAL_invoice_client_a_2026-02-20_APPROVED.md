---
type: approval_request
action: send_invoice
client: Client A
amount: 1500.00
currency: USD
invoice_number: INV-2026-001
period: January 2026
created: 2026-02-20T02:00:00Z
expires: 2026-02-21T02:00:00Z
status: pending
plan_file: Plans/PLAN_invoice_client_a.md
source_file: Inbox/invoice_client_a.txt
---

# Approval Required: Send Invoice to Client A

## Summary

The AI Employee has drafted an invoice for **Client A** and requires your approval before sending.

## Invoice Details

| Field | Value |
|-------|-------|
| Invoice # | INV-2026-001 |
| Client | Client A |
| Period | January 2026 |
| Amount | **$1,500.00** |
| Due Date | 30 days after send |

## Why Approval is Required

- Sending invoices always requires human approval (Handbook §3)
- Amount $1,500 exceeds the $100 auto-approve threshold (Handbook §3)
- Sending an external communication requires HITL (Handbook §5)

## Action Required

**To APPROVE:** Move this file to `/Approved/`

**To REJECT:** Move this file to `/Rejected/`

> ⚠️ This approval expires: **2026-02-21** — after that, a new approval will be created.

---
*Created by: AI Employee v0.1 · Bronze Tier*
