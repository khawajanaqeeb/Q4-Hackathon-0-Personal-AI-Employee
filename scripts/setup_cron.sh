#!/usr/bin/env bash
# =============================================================================
# setup_cron.sh — Set up cron jobs for Personal AI Employee (Silver Tier)
#
# Installs scheduled tasks:
#   - Every 30 min: process inbox (claude /process-inbox)
#   - Daily @ 8 AM: morning briefing (claude /morning-briefing)
#   - Sunday @ 7 PM: weekly audit
#   - Every hour:   update dashboard
#
# Usage:
#   bash scripts/setup_cron.sh           # Install cron jobs
#   bash scripts/setup_cron.sh --remove  # Remove cron jobs
#   bash scripts/setup_cron.sh --list    # Show installed jobs
#   bash scripts/setup_cron.sh --dry-run # Show what would be installed
#
# WSL2 note: cron doesn't auto-start in WSL2.
#   Start it with:  sudo service cron start
#   Or add to /etc/wsl.conf (see comments at bottom)
# =============================================================================

set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VAULT_PATH="$PROJECT_ROOT/AI_Employee_Vault"
PYTHON_CMD="${PYTHON_CMD:-python3}"
CLAUDE_CMD="${CLAUDE_CMD:-claude}"
LOG_DIR="$PROJECT_ROOT/logs"
CRON_MARKER="# AI-Employee-Silver"

# ─── Helpers ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ─── Parse args ───────────────────────────────────────────────────────────────
REMOVE=false
LIST=false
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --remove)  REMOVE=true ;;
        --list)    LIST=true ;;
        --dry-run) DRY_RUN=true ;;
        -h|--help)
            echo "Usage: $0 [--remove] [--list] [--dry-run]"
            exit 0
            ;;
    esac
done

# ─── Ensure log directory exists ──────────────────────────────────────────────
mkdir -p "$LOG_DIR"

# ─── Build cron lines ─────────────────────────────────────────────────────────

# Wrap claude skill in a shell command with proper env
# Each cron job: cd to project root, source .env if present, run claude
CLAUDE_SKILL_CMD="cd $PROJECT_ROOT && [ -f .env ] && export \$(grep -v '^#' .env | xargs) 2>/dev/null; $CLAUDE_CMD --print"

CRON_JOBS=(
    # Every 30 minutes: process inbox
    "*/30 * * * * $CLAUDE_SKILL_CMD /process-inbox >> $LOG_DIR/process-inbox.log 2>&1 $CRON_MARKER"

    # Every hour on the hour: update dashboard
    "0 * * * * $CLAUDE_SKILL_CMD /update-dashboard >> $LOG_DIR/update-dashboard.log 2>&1 $CRON_MARKER"

    # Daily at 8:00 AM: morning briefing
    "0 8 * * * $CLAUDE_SKILL_CMD /morning-briefing >> $LOG_DIR/morning-briefing.log 2>&1 $CRON_MARKER"

    # Every Sunday at 7:00 PM: weekly audit (morning-briefing with full context)
    "0 19 * * 0 $CLAUDE_SKILL_CMD /morning-briefing >> $LOG_DIR/weekly-audit.log 2>&1 $CRON_MARKER"

    # Every 5 minutes: run orchestrator once to process any approved files
    "*/5 * * * * cd $PROJECT_ROOT && $PYTHON_CMD orchestrator.py --vault $VAULT_PATH --no-schedule --send-now \$(ls $VAULT_PATH/Approved/*.md 2>/dev/null | head -1) 2>/dev/null $CRON_MARKER"
)

# Alternative: use the orchestrator directly (it handles scheduling internally)
ORCHESTRATOR_PM2="$PROJECT_ROOT/scripts/pm2.config.js"

# ─── Remove mode ──────────────────────────────────────────────────────────────
if $REMOVE; then
    info "Removing AI Employee cron jobs..."
    current_cron=$(crontab -l 2>/dev/null || echo "")
    new_cron=$(echo "$current_cron" | grep -v "$CRON_MARKER" || true)
    if $DRY_RUN; then
        warn "[DRY RUN] Would remove lines containing: $CRON_MARKER"
    else
        echo "$new_cron" | crontab -
        info "Removed all cron jobs marked with: $CRON_MARKER"
    fi
    exit 0
fi

# ─── List mode ────────────────────────────────────────────────────────────────
if $LIST; then
    info "Current AI Employee cron jobs:"
    crontab -l 2>/dev/null | grep "$CRON_MARKER" || echo "  (none installed)"
    exit 0
fi

# ─── Install mode ─────────────────────────────────────────────────────────────
info "Setting up AI Employee cron schedule..."
info "Project root: $PROJECT_ROOT"
info "Vault path:   $VAULT_PATH"
info "Python:       $(which $PYTHON_CMD 2>/dev/null || echo 'not found')"
info "Claude:       $(which $CLAUDE_CMD 2>/dev/null || echo 'not found — skills will not run')"
echo ""

# Check for WSL2
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    warn "WSL2 detected. Cron may not auto-start."
    warn "Start cron with:  sudo service cron start"
    warn "To auto-start, add to /etc/wsl.conf:"
    warn '  [boot]'
    warn '  command = service cron start'
    echo ""
fi

# Get existing crontab (ignore error if empty)
existing=$(crontab -l 2>/dev/null || echo "")

# Remove old AI Employee entries
cleaned=$(echo "$existing" | grep -v "$CRON_MARKER" || true)

# Build new crontab
new_crontab="$cleaned"
if [ -n "$cleaned" ] && [ -n "$(echo "$cleaned" | tail -1)" ]; then
    new_crontab="$cleaned"$'\n'
fi

installed=0
for job in "${CRON_JOBS[@]}"; do
    if $DRY_RUN; then
        info "[DRY RUN] Would install: $job"
    else
        new_crontab="$new_crontab"$'\n'"$job"
        info "Scheduled: $job"
        ((installed++)) || true
    fi
done

if ! $DRY_RUN; then
    echo "$new_crontab" | crontab -
    info ""
    info "✓ Installed $installed cron job(s)."
    info ""
    info "View your crontab with:   crontab -l"
    info "Remove all jobs with:     bash scripts/setup_cron.sh --remove"
fi

# ─── Alternative: recommend PM2 ──────────────────────────────────────────────
echo ""
info "── Alternative: PM2 (recommended for always-on operation) ──"
info "PM2 handles auto-restart, logging, and startup persistence."
info ""
info "  # Install PM2"
info "  npm install -g pm2"
info ""
info "  # Start all watchers + orchestrator"
info "  pm2 start scripts/pm2.config.js"
info ""
info "  # Save and enable startup"
info "  pm2 save && pm2 startup"
echo ""

# ─── WSL2 cron setup note ────────────────────────────────────────────────────
if grep -qi "microsoft" /proc/version 2>/dev/null; then
    echo "─────────────────────────────────────────────────────────"
    echo "WSL2 cron auto-start: add to /etc/wsl.conf:"
    echo ""
    echo "  [boot]"
    echo "  command = service cron start"
    echo ""
    echo "Then restart WSL: wsl --shutdown (from PowerShell)"
    echo "─────────────────────────────────────────────────────────"
fi
