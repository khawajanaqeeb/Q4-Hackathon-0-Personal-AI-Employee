"""
filesystem_watcher.py - File System Drop Folder Watcher

Monitors the vault's /Inbox folder for new files. When a file is dropped,
it creates a structured .md action file in /Needs_Action/ for Claude to process.

Usage:
    python filesystem_watcher.py --vault /path/to/AI_Employee_Vault
    python filesystem_watcher.py --vault /path/to/AI_Employee_Vault --dry-run

This is the Bronze Tier watcher — no external API keys required.
"""

import os
import sys
import shutil
import argparse
import logging
from pathlib import Path
from datetime import datetime

import time
import platform

from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

# Add parent dir to path if running standalone
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher


def _is_wsl() -> bool:
    """Detect WSL2 environment where inotify doesn't work on Windows mounts."""
    try:
        with open("/proc/version", "r") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _get_observer() -> Observer:
    """
    Choose the right watchdog observer for the current OS.
    On WSL2 with Windows-mounted paths (/mnt/...), inotify fails silently.
    PollingObserver works universally but uses more CPU.
    """
    if _is_wsl() or platform.system() == "Windows":
        return PollingObserver(timeout=2)
    return Observer()

# Dry-run mode: set DRY_RUN=true in environment to prevent file operations
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# File types to process (skip temp files, hidden files, .gitkeep)
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg",
    ".csv", ".xlsx", ".docx", ".json", ".zip"
}

# Priority keywords in filenames
PRIORITY_KEYWORDS = {
    "urgent": "P0",
    "asap": "P0",
    "important": "P1",
    "invoice": "P1",
    "payment": "P1",
    "contract": "P1",
    "review": "P2",
    "report": "P2",
}


def detect_priority(filename: str) -> str:
    """Detect priority based on filename keywords."""
    lower = filename.lower()
    for keyword, priority in PRIORITY_KEYWORDS.items():
        if keyword in lower:
            return priority
    return "P3"  # Default: low priority


def detect_file_type(suffix: str) -> str:
    """Map file extension to a human-readable type."""
    types = {
        ".pdf": "document",
        ".docx": "document",
        ".txt": "text",
        ".md": "note",
        ".csv": "data",
        ".xlsx": "spreadsheet",
        ".json": "data",
        ".png": "image",
        ".jpg": "image",
        ".jpeg": "image",
        ".zip": "archive",
    }
    return types.get(suffix.lower(), "file")


class InboxDropHandler(FileSystemEventHandler):
    """
    Watchdog event handler for the /Inbox drop folder.

    When a file is created in /Inbox, it:
    1. Copies the file to /Needs_Action/
    2. Creates a companion .md action file with metadata
    3. Logs the event
    """

    def __init__(self, vault_path: str, dry_run: bool = False):
        self.vault_path = Path(vault_path).resolve()
        self.inbox = self.vault_path / "Inbox"
        self.needs_action = self.vault_path / "Needs_Action"
        self.logs_dir = self.vault_path / "Logs"
        self.dry_run = dry_run
        self.logger = logging.getLogger("InboxDropHandler")
        self._processed = set()  # Track processed files to avoid duplicates

    def on_created(self, event):
        """Handle new file creation in /Inbox."""
        if event.is_directory:
            return

        source = Path(event.src_path)

        # Skip hidden files, temp files, .gitkeep
        if source.name.startswith(".") or source.name.startswith("~"):
            return
        if source.suffix not in ALLOWED_EXTENSIONS:
            self.logger.debug(f"Skipping unsupported file: {source.name}")
            return
        if str(source) in self._processed:
            return

        self._processed.add(str(source))
        self.logger.info(f"New file detected: {source.name}")
        self._process_file(source)

    def _process_file(self, source: Path):
        """Process a dropped file: copy it and create an action file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        priority = detect_priority(source.name)
        file_type = detect_file_type(source.suffix)
        file_size = source.stat().st_size if source.exists() else 0

        # Destination filenames
        dest_file = self.needs_action / f"FILE_{timestamp}_{source.name}"
        action_file = self.needs_action / f"FILE_{timestamp}_{source.stem}.md"

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would create action file: {action_file.name}")
            return

        # Copy the original file to Needs_Action
        try:
            shutil.copy2(source, dest_file)
            self.logger.info(f"Copied to Needs_Action: {dest_file.name}")
        except Exception as e:
            self.logger.error(f"Failed to copy file: {e}")
            return

        # Create the .md action file
        action_content = f"""---
type: file_drop
source: inbox
original_name: {source.name}
file_type: {file_type}
file_size_bytes: {file_size}
received: {datetime.now().isoformat()}
priority: {priority}
status: pending
assigned_to: claude_code
---

## File Received: {source.name}

A new **{file_type}** file has been dropped into the Inbox.

| Field | Value |
|-------|-------|
| Original Name | `{source.name}` |
| Type | {file_type} |
| Size | {file_size:,} bytes |
| Priority | {priority} |
| Received | {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} |
| Copied To | `Needs_Action/{dest_file.name}` |

## Suggested Actions

- [ ] Review file contents
- [ ] Categorize and tag appropriately
- [ ] Take action based on file type:
  - If **document/contract**: summarize and flag for review
  - If **invoice**: extract amount and log to Accounting
  - If **data/spreadsheet**: analyze and report key metrics
  - If **image**: describe and categorize
- [ ] Move to `/Done/` when complete

## Notes

_Add your notes here after review._

---
*Created by: FileSystemWatcher · Bronze Tier*
"""
        action_file.write_text(action_content)
        self.logger.info(f"Created action file: {action_file.name}")

        # Log the event
        self._log_event(source, dest_file, action_file, priority)

    def _log_event(self, source: Path, dest: Path, action_file: Path, priority: str):
        """Write a structured log entry."""
        import json

        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "file_dropped",
            "actor": "FileSystemWatcher",
            "source_file": source.name,
            "destination": dest.name,
            "action_file": action_file.name,
            "priority": priority,
            "result": "action_file_created",
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text())
            except json.JSONDecodeError:
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))


class FileSystemWatcher(BaseWatcher):
    """
    High-level file system watcher that wraps the watchdog Observer.

    Monitors the /Inbox folder using OS-native file system events
    (inotify on Linux, FSEvents on macOS, ReadDirectoryChangesW on Windows).
    This is more efficient than polling — zero CPU usage when idle.
    """

    def __init__(self, vault_path: str, dry_run: bool = False):
        super().__init__(vault_path, check_interval=1)
        self.dry_run = dry_run
        self.inbox = self.vault_path / "Inbox"
        self.observer = None

        if dry_run:
            self.logger.info("DRY RUN mode enabled — no files will be modified.")

    def check_for_updates(self) -> list:
        """Not used directly — watchdog handles events via callbacks."""
        return []

    def create_action_file(self, item) -> Path:
        """Not used directly — handler creates files via on_created callback."""
        pass

    def run(self):
        """Start the watchdog observer (with WSL2/Windows polling fallback)."""
        self.logger.info(f"Monitoring /Inbox at: {self.inbox}")
        self.logger.info("Drop files into /Inbox to trigger AI processing.")

        observer_cls = _get_observer()
        if isinstance(observer_cls, PollingObserver):
            self.logger.info("Using PollingObserver (WSL2/Windows filesystem detected).")

        handler = InboxDropHandler(str(self.vault_path), dry_run=self.dry_run)
        self.observer = observer_cls
        self.observer.schedule(handler, str(self.inbox), recursive=False)
        self.observer.start()

        self.log_event("watcher_started", {
            "watching": str(self.inbox),
            "dry_run": self.dry_run,
        })

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested. Stopping watcher.")
            self.observer.stop()

        self.observer.join()
        self.log_event("watcher_stopped", {"reason": "keyboard_interrupt"})
        self.logger.info("FileSystemWatcher stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — File System Watcher (Bronze Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python filesystem_watcher.py --vault ./AI_Employee_Vault
  python filesystem_watcher.py --vault ./AI_Employee_Vault --dry-run

Environment variables:
  DRY_RUN=true    Enable dry-run mode (no file operations)
        """,
    )
    parser.add_argument(
        "--vault",
        default=str(Path(__file__).parent.parent / "AI_Employee_Vault"),
        help="Path to the AI Employee Obsidian vault (default: ../AI_Employee_Vault)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DRY_RUN,
        help="Log actions without executing them",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = FileSystemWatcher(str(vault_path), dry_run=args.dry_run)
    watcher.run()


if __name__ == "__main__":
    main()
