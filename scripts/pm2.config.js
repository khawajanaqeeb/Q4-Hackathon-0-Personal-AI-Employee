/**
 * pm2.config.js — PM2 Process Manager Config for Personal AI Employee (Silver Tier)
 *
 * PM2 keeps all watchers and the orchestrator running 24/7,
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
 */

const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const VAULT = path.join(ROOT, "AI_Employee_Vault");
const PYTHON = process.env.PYTHON_CMD || "python3";

// Load .env values for PM2 env
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

    // ── LinkedIn Watcher — ON HOLD (re-enable when LinkedIn account is ready) ──
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

    // ── Email MCP Server (standalone mode for testing) ────────────────────────
    // The orchestrator imports email_server directly, so this is only needed
    // if you want to run it as a standalone MCP server for Claude Code.
    // {
    //   name: "email-mcp",
    //   script: PYTHON,
    //   args: "mcp_servers/email_server.py",
    //   cwd: ROOT,
    //   interpreter: "none",
    //   autorestart: true,
    //   env: {
    //     SMTP_HOST: envOrDefault("SMTP_HOST", "smtp.gmail.com"),
    //     SMTP_PORT: envOrDefault("SMTP_PORT", "587"),
    //     SMTP_USER: envOrDefault("SMTP_USER", ""),
    //     SMTP_PASSWORD: envOrDefault("SMTP_PASSWORD", ""),
    //     VAULT_PATH: VAULT,
    //     DRY_RUN: envOrDefault("DRY_RUN", "false"),
    //   },
    // },
  ],
};
