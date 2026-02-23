/**
 * pm2.config.js — PM2 Process Manager Config for Personal AI Employee (Gold Tier)
 *
 * PM2 keeps all watchers, orchestrator, and watchdog running 24/7,
 * auto-restarts on crash, and collects logs.
 *
 * Setup:
 *   npm install -g pm2
 *
 * Start all processes:
 *   pm2 start scripts/pm2.config.js
 *
 * Enable startup (survive reboot):
 *   pm2 save
 *   pm2 startup   ← follow the printed command
 *
 * Useful commands:
 *   pm2 status          — List all processes
 *   pm2 logs            — Tail all logs
 *   pm2 logs orchestrator  — Tail one process
 *   pm2 stop all        — Stop everything
 *   pm2 restart all     — Restart all
 *   pm2 delete all      — Remove from PM2
 *
 * Gold Tier additions:
 *   - twitter-watcher
 *   - facebook-watcher
 *   - instagram-watcher
 *   - watchdog (process health monitor)
 *   - weekly-audit (cron: every Monday 7am)
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
    // ── Orchestrator (core routing + scheduler) ──────────────────────────────
    {
      name: "orchestrator",
      script: PYTHON,
      args: `orchestrator.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 5000,
      max_restarts: 10,
      autorestart: true,
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
        SMTP_HOST: envOrDefault("SMTP_HOST", "smtp.gmail.com"),
        SMTP_PORT: envOrDefault("SMTP_PORT", "587"),
        SMTP_USER: envOrDefault("SMTP_USER", ""),
        SMTP_PASSWORD: envOrDefault("SMTP_PASSWORD", ""),
        SMTP_FROM_NAME: envOrDefault("SMTP_FROM_NAME", "AI Employee"),
        CLAUDE_CMD: envOrDefault("CLAUDE_CMD", "claude"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "orchestrator-error.log"),
      out_file: path.join(ROOT, "logs", "orchestrator-out.log"),
    },

    // ── Watchdog (Gold Tier: process health monitor) ──────────────────────────
    {
      name: "watchdog",
      script: PYTHON,
      args: `scripts/watchdog.py --vault ${VAULT} --interval 60`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "watchdog-error.log"),
      out_file: path.join(ROOT, "logs", "watchdog-out.log"),
    },

    // ── File System Watcher (Inbox drop folder) ───────────────────────────────
    {
      name: "fs-watcher",
      script: PYTHON,
      args: `watchers/filesystem_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 3000,
      max_restarts: 20,
      autorestart: true,
      watch: false,
      env: {
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "fs-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "fs-watcher-out.log"),
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
        GMAIL_CREDENTIALS_PATH: envOrDefault("GMAIL_CREDENTIALS_PATH", path.join(ROOT, "watchers/credentials.json")),
        GMAIL_TOKEN_PATH: envOrDefault("GMAIL_TOKEN_PATH", path.join(ROOT, "watchers/token.json")),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "gmail-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "gmail-watcher-out.log"),
    },

    // ── LinkedIn Watcher ──────────────────────────────────────────────────────
    // Uncomment when LinkedIn account is ready:
    // {
    //   name: "linkedin-watcher",
    //   script: PYTHON,
    //   args: `watchers/linkedin_watcher.py --vault ${VAULT}`,
    //   cwd: ROOT,
    //   interpreter: "none",
    //   restart_delay: 10000,
    //   max_restarts: 5,
    //   autorestart: true,
    //   watch: false,
    //   env: {
    //     LINKEDIN_EMAIL: envOrDefault("LINKEDIN_EMAIL", ""),
    //     LINKEDIN_PASSWORD: envOrDefault("LINKEDIN_PASSWORD", ""),
    //     LINKEDIN_SESSION_PATH: envOrDefault("LINKEDIN_SESSION_PATH", path.join(ROOT, ".linkedin_session")),
    //     DRY_RUN: envOrDefault("DRY_RUN", "false"),
    //   },
    // },

    // ── WhatsApp Watcher ──────────────────────────────────────────────────────
    // NOTE: Run --setup manually first to scan the QR code.
    {
      name: "whatsapp-watcher",
      script: PYTHON,
      args: `watchers/whatsapp_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        WHATSAPP_SESSION_PATH: envOrDefault("WHATSAPP_SESSION_PATH", path.join(ROOT, ".whatsapp_session")),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "whatsapp-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "whatsapp-watcher-out.log"),
    },

    // ── Twitter/X Watcher (Gold Tier) ─────────────────────────────────────────
    // Run --setup first: python3 watchers/twitter_watcher.py --vault AI_Employee_Vault --setup
    {
      name: "twitter-watcher",
      script: PYTHON,
      args: `watchers/twitter_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        TWITTER_SESSION_PATH: envOrDefault("TWITTER_SESSION_PATH", path.join(ROOT, ".twitter_session")),
        TWITTER_HANDLE: envOrDefault("TWITTER_HANDLE", ""),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "twitter-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "twitter-watcher-out.log"),
    },

    // ── Facebook Watcher (Gold Tier) ──────────────────────────────────────────
    // Run --setup first: python3 watchers/facebook_watcher.py --vault AI_Employee_Vault --setup
    {
      name: "facebook-watcher",
      script: PYTHON,
      args: `watchers/facebook_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        FACEBOOK_SESSION_PATH: envOrDefault("FACEBOOK_SESSION_PATH", path.join(ROOT, ".facebook_session")),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "facebook-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "facebook-watcher-out.log"),
    },

    // ── Instagram Watcher (Gold Tier) ─────────────────────────────────────────
    // Run --setup first: python3 watchers/instagram_watcher.py --vault AI_Employee_Vault --setup
    {
      name: "instagram-watcher",
      script: PYTHON,
      args: `watchers/instagram_watcher.py --vault ${VAULT}`,
      cwd: ROOT,
      interpreter: "none",
      restart_delay: 10000,
      max_restarts: 5,
      autorestart: true,
      watch: false,
      env: {
        INSTAGRAM_SESSION_PATH: envOrDefault("INSTAGRAM_SESSION_PATH", path.join(ROOT, ".instagram_session")),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "instagram-watcher-error.log"),
      out_file: path.join(ROOT, "logs", "instagram-watcher-out.log"),
    },

    // ── Weekly Audit (Gold Tier) — runs every Monday at 7:00 AM ───────────────
    // PM2 doesn't support cron natively; use setup_cron_gold.sh or crontab for this.
    // This entry is for manual/on-demand runs:
    // pm2 start scripts/pm2.config.js --only weekly-audit
    {
      name: "weekly-audit",
      script: PYTHON,
      args: `scripts/weekly_audit.py --vault ${VAULT} --period 7`,
      cwd: ROOT,
      interpreter: "none",
      autorestart: false,   // run once; triggered by cron
      watch: false,
      env: {
        VAULT_PATH: VAULT,
        ODOO_URL: envOrDefault("ODOO_URL", ""),
        ODOO_DB: envOrDefault("ODOO_DB", "odoo"),
        ODOO_USERNAME: envOrDefault("ODOO_USERNAME", "admin"),
        ODOO_PASSWORD: envOrDefault("ODOO_PASSWORD", "admin"),
        DRY_RUN: envOrDefault("DRY_RUN", "false"),
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: path.join(ROOT, "logs", "weekly-audit-error.log"),
      out_file: path.join(ROOT, "logs", "weekly-audit-out.log"),
    },
  ],
};
