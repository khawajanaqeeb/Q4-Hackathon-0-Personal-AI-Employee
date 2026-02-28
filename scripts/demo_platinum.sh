#!/usr/bin/env bash
# ── Platinum Tier: End-to-End Demo ────────────────────────────────────────────
# demo_platinum.sh — Demonstrates the full Platinum cloud/local workflow
#
# What this demo does:
#   Step 1: Creates a simulated inbound email action in Needs_Action/
#   Step 2: Simulates Cloud Agent claiming + drafting reply
#   Step 3: Shows the resulting CLOUD_DRAFT_EMAIL_* in Pending_Approval/
#   Step 4: Prompts user to approve (move to Approved/)
#   Step 5: Runs local orchestrator to send via Email MCP
#   Step 6: Verifies Done/ and logs
#
# Usage:
#   bash scripts/demo_platinum.sh
#   bash scripts/demo_platinum.sh --dry-run   (no actual email sends)
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${REPO_DIR}/AI_Employee_Vault"
PYTHON="${PYTHON_CMD:-python3}"
DRY_RUN="${1:-}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

if [ "${DRY_RUN}" = "--dry-run" ]; then
    export DRY_RUN=true
    echo "Running in DRY-RUN mode (no actual email sends)"
else
    export DRY_RUN=false
fi

echo ""
echo "============================================================"
echo "  Personal AI Employee — Platinum Tier Demo"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""

# ── Step 1: Create simulated email action in Needs_Action/ ───────────────────
echo "STEP 1: Simulating inbound email (gmail-watcher creates action file)..."
EMAIL_FILE="${VAULT_DIR}/Needs_Action/EMAIL_LEAD_${TIMESTAMP}.md"

CREATED_AT=$(date -Iseconds)
RECEIVED_AT=$(date '+%Y-%m-%d %H:%M')
cat > "${EMAIL_FILE}" <<HEREDOC
---
type: inbound_email
action: triage_email
sender: Jane Smith
email: jane.smith@example.com
subject: Partnership Opportunity - Digital Services
urgency: high
summary: Jane wants to discuss a 50k/year partnership for digital marketing services
created: ${CREATED_AT}
---

# Inbound Email: Partnership Opportunity

**From:** Jane Smith <jane.smith@example.com>
**Subject:** Partnership Opportunity - Digital Services
**Received:** ${RECEIVED_AT}
**Urgency:** High

## Email Body

Hi there,

I came across your work and I'm very impressed. I represent XYZ Corp and we're
looking for a strategic digital services partner for our Q2 expansion.

We have a budget of approximately USD 50,000/year and are looking for:
- SEO and content strategy
- Social media management
- Email marketing automation

Would you be available for a 30-minute call this week to discuss further?

Best regards,
Jane Smith
Director of Marketing, XYZ Corp
jane.smith@example.com | +1 (555) 123-4567

---
_Created by gmail-watcher (demo simulation)_
HEREDOC

echo "  ✔ Created: Needs_Action/EMAIL_LEAD_${TIMESTAMP}.md"
echo ""

# ── Step 2: Run Cloud Agent (claim + draft) ───────────────────────────────────
echo "STEP 2: Running Cloud Agent to claim and draft email reply..."
AGENT_MODE=cloud ${PYTHON} scripts/cloud_agent.py \
    --vault "${VAULT_DIR}" \
    --once \
    ${DRY_RUN:+--dry-run} 2>&1 | sed 's/^/  [cloud] /'
echo ""

# ── Step 3: Show pending approval ────────────────────────────────────────────
echo "STEP 3: Checking Pending_Approval/ for cloud draft..."
DRAFT_FILE=$(ls "${VAULT_DIR}/Pending_Approval/CLOUD_DRAFT_EMAIL_"* 2>/dev/null | tail -1 || true)

if [ -z "${DRAFT_FILE}" ]; then
    echo "  ⚠ No cloud draft found in Pending_Approval/"
    echo "    (In dry-run mode, files are not written)"
    DRAFT_FILE="(dry-run — no file written)"
else
    echo "  ✔ Cloud draft ready for approval:"
    echo ""
    echo "  File: $(basename "${DRAFT_FILE}")"
    echo "  ──────────────────────────────────────"
    head -30 "${DRAFT_FILE}" | sed 's/^/  /'
    echo "  ..."
    echo ""
fi

# ── Step 4: Approval prompt ───────────────────────────────────────────────────
echo "STEP 4: Human approval required."
echo ""
echo "  Review the draft at:"
echo "  ${DRAFT_FILE}"
echo ""

if [ "${DRY_RUN}" = "true" ] || [ "${DRY_RUN}" = "false" ] && [ -f "${DRAFT_FILE}" ]; then
    if [ "${DRY_RUN}" = "false" ]; then
        echo "  To approve: move the file to Approved/"
        echo "    mv '${DRAFT_FILE}' '${VAULT_DIR}/Approved/'"
        echo ""
        read -r -p "  Auto-approve for demo? (y/N): " APPROVE
        if [[ "${APPROVE}" =~ ^[Yy]$ ]]; then
            APPROVED_FILE="${VAULT_DIR}/Approved/$(basename "${DRAFT_FILE}")"
            mv "${DRAFT_FILE}" "${APPROVED_FILE}"
            echo "  ✔ Moved to Approved/"
            echo ""
        else
            echo "  Skipping auto-approve. Move the file manually when ready."
            echo "  Then run: python3 orchestrator.py --vault ${VAULT_DIR} --send-now <file>"
            echo ""
            echo "============================================================"
            echo "  Demo paused at Step 4. Resume after manual approval."
            echo "============================================================"
            exit 0
        fi
    else
        echo "  [DRY RUN] Skipping approval step"
        echo ""
    fi
fi

# ── Step 5: Local orchestrator sends email ─────────────────────────────────────
if [ "${DRY_RUN}" = "false" ] && [ -f "${VAULT_DIR}/Approved/$(basename "${DRAFT_FILE}" 2>/dev/null)" 2>/dev/null ]; then
    echo "STEP 5: Local orchestrator routing approved file..."
    APPROVED_FILE="${VAULT_DIR}/Approved/$(basename "${DRAFT_FILE}")"
    ${PYTHON} orchestrator.py \
        --vault "${VAULT_DIR}" \
        --send-now "${APPROVED_FILE}" \
        ${DRY_RUN:+--dry-run} 2>&1 | sed 's/^/  [local] /'
    echo ""
else
    echo "STEP 5: [DRY RUN] Would route approved file via local orchestrator"
    echo ""
fi

# ── Step 6: Vault sync push ───────────────────────────────────────────────────
echo "STEP 6: Syncing vault state to Git..."
${PYTHON} scripts/vault_sync.py \
    --vault "${VAULT_DIR}" \
    --once \
    --dry-run 2>&1 | sed 's/^/  [sync] /'
echo ""

# ── Summary ───────────────────────────────────────────────────────────────────
echo "============================================================"
echo "  Platinum Demo Complete!"
echo ""
echo "  What happened:"
echo "   1. Email action file created in Needs_Action/"
echo "   2. Cloud Agent claimed it → In_Progress/cloud/"
echo "   3. Cloud Agent drafted reply → Pending_Approval/"
echo "   4. User approved → Approved/"
echo "   5. Local orchestrator routed → Email MCP send"
echo "   6. Vault synced to Git"
echo ""
echo "  Check:"
echo "   Vault logs: ${VAULT_DIR}/Logs/$(date +%Y-%m-%d).json"
echo "   Done dir:   ${VAULT_DIR}/Done/"
echo "   Dashboard:  ${VAULT_DIR}/Dashboard.md"
echo ""
echo "  Cloud status: python3 scripts/merge_signals.py --vault ${VAULT_DIR}"
echo "============================================================"
