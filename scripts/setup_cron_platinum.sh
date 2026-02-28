#!/usr/bin/env bash
# ── Platinum Tier: Cron Setup ─────────────────────────────────────────────────
# setup_cron_platinum.sh — Install Platinum Tier cron jobs
#
# Adds:
#   - Vault sync every 5 minutes (cloud + local)
#   - Odoo daily backup at 2am (cloud only)
#   - Signal merge every 30 minutes (local only)
#
# Usage:
#   bash scripts/setup_cron_platinum.sh           # Install all
#   bash scripts/setup_cron_platinum.sh --local   # Local-only jobs
#   bash scripts/setup_cron_platinum.sh --cloud   # Cloud-only jobs
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${REPO_DIR}/AI_Employee_Vault"
PYTHON="${PYTHON_CMD:-python3}"
MODE="${1:-}"

echo "Installing Platinum Tier cron jobs..."
echo "  Repo: ${REPO_DIR}"

# ── Cron job definitions ──────────────────────────────────────────────────────

# Vault sync every 5 minutes (both cloud and local)
VAULT_SYNC_CRON="*/5 * * * * cd ${REPO_DIR} && ${PYTHON} scripts/vault_sync.py --vault ${VAULT_DIR} --once >> logs/vault-sync-cron.log 2>&1"

# Signal merge every 30 minutes (local only — merges cloud signals into Dashboard.md)
MERGE_SIGNALS_CRON="*/30 * * * * cd ${REPO_DIR} && ${PYTHON} scripts/merge_signals.py --vault ${VAULT_DIR} >> logs/merge-signals-cron.log 2>&1"

# Odoo daily backup at 2am (cloud only)
ODOO_BACKUP_DIR="${REPO_DIR}/backups"
ODOO_BACKUP_CRON="0 2 * * * mkdir -p ${ODOO_BACKUP_DIR} && docker exec odoo-db pg_dumpall -U odoo > ${ODOO_BACKUP_DIR}/odoo_\$(date +\%Y\%m\%d).sql 2>/dev/null && find ${ODOO_BACKUP_DIR} -name 'odoo_*.sql' -mtime +7 -delete"

# ── Install jobs based on mode ────────────────────────────────────────────────

mkdir -p "${REPO_DIR}/logs"

install_cron() {
    local job="$1"
    local desc="$2"
    # Remove existing identical job to avoid duplicates, then add
    ( crontab -l 2>/dev/null | grep -vF "${job}" ; echo "${job}" ) | crontab -
    echo "  ✔ Installed: ${desc}"
}

if [ "${MODE}" = "--local" ]; then
    echo "→ Installing local-only cron jobs..."
    install_cron "${VAULT_SYNC_CRON}" "vault-sync (every 5 min)"
    install_cron "${MERGE_SIGNALS_CRON}" "merge-signals (every 30 min)"
elif [ "${MODE}" = "--cloud" ]; then
    echo "→ Installing cloud-only cron jobs..."
    install_cron "${VAULT_SYNC_CRON}" "vault-sync (every 5 min)"
    install_cron "${ODOO_BACKUP_CRON}" "odoo-backup (daily 2am)"
else
    echo "→ Installing all Platinum cron jobs..."
    install_cron "${VAULT_SYNC_CRON}" "vault-sync (every 5 min)"
    install_cron "${MERGE_SIGNALS_CRON}" "merge-signals (every 30 min)"
    install_cron "${ODOO_BACKUP_CRON}" "odoo-backup (daily 2am)"
fi

echo ""
echo "Current crontab:"
crontab -l 2>/dev/null | grep -E "vault_sync|merge_signals|odoo_backup|weekly_audit" | sed 's/^/  /'
echo ""
echo "Platinum cron setup complete."
echo "To view all jobs: crontab -l"
echo "To view logs:     tail -f ${REPO_DIR}/logs/vault-sync-cron.log"
