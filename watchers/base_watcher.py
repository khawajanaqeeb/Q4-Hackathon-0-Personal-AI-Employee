"""base_watcher.py - Template for all watchers in the Personal AI Employee system."""

import time
import logging
import json
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class BaseWatcher(ABC):
    """
    Abstract base class for all AI Employee watchers.

    Watchers are the "senses" of the AI Employee — they monitor external
    sources and translate events into .md action files for Claude to process.
    """

    def __init__(self, vault_path: str, check_interval: int = 60):
        self.vault_path = Path(vault_path).resolve()
        self.needs_action = self.vault_path / "Needs_Action"
        self.logs_dir = self.vault_path / "Logs"
        self.check_interval = check_interval
        self.logger = logging.getLogger(self.__class__.__name__)
        self._running = False

        # Validate vault structure
        self._validate_vault()

    def _validate_vault(self):
        """Ensure the vault has required directories."""
        required_dirs = ["Needs_Action", "Done", "Plans", "Logs", "Pending_Approval"]
        missing = []
        for d in required_dirs:
            if not (self.vault_path / d).exists():
                missing.append(d)
        if missing:
            self.logger.warning(f"Missing vault directories: {missing}. Creating them.")
            for d in missing:
                (self.vault_path / d).mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def check_for_updates(self) -> list:
        """Return list of new items to process."""
        pass

    @abstractmethod
    def create_action_file(self, item) -> Path:
        """Create a .md file in the Needs_Action folder."""
        pass

    def log_event(self, event_type: str, details: dict):
        """Write a structured log entry to /Logs/YYYY-MM-DD.json."""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = self.logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "actor": self.__class__.__name__,
            **details,
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text())
            except json.JSONDecodeError:
                entries = []

        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))

    def run(self):
        """Main loop: poll for updates and create action files."""
        self.logger.info(f"Starting {self.__class__.__name__} (interval: {self.check_interval}s)")
        self._running = True

        while self._running:
            try:
                items = self.check_for_updates()
                for item in items:
                    try:
                        filepath = self.create_action_file(item)
                        self.logger.info(f"Created action file: {filepath.name}")
                        self.log_event("action_file_created", {"file": str(filepath.name)})
                    except Exception as e:
                        self.logger.error(f"Failed to create action file for item: {e}")
            except KeyboardInterrupt:
                self.logger.info("Shutdown requested. Stopping watcher.")
                self._running = False
                break
            except Exception as e:
                self.logger.error(f"Error in check_for_updates: {e}")

            if self._running:
                time.sleep(self.check_interval)

        self.logger.info(f"{self.__class__.__name__} stopped.")

    def stop(self):
        """Gracefully stop the watcher."""
        self._running = False
