#!/usr/bin/env python3
"""watchdog.py - Process health monitor for Personal AI Employee (Gold Tier).

Monitors all watcher and orchestrator processes. Restarts failed processes
automatically. Writes health status to vault and alerts on persistent failures.

Usage:
    python3 scripts/watchdog.py --vault AI_Employee_Vault [--interval 60]
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Watchdog] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Watchdog")

ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

# ── Process registry ──────────────────────────────────────────────────────────
# Each entry: name → {cmd, args, max_restarts, restart_delay}
PROCESS_REGISTRY = {
    "orchestrator": {
        "cmd": [sys.executable, str(ROOT / "orchestrator.py"), "--vault", "{vault}"],
        "max_restarts": 10,
        "restart_delay": 5,
    },
    "fs-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/filesystem_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 20,
        "restart_delay": 3,
    },
    "gmail-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/gmail_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 10,
        "restart_delay": 5,
    },
    "whatsapp-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/whatsapp_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 5,
        "restart_delay": 10,
    },
    "twitter-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/twitter_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 5,
        "restart_delay": 10,
    },
    "facebook-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/facebook_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 5,
        "restart_delay": 10,
    },
    "instagram-watcher": {
        "cmd": [sys.executable, str(ROOT / "watchers/instagram_watcher.py"), "--vault", "{vault}"],
        "max_restarts": 5,
        "restart_delay": 10,
    },
}


class ProcessMonitor:
    """Monitors a single process and restarts it when it dies."""

    def __init__(self, name: str, config: dict, vault: Path):
        self.name = name
        self.config = config
        self.vault = vault
        self.process: subprocess.Popen | None = None
        self.restart_count = 0
        self.last_restart = 0.0
        self.enabled = True

    def _build_cmd(self) -> list:
        return [
            part.replace("{vault}", str(self.vault))
            for part in self.config["cmd"]
        ]

    def start(self):
        cmd = self._build_cmd()
        # Only start if the script exists
        script = cmd[1] if len(cmd) > 1 else cmd[0]
        if not Path(script).exists():
            logger.debug(f"[{self.name}] Script not found: {script} — skipping")
            self.enabled = False
            return

        logger.info(f"[{self.name}] Starting process: {' '.join(cmd)}")
        try:
            log_dir = ROOT / "logs"
            log_dir.mkdir(exist_ok=True)
            out_file = open(log_dir / f"{self.name}-out.log", "a")
            err_file = open(log_dir / f"{self.name}-err.log", "a")
            self.process = subprocess.Popen(
                cmd,
                stdout=out_file,
                stderr=err_file,
                cwd=str(ROOT),
            )
            self.last_restart = time.time()
            logger.info(f"[{self.name}] Started with PID {self.process.pid}")
        except Exception as e:
            logger.error(f"[{self.name}] Failed to start: {e}")
            self.enabled = False

    def check(self) -> bool:
        """Returns True if healthy, False if dead."""
        if not self.enabled:
            return True  # skip disabled processes
        if self.process is None:
            return False
        return self.process.poll() is None  # None means still running

    def restart_if_needed(self) -> bool:
        """Returns True if a restart was attempted."""
        if not self.enabled or self.check():
            return False

        if self.restart_count >= self.config["max_restarts"]:
            if self.enabled:
                logger.error(
                    f"[{self.name}] Max restarts ({self.config['max_restarts']}) reached. "
                    "Disabling. Manual intervention required."
                )
                self.enabled = False
            return False

        delay = self.config.get("restart_delay", 5)
        logger.warning(
            f"[{self.name}] Process died (exit={self.process.returncode if self.process else '?'}). "
            f"Restart {self.restart_count + 1}/{self.config['max_restarts']} in {delay}s..."
        )
        time.sleep(delay)
        self.restart_count += 1
        self.start()
        return True

    def stop(self):
        if self.process and self.process.poll() is None:
            logger.info(f"[{self.name}] Stopping PID {self.process.pid}")
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Watchdog:
    """Master health monitor — runs all process monitors and logs health."""

    def __init__(self, vault: Path, interval: int = 60):
        self.vault = vault
        self.interval = interval
        self._running = False
        self.monitors: dict[str, ProcessMonitor] = {}
        self._build_monitors()

    def _build_monitors(self):
        for name, config in PROCESS_REGISTRY.items():
            self.monitors[name] = ProcessMonitor(name, config, self.vault)

    def start_all(self):
        for monitor in self.monitors.values():
            monitor.start()

    def _write_health_status(self):
        """Write health status to vault Logs."""
        status = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "watchdog_health_check",
            "actor": "Watchdog",
            "processes": {},
        }
        for name, monitor in self.monitors.items():
            healthy = monitor.check()
            status["processes"][name] = {
                "healthy": healthy,
                "enabled": monitor.enabled,
                "restart_count": monitor.restart_count,
                "pid": monitor.process.pid if monitor.process and monitor.process.poll() is None else None,
            }

        # Append to today's log
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.vault / "Logs" / f"{today}.json"
        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text())
            except json.JSONDecodeError:
                entries = []
        entries.append(status)
        log_file.write_text(json.dumps(entries, indent=2))

        # Count unhealthy
        unhealthy = [
            n for n, m in self.monitors.items()
            if m.enabled and not m.check()
        ]
        if unhealthy:
            logger.warning(f"Unhealthy processes: {unhealthy}")
        else:
            logger.info("All monitored processes healthy.")

    def run(self):
        self._running = True
        logger.info(f"Watchdog started. Monitoring {len(self.monitors)} processes every {self.interval}s.")
        self.start_all()

        def _shutdown(sig, frame):
            logger.info("Shutdown signal received.")
            self._running = False

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        while self._running:
            for monitor in self.monitors.values():
                monitor.restart_if_needed()
            self._write_health_status()
            time.sleep(self.interval)

        # Stop all on exit
        for monitor in self.monitors.values():
            monitor.stop()
        logger.info("Watchdog stopped.")


def main():
    parser = argparse.ArgumentParser(description="AI Employee Process Watchdog (Gold Tier)")
    parser.add_argument("--vault", default=str(VAULT_DEFAULT), help="Path to AI_Employee_Vault")
    parser.add_argument("--interval", type=int, default=60, help="Health check interval in seconds")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        logger.error(f"Vault not found: {vault}")
        sys.exit(1)

    watchdog = Watchdog(vault=vault, interval=args.interval)
    watchdog.run()


if __name__ == "__main__":
    main()
