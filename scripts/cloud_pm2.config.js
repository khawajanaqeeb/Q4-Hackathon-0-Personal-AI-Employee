/**
 * cloud_pm2.config.js — PM2 Process Config for Cloud VM (Platinum Tier)
 *
 * Cloud-only processes:
 *   - cloud-agent     → scripts/cloud_agent.py (email triage + social drafts)
 *   - gmail-watcher   → watchers/gmail_watcher.py (inbound email monitor)
 *   - vault-sync      → scripts/vault_sync.py (git pull/push daemon)
 *   - watchdog-cloud  → scripts/watchdog.py (health monitor for cloud processes)
 *
 * Setup:
 *   npm install -g pm2
 *   pm2 start scripts/cloud_pm2.config.js
 *   pm2 save && pm2 startup
 *
 * Useful commands:
 *   pm2 status                  — List cloud processes
 *   pm2 logs cloud-agent        — Tail cloud agent logs
 *   pm2 logs vault-sync         — Tail vault sync logs
 *   pm2 restart cloud-agent     — Restart one process
 */

const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const VAULT = path.join(ROOT, "AI_Employee_Vault");
const PYTHON = process.env.PYTHON_CMD || "python3";

function envOrDefault(key, def) {
  return process.env[key] || def;
}

module.exports = {
  apps: [
    // ── Cloud Agent (Platinum Tier core) ─────────────────────────────────────
    {
      name: "cloud-agent",
      script: PYTHON,
      args: `scripts/cloud_agent.py --vault ${VAULT} --interval 30`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 5000,
      max_restarts: 20,
      autorestart: true,
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        AGENT_MODE: "cloud",
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
        CLOUD_POLL_INTERVAL: "30",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "cloud-agent-error.log"),
      out_file: path.join(ROOT, "logs", "cloud-agent-out.log"),
    },

    // ── Gmail Watcher ─────────────────────────────────────────────────────────
    {
      name: "gmail-watcher",
      script: PYTHON,
      args: `watchers/gmail_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 5000,
      max_restarts: 10,
      autorestart: true,
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        AGENT_MODE: "cloud",
        GMAIL_CREDENTIALS_PATH: envOrDefault(
          "GMAIL_CREDENTIALS_PATH",
          path.join(ROOT, "watchers/credentials.json")
        ),
        GMAIL_TOKEN_PATH: envOrDefault(
          "GMAIL_TOKEN_PATH",
          path.join(ROOT, "watchers/token.json")
        ),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "gmail-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "gmail-watcher-out.log"),
    },

    // ── Vault Sync (git pull/push daemon) ─────────────────────────────────────
    {
      name: "vault-sync",
      script: PYTHON,
      args: `scripts/vault_sync.py --vault ${VAULT} --interval 300`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 10,
      autorestart: true,
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        GIT_VAULT_BRANCH: envOrDefault("GIT_VAULT_BRANCH", "main"),
        VAULT_SYNC_INTERVAL: envOrDefault("VAULT_SYNC_INTERVAL", "300"),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "vault-sync-error.log"),
      out_file: path.join(ROOT, "logs", "vault-sync-out.log"),
    },

    // ── Watchdog (Cloud) ──────────────────────────────────────────────────────
    {
      name: "watchdog-cloud",
      script: PYTHON,
      args: `scripts/watchdog.py --vault ${VAULT} --interval 60`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 15000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "watchdog-cloud-error.log"),
      out_file: path.join(ROOT, "logs", "watchdog-cloud-out.log"),
    },
  ],
};
