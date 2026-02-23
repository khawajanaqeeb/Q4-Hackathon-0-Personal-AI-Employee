#!/bin/bash
# setup_cron_gold.sh - Set up Gold Tier cron jobs for Personal AI Employee
#
# Gold Tier additions:
#   - Weekly business audit every Monday at 7:00 AM
#   - Watchdog health check every hour
#   - Social media summary every Friday at 5:00 PM
#
# Usage:
#   bash scripts/setup_cron_gold.sh
#   bash scripts/setup_cron_gold.sh --dry-run

set -e

# ── Config ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VAULT_DIR="$ROOT_DIR/AI_Employee_Vault"
PYTHON="${PYTHON_CMD:-python3}"
LOG_DIR="$ROOT_DIR/logs"
DRY_RUN=false

# Parse args
for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

mkdir -p "$LOG_DIR"

echo "========================================"
echo "Personal AI Employee — Gold Tier Cron Setup"
echo "========================================"
echo "Root:   $ROOT_DIR"
echo "Vault:  $VAULT_DIR"
echo "Python: $PYTHON"
echo "DryRun: $DRY_RUN"
echo ""

# ── Build cron entries ──────────────────────────────────────────────────────────
WEEKLY_AUDIT_CRON="0 7 * * 1 cd $ROOT_DIR && $PYTHON scripts/weekly_audit.py --vault $VAULT_DIR >> $LOG_DIR/weekly-audit.log 2>&1"
FRIDAY_SOCIAL_CRON="0 17 * * 5 cd $ROOT_DIR && $PYTHON mcp_servers/social_media_server.py 2>&1 | head -5 >> $LOG_DIR/social-summary.log"
WATCHDOG_HOURLY="@reboot cd $ROOT_DIR && $PYTHON scripts/watchdog.py --vault $VAULT_DIR >> $LOG_DIR/watchdog.log 2>&1 &"

echo "Cron jobs to install:"
echo "  1. Weekly audit (Mon 7am):    $WEEKLY_AUDIT_CRON"
echo "  2. Social summary (Fri 5pm):  $FRIDAY_SOCIAL_CRON"
echo "  3. Watchdog on reboot:        $WATCHDOG_HOURLY"
echo ""

if $DRY_RUN; then
  echo "[DRY RUN] No changes made."
  exit 0
fi

# ── Install cron jobs ───────────────────────────────────────────────────────────
# Read existing crontab, remove our managed entries, add new ones
MARKER="# AI-Employee-Gold"

(crontab -l 2>/dev/null | grep -v "$MARKER"; \
  echo "$WEEKLY_AUDIT_CRON  $MARKER-weekly-audit"; \
  echo "$FRIDAY_SOCIAL_CRON  $MARKER-social-summary"; \
  echo "$WATCHDOG_HOURLY  $MARKER-watchdog"; \
) | crontab -

echo "✅ Gold Tier cron jobs installed."
echo ""
echo "Verify with: crontab -l"
echo ""
echo "Manual test:"
echo "  python3 scripts/weekly_audit.py --vault AI_Employee_Vault"
echo "  python3 scripts/watchdog.py --vault AI_Employee_Vault --interval 30"
