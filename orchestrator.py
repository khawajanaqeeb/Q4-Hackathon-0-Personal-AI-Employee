"""
orchestrator.py - Master Orchestrator for Personal AI Employee

The Orchestrator is the "nervous system" that ties all Silver Tier components together:

1. Watches /Approved/ folder for human-approved action files
2. Routes approved actions to the right executor:
   - EMAIL_*.md      → Email MCP Server (send_approved_email)
   - LINKEDIN_POST_* → LinkedIn Watcher (post_to_linkedin)
   - WHATSAPP_*.md   → WhatsApp (log reply — actual send is manual)
   - Generic         → Log and move to Done/

3. Watches /Inbox/ for new files (delegates to FileSystemWatcher)
4. Scheduled tasks:
   - Every 30 min: trigger /process-inbox (via claude --print)
   - Every day @ 8AM: trigger /morning-briefing
   - Every Sunday @ 7PM: trigger weekly audit

Usage:
    python orchestrator.py --vault AI_Employee_Vault
    python orchestrator.py --vault AI_Employee_Vault --dry-run
    python orchestrator.py --vault AI_Employee_Vault --no-schedule

Environment variables:
    VAULT_PATH          Override vault path
    DRY_RUN=true        Log actions without executing them
    SCHEDULE=false      Disable cron-style scheduling
    CLAUDE_CMD          Override claude command (default: claude)
"""

import os
import sys
import json
import time
import shutil
import logging
import argparse
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import platform
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [Orchestrator] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("Orchestrator")

VAULT_PATH  = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault")).resolve()
DRY_RUN     = os.getenv("DRY_RUN", "false").lower() == "true"
CLAUDE_CMD  = os.getenv("CLAUDE_CMD", "claude")


def _is_wsl() -> bool:
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _get_observer():
    if _is_wsl() or platform.system() == "Windows":
        return PollingObserver(timeout=2)
    return Observer()


def _log_event(event_type: str, details: dict):
    """Append to vault's daily log."""
    try:
        logs_dir = VAULT_PATH / "Logs"
        logs_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = logs_dir / f"{today}.json"
        entry = {"timestamp": datetime.now().isoformat(), "event_type": event_type, "actor": "Orchestrator", **details}
        entries = json.loads(log_file.read_text()) if log_file.exists() else []
        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Log write failed: {e}")


def _move_to_done(file_path: Path, note: str = ""):
    """Move an approved/processed file to /Done/."""
    done_dir = VAULT_PATH / "Done"
    done_dir.mkdir(exist_ok=True)
    dest = done_dir / file_path.name
    # Avoid collision
    if dest.exists():
        ts = datetime.now().strftime("%H%M%S")
        dest = done_dir / f"{file_path.stem}_{ts}{file_path.suffix}"
    shutil.move(str(file_path), str(dest))
    logger.info(f"Moved to Done/: {dest.name}" + (f" ({note})" if note else ""))


def _move_to_rejected(file_path: Path, reason: str = ""):
    """Move a file to /Rejected/ (expired or invalid approvals)."""
    rejected_dir = VAULT_PATH / "Rejected"
    rejected_dir.mkdir(exist_ok=True)
    dest = rejected_dir / file_path.name
    shutil.move(str(file_path), str(dest))
    logger.info(f"Moved to Rejected/: {dest.name}" + (f" ({reason})" if reason else ""))


# ─── Action Handlers ──────────────────────────────────────────────────────────

def handle_email(approved_file: Path):
    """Send an approved email via the Email MCP server."""
    logger.info(f"Sending approved email: {approved_file.name}")

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send email from: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    try:
        # Import and call directly (avoids MCP server startup overhead for orchestrator)
        sys.path.insert(0, str(Path(__file__).parent))
        from mcp_servers.email_server import send_approved_email
        success = send_approved_email(approved_file)
        if success:
            _log_event("email_sent", {"file": approved_file.name, "result": "success"})
        else:
            _log_event("email_failed", {"file": approved_file.name, "result": "failed"})
            logger.error(f"Email send failed for: {approved_file.name}")
    except Exception as e:
        logger.error(f"Email handler error: {e}", exc_info=True)
        _log_event("email_error", {"file": approved_file.name, "error": str(e)})


def handle_linkedin_post(approved_file: Path):
    """Publish an approved LinkedIn post."""
    logger.info(f"Publishing LinkedIn post: {approved_file.name}")

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would post to LinkedIn from: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from watchers.linkedin_watcher import post_from_approved_file
        session_path = os.getenv("LINKEDIN_SESSION_PATH", ".linkedin_session")
        success = post_from_approved_file(str(VAULT_PATH), approved_file, dry_run=DRY_RUN)
        if success:
            _log_event("linkedin_posted", {"file": approved_file.name, "result": "success"})
        else:
            _log_event("linkedin_post_failed", {"file": approved_file.name, "result": "failed"})
    except Exception as e:
        logger.error(f"LinkedIn handler error: {e}", exc_info=True)
        _log_event("linkedin_error", {"file": approved_file.name, "error": str(e)})


def handle_generic(approved_file: Path):
    """Log and move generic approved files to Done/."""
    logger.info(f"Approved action file processed: {approved_file.name}")
    _log_event("generic_approved", {"file": approved_file.name})
    if not DRY_RUN:
        _move_to_done(approved_file, "approved")
    else:
        logger.info(f"[DRY RUN] Would move {approved_file.name} to Done/")


def route_approved_file(approved_file: Path):
    """
    Inspect the filename (and optionally frontmatter) to determine
    which handler to invoke.
    """
    name = approved_file.name.upper()
    logger.info(f"Routing approved file: {approved_file.name}")

    if name.startswith("EMAIL_"):
        handle_email(approved_file)
    elif name.startswith("LINKEDIN_POST_"):
        handle_linkedin_post(approved_file)
    else:
        # Try to read the 'action' field from frontmatter
        try:
            import re
            raw = approved_file.read_text()
            action_match = re.search(r"^action:\s*(.+)$", raw, re.MULTILINE)
            action = action_match.group(1).strip() if action_match else "unknown"
            if action == "send_email":
                handle_email(approved_file)
            elif action == "post_to_linkedin":
                handle_linkedin_post(approved_file)
            else:
                handle_generic(approved_file)
        except Exception:
            handle_generic(approved_file)


# ─── Approved Folder Watcher ──────────────────────────────────────────────────

class ApprovedFolderHandler(FileSystemEventHandler):
    """
    Watchdog handler for the /Approved/ folder.
    When a file is moved/created here, route it to the right handler.
    """

    def __init__(self):
        self._processed = set()

    def on_created(self, event):
        self._handle(event)

    def on_moved(self, event):
        """Handle files moved INTO /Approved/ (most common human action)."""
        if not event.is_directory:
            self._handle_path(Path(event.dest_path))

    def _handle(self, event):
        if not event.is_directory:
            self._handle_path(Path(event.src_path))

    def _handle_path(self, path: Path):
        if path.suffix not in (".md", ".json", ".txt"):
            return
        if path.name.startswith(".") or path.name == ".gitkeep":
            return
        if str(path) in self._processed:
            return

        self._processed.add(str(path))
        # Small delay to ensure file is fully written
        time.sleep(0.5)

        if path.exists():
            try:
                route_approved_file(path)
            except Exception as e:
                logger.error(f"Error routing {path.name}: {e}", exc_info=True)


# ─── Scheduler ────────────────────────────────────────────────────────────────

class Task:
    """A scheduled task with a callable and next-run time."""

    def __init__(self, name: str, fn: Callable, interval_seconds: int, run_at_start: bool = False):
        self.name = name
        self.fn = fn
        self.interval = interval_seconds
        self.next_run = datetime.now() if run_at_start else datetime.now() + timedelta(seconds=interval_seconds)

    def is_due(self) -> bool:
        return datetime.now() >= self.next_run

    def run(self):
        try:
            logger.info(f"Scheduled task: {self.name}")
            self.fn()
        except Exception as e:
            logger.error(f"Scheduled task '{self.name}' failed: {e}", exc_info=True)
        finally:
            self.next_run = datetime.now() + timedelta(seconds=self.interval)


def _run_claude_skill(skill_name: str):
    """Run a Claude Code slash command non-interactively."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would run Claude skill: /{skill_name}")
        return

    cmd = [CLAUDE_CMD, "--print", f"/{skill_name}"]
    logger.info(f"Running Claude skill: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(Path(__file__).parent),
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
        )
        if result.returncode == 0:
            logger.info(f"/{skill_name} completed successfully.")
            _log_event(f"scheduled_{skill_name}", {"result": "success"})
        else:
            logger.warning(f"/{skill_name} exited with code {result.returncode}")
            logger.debug(f"stderr: {result.stderr[:500]}")
            _log_event(f"scheduled_{skill_name}", {"result": "failed", "code": result.returncode})
    except subprocess.TimeoutExpired:
        logger.warning(f"/{skill_name} timed out after 5 minutes.")
    except FileNotFoundError:
        logger.warning(f"'claude' command not found. Skill /{skill_name} skipped.")
        logger.info("To enable scheduled Claude skills, install Claude Code: npm install -g @anthropic/claude-code")


def _is_morning(hour: int = 8) -> bool:
    return datetime.now().hour == hour and datetime.now().minute < 5


def _process_inbox_task():
    _run_claude_skill("process-inbox")


def _morning_briefing_task():
    if _is_morning():
        _run_claude_skill("morning-briefing")


def _weekly_audit_task():
    """Sunday audit — run /morning-briefing with weekly context."""
    if datetime.now().weekday() == 6:  # Sunday
        _run_claude_skill("morning-briefing")


def _update_dashboard_task():
    _run_claude_skill("update-dashboard")


# ─── Main Orchestrator Loop ───────────────────────────────────────────────────

def run_orchestrator(vault_path: Path, enable_schedule: bool = True, dry_run: bool = False):
    """
    Main orchestrator loop:
    1. Watch /Approved/ for human-approved files
    2. Run scheduled tasks (inbox processing, briefings)
    """
    approved_dir = vault_path / "Approved"
    approved_dir.mkdir(exist_ok=True)

    logger.info(f"Orchestrator starting — vault: {vault_path}")
    logger.info(f"Dry-run: {dry_run} | Scheduling: {enable_schedule}")

    _log_event("orchestrator_started", {
        "vault": str(vault_path),
        "dry_run": dry_run,
        "scheduling": enable_schedule,
    })

    # --- Set up /Approved/ folder watcher ---
    observer = _get_observer()
    handler = ApprovedFolderHandler()
    observer.schedule(handler, str(approved_dir), recursive=False)
    observer.start()
    logger.info(f"Watching /Approved/ for human-approved actions.")

    # --- Set up scheduled tasks ---
    scheduled_tasks = []
    if enable_schedule:
        scheduled_tasks = [
            Task("process-inbox",    _process_inbox_task,    interval_seconds=1800),  # every 30 min
            Task("update-dashboard", _update_dashboard_task, interval_seconds=3600),  # every 1 hour
            Task("morning-briefing", _morning_briefing_task, interval_seconds=300),   # check every 5 min
            Task("weekly-audit",     _weekly_audit_task,     interval_seconds=3600),  # check hourly
        ]
        logger.info(f"Scheduler active: {len(scheduled_tasks)} tasks registered.")

    # --- Main loop ---
    try:
        while True:
            for task in scheduled_tasks:
                if task.is_due():
                    task.run()
            time.sleep(5)  # Check schedule every 5 seconds

    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    finally:
        observer.stop()
        observer.join()
        _log_event("orchestrator_stopped", {"reason": "keyboard_interrupt"})
        logger.info("Orchestrator stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Master Orchestrator (Silver Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start orchestrator (watches /Approved/ + runs schedule)
  python orchestrator.py --vault AI_Employee_Vault

  # No scheduling (just watch /Approved/)
  python orchestrator.py --vault AI_Employee_Vault --no-schedule

  # Dry-run (log only, no real actions)
  python orchestrator.py --vault AI_Employee_Vault --dry-run

  # Route a single approved file and exit
  python orchestrator.py --vault AI_Employee_Vault \\
      --send-now AI_Employee_Vault/Approved/EMAIL_draft.md
        """,
    )
    parser.add_argument(
        "--vault",
        default=str(VAULT_PATH),
        help="Path to the AI Employee vault",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DRY_RUN,
        help="Log actions without executing them",
    )
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help="Disable the built-in task scheduler",
    )
    parser.add_argument(
        "--send-now",
        metavar="FILE",
        help="Immediately route a specific approved file and exit",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        sys.exit(1)

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    if args.send_now:
        route_approved_file(Path(args.send_now))
        sys.exit(0)

    run_orchestrator(
        vault_path=vault_path,
        enable_schedule=not args.no_schedule,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
