#!/usr/bin/env bash
# ── Platinum Tier: Odoo Community Cloud Setup ─────────────────────────────────
# odoo_cloud_setup.sh — Set up Odoo with HTTPS via Caddy on Cloud VM
#
# Prerequisites:
#   - Domain pointing to this VM's IP (e.g. odoo.yourdomain.com → VM_IP)
#   - Docker installed (run setup_cloud.sh first)
#   - Ports 80 and 443 open in cloud firewall
#
# Usage:
#   ODOO_DOMAIN=odoo.yourdomain.com bash scripts/odoo_cloud_setup.sh
# ──────────────────────────────────────────────────────────────────────────────

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ODOO_DOMAIN="${ODOO_DOMAIN:-odoo.example.com}"
BACKUP_DIR="${REPO_DIR}/backups"

echo "============================================================"
echo "  Odoo Cloud Setup — Domain: ${ODOO_DOMAIN}"
echo "============================================================"
echo ""

# ── Start Odoo + PostgreSQL ───────────────────────────────────────────────────
echo "→ Starting Odoo via Docker Compose..."
mkdir -p "${REPO_DIR}/scripts/odoo_addons"
docker compose -f "${REPO_DIR}/scripts/odoo_docker_compose.yml" up -d
echo "  ✔ Odoo started on port 8069"

# Wait for Odoo to be healthy
echo "→ Waiting for Odoo to be ready (up to 90s)..."
for i in $(seq 1 18); do
    if curl -sf http://localhost:8069/web/health &>/dev/null; then
        echo "  ✔ Odoo is healthy"
        break
    fi
    echo "  ... waiting ($((i*5))s)"
    sleep 5
done

# ── Caddy Reverse Proxy ───────────────────────────────────────────────────────
echo "→ Configuring Caddy for HTTPS..."

CADDY_CONF="/etc/caddy/Caddyfile"

sudo tee "${CADDY_CONF}" > /dev/null <<EOF
${ODOO_DOMAIN} {
    # HTTPS auto-cert (Let's Encrypt)
    tls {
        protocols tls1.2 tls1.3
    }

    # Odoo HTTP proxy
    reverse_proxy localhost:8069 {
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Proto {scheme}
        header_up X-Real-IP {remote_host}
    }

    # WebSocket (Odoo long polling)
    @websocket {
        path /longpolling/*
    }
    reverse_proxy @websocket localhost:8072

    # Security headers
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        -Server
    }

    # Gzip
    encode gzip
}
EOF

sudo systemctl reload caddy
echo "  ✔ Caddy configured for https://${ODOO_DOMAIN}"

# ── Daily Backup Cron ─────────────────────────────────────────────────────────
echo "→ Setting up daily Odoo backup cron..."
mkdir -p "${BACKUP_DIR}"

CRON_JOB="0 2 * * * docker exec odoo-db pg_dumpall -U odoo > ${BACKUP_DIR}/odoo_\$(date +\%Y\%m\%d).sql && find ${BACKUP_DIR} -name 'odoo_*.sql' -mtime +7 -delete"

# Add to crontab if not already present
( crontab -l 2>/dev/null | grep -v "odoo-db pg_dumpall" ; echo "${CRON_JOB}" ) | crontab -
echo "  ✔ Daily backup cron installed (runs at 2am, keeps 7 days)"

# ── Health Check ──────────────────────────────────────────────────────────────
echo ""
echo "→ Health check..."
if curl -sf "https://${ODOO_DOMAIN}/web/health" &>/dev/null; then
    echo "  ✔ Odoo HTTPS health check: PASS"
else
    echo "  ⚠ HTTPS health check failed — DNS may not be propagated yet."
    echo "    Test manually: curl https://${ODOO_DOMAIN}/web/health"
fi

# ── Update .env ───────────────────────────────────────────────────────────────
echo "→ Updating .env with cloud Odoo URL..."
if [ -f "${REPO_DIR}/.env" ]; then
    sed -i "s|^CLOUD_ODOO_URL=.*|CLOUD_ODOO_URL=https://${ODOO_DOMAIN}|" "${REPO_DIR}/.env" || \
        echo "CLOUD_ODOO_URL=https://${ODOO_DOMAIN}" >> "${REPO_DIR}/.env"
    echo "  ✔ CLOUD_ODOO_URL set in .env"
fi

echo ""
echo "============================================================"
echo "  Odoo setup complete!"
echo ""
echo "  Odoo URL:  https://${ODOO_DOMAIN}"
echo "  Backups:   ${BACKUP_DIR}/"
echo ""
echo "  First-run: visit https://${ODOO_DOMAIN}"
echo "    → Create database → set master password"
echo ""
echo "  Update .env:"
echo "    ODOO_URL=https://${ODOO_DOMAIN}"
echo "    ODOO_DB=odoo"
echo "    ODOO_USERNAME=admin"
echo "    ODOO_PASSWORD=<your-password>"
echo "============================================================"
