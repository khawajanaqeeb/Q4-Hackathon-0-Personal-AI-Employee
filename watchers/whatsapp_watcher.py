"""
whatsapp_watcher.py - WhatsApp Web Watcher for Personal AI Employee

Uses Playwright to monitor WhatsApp Web for unread messages containing
priority keywords (urgent, invoice, payment, etc.) and creates action files.

NOTE: WhatsApp Web requires scanning a QR code the first time.
The session is persisted so you only need to scan once.

Setup:
    pip install playwright
    playwright install chromium

    First run (interactive — scan QR code):
    python watchers/whatsapp_watcher.py --vault AI_Employee_Vault --setup

    Normal run (headless after session saved):
    python watchers/whatsapp_watcher.py --vault AI_Employee_Vault

Environment Variables:
    WHATSAPP_SESSION_PATH   Path for persistent browser session (default: .whatsapp_session)
    DRY_RUN=true            Log only, no real actions
"""

import os
import sys
import json
import argparse
import logging
import time
from pathlib import Path
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

# Load .env from project root
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Keywords that trigger action file creation
PRIORITY_KEYWORDS = {
    "P0": ["urgent", "asap", "emergency", "critical"],
    "P1": ["invoice", "payment", "contract", "meeting", "proposal", "help", "issue", "price", "quote"],
    "P2": ["question", "update", "follow up", "check in", "reminder"],
}


def _load_playwright():
    """Import Playwright — gives a clear error if not installed."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print(
            "\n[ERROR] Playwright not installed.\n"
            "Install it with:\n"
            "  pip install playwright\n"
            "  playwright install chromium\n"
        )
        sys.exit(1)


def detect_priority(text: str) -> str:
    """Detect priority based on keyword presence."""
    lower = text.lower()
    for priority, keywords in PRIORITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return priority
    return "P3"


class WhatsAppWatcher(BaseWatcher):
    """
    Playwright-based WhatsApp Web watcher.

    Monitors WhatsApp Web for unread messages containing business keywords.
    Persists browser session so QR code scanning only happens once.

    Architecture note:
    - WhatsApp does not have a public API for message reading.
    - This uses WhatsApp Web (web.whatsapp.com) via browser automation.
    - Be aware of WhatsApp's Terms of Service when using automation.
    """

    def __init__(self, vault_path: str, session_path: str, dry_run: bool = False):
        super().__init__(vault_path, check_interval=30)  # 30-second polling
        self.session_path = Path(session_path).resolve()
        self.dry_run = dry_run
        self.processed_ids: set = self._load_processed_ids()
        self.session_path.mkdir(parents=True, exist_ok=True)
        self._pw = None  # Persistent Playwright instance
        self._context = None
        self._page = None

        if dry_run:
            self.logger.info("DRY RUN mode enabled — no files will be modified.")

    def _load_processed_ids(self) -> set:
        """Load previously processed message IDs."""
        state_file = self.vault_path / ".whatsapp_state.json"
        if state_file.exists():
            try:
                return set(json.loads(state_file.read_text()))
            except Exception:
                return set()
        return set()

    def _save_processed_ids(self):
        """Persist processed IDs."""
        state_file = self.vault_path / ".whatsapp_state.json"
        ids_list = list(self.processed_ids)[-1000:]
        state_file.write_text(json.dumps(ids_list))

    def _get_browser_context(self, playwright, headless: bool = True):
        """Launch (or resume) a persistent Chromium browser session."""
        return playwright.chromium.launch_persistent_context(
            str(self.session_path),
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--start-maximized",
            ],
            ignore_default_args=["--enable-automation"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )

    def setup_session(self):
        """
        Interactive setup: launches a visible browser so the user can
        scan the WhatsApp QR code. Saves the session for future headless runs.

        Strategy: Wait for QR code to disappear (login happened), then wait
        30 seconds for the session to fully sync before saving.
        """
        sync_playwright = _load_playwright()
        self.logger.info("Opening WhatsApp Web for QR code scan...")
        self.logger.info(f"Session will be saved to: {self.session_path}")
        self.logger.info("1. A browser window will open on your desktop.")
        self.logger.info("2. Scan the QR code with WhatsApp on your phone.")
        self.logger.info("3. Wait for the chats to load, then press Ctrl+C to save and exit.")

        with sync_playwright() as p:
            context = self._get_browser_context(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://web.whatsapp.com", timeout=60000)
            self.logger.info("Browser opened. Waiting for QR code to appear...")

            try:
                # Step 1: Wait for the QR code to appear
                try:
                    page.wait_for_selector(
                        '[data-testid="qrcode"], canvas[aria-label="Scan me!"], [data-ref]',
                        timeout=20000,
                    )
                    self.logger.info("QR code visible — scan it with your phone now.")
                except Exception:
                    self.logger.info("QR code not detected (may already be logged in). Continuing...")

                # Step 2: Wait for REAL login — only #side or chat-list count
                # (avoids false positives from the loading/QR page)
                logged_in = False
                self.logger.info("Waiting for you to scan the QR code and chats to load...")
                for _ in range(60):  # 60 x 5s = 5 minutes
                    time.sleep(5)
                    try:
                        has_chats = page.evaluate(
                            """() => !!(
                                document.querySelector('#side') ||
                                document.querySelector('[data-testid="chat-list"]') ||
                                document.querySelector('[aria-label="Chat list"]')
                            )"""
                        )
                        if has_chats:
                            self.logger.info("Chats loaded! Waiting 60 seconds for full session sync...")
                            time.sleep(60)  # Let WhatsApp fully write session to disk
                            logged_in = True
                            break
                    except Exception:
                        continue

                if logged_in:
                    self.logger.info("WhatsApp session saved successfully!")
                else:
                    self.logger.warning(
                        "Could not confirm login. If you see your chats in the browser, "
                        "press Ctrl+C to save and exit — the session may still be usable."
                    )
            except KeyboardInterrupt:
                self.logger.info("Ctrl+C pressed — saving session and exiting.")
            finally:
                context.close()
                self.logger.info(f"Session stored at: {self.session_path}")

    def _scrape_chats(self, page) -> list:
        """Scrape the already-open WhatsApp Web page for unread priority messages."""
        items = []
        try:
            # Make sure we're still on WhatsApp Web
            if "whatsapp.com" not in page.url:
                page.goto("https://web.whatsapp.com", timeout=60000)

            # Wait for chat list (already open — should be fast)
            page.wait_for_selector(
                '#side, [data-testid="chat-list"], [aria-label="Chat list"]',
                timeout=60000,
            )

            # Find unread chats
            unread_chats = page.query_selector_all(
                '[data-testid="cell-frame-container"]:has([data-testid="icon-unread-count"]),'
                '[role="listitem"]:has([data-testid="icon-unread-count"])'
            )

            for chat in unread_chats[:10]:
                try:
                    title_el = chat.query_selector('[data-testid="cell-frame-title"]')
                    sender = title_el.inner_text().strip() if title_el else "Unknown"

                    body_el = chat.query_selector('[data-testid="last-msg"]')
                    preview = body_el.inner_text().strip() if body_el else ""

                    msg_id = f"wa_{hash(sender + preview)}"
                    if msg_id in self.processed_ids:
                        continue

                    priority = detect_priority(preview + " " + sender)
                    items.append({
                        "id": msg_id,
                        "sender": sender,
                        "preview": preview[:400],
                        "priority": priority,
                    })
                except Exception as e:
                    self.logger.debug(f"Error parsing chat: {e}")
                    continue

        except Exception as e:
            self.logger.warning(f"WhatsApp scrape error: {e}")

        return items

    def check_for_updates(self) -> list:
        """
        Scrape WhatsApp Web for unread messages with priority keywords.
        Uses a persistent (non-headless) browser kept open between polls.
        """
        # Lazy-init: open browser once, keep it open
        if not hasattr(self, '_pw') or self._pw is None:
            sync_playwright = _load_playwright()
            self._pw = sync_playwright().__enter__()
            self._context = self._get_browser_context(self._pw, headless=False)
            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
            self.logger.info("Opening WhatsApp Web (non-headless — you can minimise the window)...")
            self._page.goto("https://web.whatsapp.com", timeout=60000)
            try:
                self._page.wait_for_selector(
                    '#side, [data-testid="chat-list"], [aria-label="Chat list"]',
                    timeout=90000,
                )
                self.logger.info("WhatsApp Web loaded. Monitoring started.")
            except Exception:
                self.logger.warning("Chat list not found on startup — may need to re-run --setup.")
                return []

        items = self._scrape_chats(self._page)
        if items:
            self.logger.info(f"Found {len(items)} new WhatsApp messages with priority keywords.")
        return items

    def create_action_file(self, item: dict) -> Path:
        """Create a .md action file for a WhatsApp message."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        priority = item.get("priority", "P2")
        sender = item.get("sender", "Unknown")
        msg_id = str(item.get("id", timestamp))

        safe_sender = "".join(c if c.isalnum() else "_" for c in sender)[:20]
        filename = f"WHATSAPP_{safe_sender}_{timestamp}.md"
        action_file = self.needs_action / filename

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would create: {filename}")
            self.processed_ids.add(msg_id)
            return action_file

        content = f"""---
type: whatsapp_message
source: whatsapp
sender: {sender}
preview: "{item.get('preview', '')[:100].replace('"', "'")}"
received: {datetime.now().isoformat()}
priority: {priority}
status: pending
assigned_to: claude_code
---

## WhatsApp Message from {sender}

**Priority:** {priority}

### Message Preview

> {item.get('preview', '')}

### Suggested Actions

- [ ] Review full conversation in WhatsApp Web
- [ ] Draft reply → create approval file in /Pending_Approval/
- [ ] If invoice request → generate invoice and create email approval
- [ ] If payment question → check /Accounting/ and respond
- [ ] Move to /Done/ after processing

### Notes

_Add context or action taken here._

---
*Created by: WhatsAppWatcher · Silver Tier*
"""
        action_file.write_text(content)
        self.processed_ids.add(msg_id)
        self._save_processed_ids()

        self.log_event("whatsapp_message_detected", {
            "sender": sender,
            "priority": priority,
            "action_file": filename,
        })

        return action_file


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — WhatsApp Watcher (Silver Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First-time setup (scan QR code)
  python watchers/whatsapp_watcher.py --vault AI_Employee_Vault --setup

  # Normal monitoring (headless)
  python watchers/whatsapp_watcher.py --vault AI_Employee_Vault

  # Single check (for cron)
  python watchers/whatsapp_watcher.py --vault AI_Employee_Vault --once

  # Dry-run
  python watchers/whatsapp_watcher.py --vault AI_Employee_Vault --dry-run

Environment variables:
  WHATSAPP_SESSION_PATH   Browser session directory (default: .whatsapp_session)
  DRY_RUN=true            Enable dry-run mode
        """,
    )
    parser.add_argument(
        "--vault",
        default=str(Path(__file__).parent.parent / "AI_Employee_Vault"),
        help="Path to the AI Employee vault",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup to scan WhatsApp QR code",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DRY_RUN,
        help="Log actions without creating files",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check then exit (for cron jobs)",
    )
    parser.add_argument(
        "--session-path",
        default=os.getenv("WHATSAPP_SESSION_PATH", ".whatsapp_session"),
        help="Path for persistent browser session",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        sys.exit(1)

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    watcher = WhatsAppWatcher(str(vault_path), args.session_path, dry_run=args.dry_run)

    if args.setup:
        watcher.setup_session()
        sys.exit(0)

    if args.once:
        items = watcher.check_for_updates()
        for item in items:
            watcher.create_action_file(item)
        print(f"Found and processed {len(items)} WhatsApp messages.")
        sys.exit(0)

    watcher.run()


if __name__ == "__main__":
    main()
