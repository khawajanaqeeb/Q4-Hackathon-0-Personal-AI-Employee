#!/usr/bin/env bash
# ── Platinum Tier: Cloud VM Bootstrap ─────────────────────────────────────────
# setup_cloud.sh — Bootstrap script for Ubuntu 22.04 / Oracle Cloud Free Tier
#
# Usage:
#   bash scripts/setup_cloud.sh
#
# After running:
#   1. Fill in .env (NEVER commit it)
#   2. Set up git remote: git remote add origin <your-repo-url>
#   3. Add SSH public key to your GitHub/GitLab repo
#   4. pm2 start scripts/cloud_pm2.config.js
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VAULT_DIR="${REPO_DIR}/AI_Employee_Vault"

echo "============================================================"
echo "  Personal AI Employee — Platinum Tier Cloud VM Setup"
echo "  Repo: ${REPO_DIR}"
echo "============================================================"
echo ""

# ── System Dependencies ───────────────────────────────────────────────────────
echo "→ Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    python3.12 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    docker.io \
    docker-compose-plugin \
    caddy \
    cron

# Enable and start services
sudo systemctl enable --now docker
sudo systemctl enable --now cron
sudo usermod -aG docker "$USER" || true
echo "  ✔ System deps installed"

# ── Node.js + PM2 ─────────────────────────────────────────────────────────────
echo "→ Installing Node.js and PM2..."
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
sudo npm install -g pm2
echo "  ✔ PM2 installed"

# ── Python Dependencies ───────────────────────────────────────────────────────
echo "→ Installing Python dependencies..."
cd "${REPO_DIR}"
pip3 install --break-system-packages -r watchers/requirements.txt 2>/dev/null || \
    pip3 install --user -r watchers/requirements.txt
echo "  ✔ Python deps installed"

# ── Playwright ────────────────────────────────────────────────────────────────
echo "→ Installing Playwright Chromium..."
python3 -m playwright install chromium --with-deps 2>/dev/null || \
    playwright install chromium --with-deps || \
    echo "  ⚠ Playwright install failed — install manually: playwright install chromium --with-deps"
echo "  ✔ Playwright done"

# ── Vault Directories ─────────────────────────────────────────────────────────
echo "→ Ensuring vault directories exist..."
mkdir -p \
    "${VAULT_DIR}/Inbox" \
    "${VAULT_DIR}/Needs_Action" \
    "${VAULT_DIR}/In_Progress/cloud" \
    "${VAULT_DIR}/In_Progress/local" \
    "${VAULT_DIR}/Pending_Approval" \
    "${VAULT_DIR}/Approved" \
    "${VAULT_DIR}/Done" \
    "${VAULT_DIR}/Rejected" \
    "${VAULT_DIR}/Plans" \
    "${VAULT_DIR}/Logs" \
    "${VAULT_DIR}/Briefings" \
    "${VAULT_DIR}/Accounting" \
    "${VAULT_DIR}/Signals"

for dir in \
    "${VAULT_DIR}/In_Progress" \
    "${VAULT_DIR}/In_Progress/cloud" \
    "${VAULT_DIR}/In_Progress/local" \
    "${VAULT_DIR}/Signals"; do
    touch "${dir}/.gitkeep"
done
echo "  ✔ Vault directories created"

# ── Environment File ──────────────────────────────────────────────────────────
echo "→ Setting up .env..."
if [ ! -f "${REPO_DIR}/.env" ]; then
    cp "${REPO_DIR}/.env.example" "${REPO_DIR}/.env"
    echo ""
    echo "  ⚠  WARNING: .env created from template."
    echo "     Fill in your credentials before starting:"
    echo "     nano ${REPO_DIR}/.env"
    echo ""
    echo "     Minimum required for cloud agent:"
    echo "       AGENT_MODE=cloud"
    echo "       GIT_REMOTE_URL=<your-git-repo-url>"
    echo "       GMAIL_CREDENTIALS_PATH=watchers/credentials.json"
    echo "       SMTP_USER=<your-email>"
    echo "       SMTP_PASSWORD=<app-password>"
    echo ""
else
    echo "  ✔ .env already exists (skipped)"
fi

# Set AGENT_MODE=cloud if not already set
if ! grep -q "^AGENT_MODE=" "${REPO_DIR}/.env" 2>/dev/null; then
    echo "AGENT_MODE=cloud" >> "${REPO_DIR}/.env"
    echo "  → AGENT_MODE=cloud added to .env"
fi

# ── Git Remote ────────────────────────────────────────────────────────────────
echo "→ Checking git remote..."
if git -C "${REPO_DIR}" remote | grep -q origin; then
    echo "  ✔ Git remote 'origin' already configured"
else
    GIT_URL="${GIT_REMOTE_URL:-}"
    if [ -n "${GIT_URL}" ]; then
        git -C "${REPO_DIR}" remote add origin "${GIT_URL}"
        echo "  ✔ Git remote added: ${GIT_URL}"
    else
        echo "  ⚠  No git remote configured."
        echo "     Set GIT_REMOTE_URL in .env or run:"
        echo "     git remote add origin <your-repo-url>"
    fi
fi

# ── Odoo (optional) ───────────────────────────────────────────────────────────
echo "→ Starting Odoo Community (Docker)..."
if [ -f "${REPO_DIR}/scripts/odoo_docker_compose.yml" ]; then
    docker compose -f "${REPO_DIR}/scripts/odoo_docker_compose.yml" up -d || \
        echo "  ⚠ Odoo Docker start failed — start manually with:"
    echo "    docker compose -f scripts/odoo_docker_compose.yml up -d"
else
    echo "  ⚠ odoo_docker_compose.yml not found — skipping Odoo"
fi

# ── PM2 ───────────────────────────────────────────────────────────────────────
echo "→ Setting up PM2..."
mkdir -p "${REPO_DIR}/logs"
pm2 start "${REPO_DIR}/scripts/cloud_pm2.config.js" || \
    echo "  ⚠ PM2 start failed — run manually: pm2 start scripts/cloud_pm2.config.js"
pm2 save || true

# Enable PM2 startup
pm2 startup systemd -u "$USER" --hp "$HOME" 2>/dev/null | tail -1 | bash || \
    echo "  ⚠ Run 'pm2 startup' manually and follow the printed command."

# ── Cron ─────────────────────────────────────────────────────────────────────
echo "→ Installing Platinum cron jobs..."
bash "${REPO_DIR}/scripts/setup_cron_platinum.sh" || \
    echo "  ⚠ Cron setup failed — run manually: bash scripts/setup_cron_platinum.sh"

echo ""
echo "============================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Fill in .env: nano ${REPO_DIR}/.env"
echo "  2. Configure git remote (if not done): git remote add origin <url>"
echo "  3. Check PM2 status: pm2 status"
echo "  4. Watch logs: pm2 logs cloud-agent"
echo "  5. Odoo UI: http://localhost:8069 (or your domain)"
echo "============================================================"
