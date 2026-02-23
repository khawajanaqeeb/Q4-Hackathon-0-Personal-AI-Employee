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

    # Selectors that indicate WhatsApp Web is fully loaded and logged in
    CHAT_LIST_SELECTORS = (
        '#side, '
        '[data-testid="chat-list"], '
        '[aria-label="Chat list"], '
        'div[role="grid"], '
        '[data-testid="default-user"], '
        'header[data-testid="chatlist-header"]'
    )

    # Selectors that indicate a QR code is being shown (not logged in)
    QR_SELECTORS = (
        '[data-testid="qrcode"], '
        'canvas[aria-label="Scan me!"], '
        '[data-ref], '
        '[data-testid="intro-title"]'
    )

    def _is_showing_qr(self, page) -> bool:
        """Return True if the page is showing a QR code (not logged in)."""
        try:
            return page.evaluate(
                f"""() => !!(
                    document.querySelector('[data-testid="qrcode"]') ||
                    document.querySelector('canvas[aria-label="Scan me!"]') ||
                    document.querySelector('[data-ref]') ||
                    document.querySelector('[data-testid="intro-title"]')
                )"""
            )
        except Exception:
            return False

    def _is_logged_in(self, page) -> bool:
        """Return True if WhatsApp Web chat list is visible."""
        try:
            return page.evaluate(
                """() => !!(
                    document.querySelector('#side') ||
                    document.querySelector('[data-testid="chat-list"]') ||
                    document.querySelector('[aria-label="Chat list"]') ||
                    document.querySelector('header[data-testid="chatlist-header"]') ||
                    document.querySelector('div[role="grid"]')
                )"""
            )
        except Exception:
            return False

    def setup_session(self):
        """
        Interactive setup: launches a visible browser so the user can
        scan the WhatsApp QR code. Saves the session for future headless runs.
        """
        sync_playwright = _load_playwright()
        self.logger.info("Opening WhatsApp Web for QR code scan...")
        self.logger.info(f"Session will be saved to: {self.session_path}")
        self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.logger.info("1. A browser window will open on your desktop.")
        self.logger.info("2. Open WhatsApp on your phone.")
        self.logger.info("3. Go to Settings → Linked Devices → Link a Device.")
        self.logger.info("4. Scan the QR code shown in the browser.")
        self.logger.info("5. Wait for your chats to appear — script exits automatically.")
        self.logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        with sync_playwright() as p:
            context = self._get_browser_context(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://web.whatsapp.com", timeout=60000)
            self.logger.info("Browser opened. Checking login state...")

            try:
                # Give the page time to load fully
                time.sleep(5)

                if self._is_logged_in(page):
                    self.logger.info("Already logged in! Waiting 15 seconds for session sync...")
                    time.sleep(15)
                    self.logger.info("WhatsApp session confirmed and saved.")
                    context.close()
                    return

                if self._is_showing_qr(page):
                    self.logger.info("QR code visible — scan it with WhatsApp on your phone now.")
                else:
                    self.logger.info("WhatsApp is loading... waiting for QR code or chat list.")

                # Poll every 3 seconds for up to 5 minutes
                logged_in = False
                for attempt in range(100):  # 100 x 3s = 5 minutes
                    time.sleep(3)
                    try:
                        if self._is_logged_in(page):
                            self.logger.info(
                                f"✓ Logged in after {attempt * 3}s! "
                                "Waiting 30 seconds for full session sync..."
                            )
                            time.sleep(30)
                            logged_in = True
                            break
                        elif attempt % 10 == 9:  # Every 30s remind the user
                            self.logger.info(
                                f"Still waiting for QR scan... ({attempt * 3}s elapsed)"
                            )
                    except Exception:
                        continue

                if logged_in:
                    self.logger.info("WhatsApp session saved successfully!")
                    self.logger.info(f"Session stored at: {self.session_path}")
                else:
                    self.logger.warning(
                        "5 minutes elapsed without detecting login. "
                        "If you see your chats in the browser, press Ctrl+C — "
                        "the session may still be usable."
                    )
                    # Wait for Ctrl+C
                    while True:
                        time.sleep(5)

            except KeyboardInterrupt:
                self.logger.info("Ctrl+C pressed — saving session and exiting.")
            finally:
                context.close()
                self.logger.info(f"Session stored at: {self.session_path}")

    # Ordered list of selector strategies for finding unread chat rows.
    # Each entry is a CSS selector string; the first one that returns results wins.
    UNREAD_CHAT_SELECTORS = [
        # Strategy 1: exact data-testid with :has() — works in modern Chromium
        '[data-testid="cell-frame-container"]:has([data-testid="icon-unread-count"])',
        # Strategy 2: listitem variant
        '[role="listitem"]:has([data-testid="icon-unread-count"])',
        # Strategy 3: row variant
        'div[role="row"]:has([data-testid="icon-unread-count"])',
        # Strategy 4: li variant
        'li:has([data-testid="icon-unread-count"])',
        # Strategy 5: fall back to ALL chat rows (filter by keyword below)
        '[data-testid="cell-frame-container"]',
        '[role="listitem"]',
        'div[role="row"]',
    ]

    def _scrape_chats(self, page) -> list:
        """Scrape the already-open WhatsApp Web page for unread priority messages."""
        items = []
        try:
            # Make sure we're still on WhatsApp Web
            if "whatsapp.com" not in page.url:
                page.goto("https://web.whatsapp.com", timeout=60000)

            # Wait for chat list with broad fallback selectors
            page.wait_for_selector(self.CHAT_LIST_SELECTORS, timeout=60000)

            # Find unread chats — try each selector strategy in order
            unread_chats = []
            used_selector = None
            keyword_filter_required = False  # True when falling back to all chats

            for sel in self.UNREAD_CHAT_SELECTORS:
                found = page.query_selector_all(sel)
                if found:
                    unread_chats = found
                    used_selector = sel
                    # If we fell back to a non-unread-specific selector, we'll
                    # filter by keyword content instead of unread badge
                    keyword_filter_required = "[data-testid=\"icon-unread-count\"]" not in sel
                    self.logger.info(
                        f"WhatsApp: found {len(found)} chat row(s) with selector '{sel}' "
                        f"(keyword_filter={keyword_filter_required})"
                    )
                    break

            if not unread_chats:
                try:
                    body_text = page.inner_text("body")
                    self.logger.warning(
                        f"WhatsApp: no chat rows found with any selector. "
                        f"Page title: '{page.title()}'. "
                        f"Body snippet: {body_text[:300]!r}"
                    )
                except Exception:
                    self.logger.warning("WhatsApp: no chat rows found and could not read body.")
                return items

            self.logger.debug(f"WhatsApp: processing up to {min(10, len(unread_chats))} chat row(s).")

            for chat in unread_chats[:10]:
                try:
                    # Sender name — try multiple selectors
                    sender = "Unknown"
                    for sel in [
                        '[data-testid="cell-frame-title"]',
                        'span[title]',
                        '[aria-label] span',
                        'span._ao3e',  # WhatsApp internal class (fallback)
                    ]:
                        el = chat.query_selector(sel)
                        if el:
                            text = el.get_attribute("title") or el.inner_text()
                            if text and text.strip():
                                sender = text.strip()
                                break

                    # Message preview — try multiple selectors
                    preview = ""
                    for sel in [
                        '[data-testid="last-msg"]',
                        '[data-testid="msg-meta"]',
                        'span.copyable-text',
                        'div._ak8l span',  # WhatsApp internal class (fallback)
                    ]:
                        el = chat.query_selector(sel)
                        if el:
                            text = el.inner_text().strip()
                            if text:
                                preview = text
                                break

                    # When falling back to all chats, only process if it has keywords
                    if keyword_filter_required:
                        combined = (sender + " " + preview).lower()
                        all_keywords = [kw for kwlist in PRIORITY_KEYWORDS.values() for kw in kwlist]
                        if not any(kw in combined for kw in all_keywords):
                            continue

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
            self.logger.info("Opening WhatsApp Web (you can minimise the browser window)...")
            self._page.goto("https://web.whatsapp.com", timeout=60000)
            time.sleep(4)  # Let the page settle before checking state

            if self._is_showing_qr(self._page):
                self.logger.error(
                    "WhatsApp Web is showing a QR code — session expired.\n"
                    "  Run setup to re-link your phone:\n"
                    "  python watchers/whatsapp_watcher.py --vault AI_Employee_Vault --setup"
                )
                return []

            try:
                self._page.wait_for_selector(self.CHAT_LIST_SELECTORS, timeout=90000)
                self.logger.info("WhatsApp Web loaded. Monitoring started.")
            except Exception:
                if self._is_showing_qr(self._page):
                    self.logger.error(
                        "QR code detected — session expired. Re-run with --setup to scan QR code."
                    )
                else:
                    self.logger.warning(
                        "Chat list not found after 90s. "
                        "Try --setup to refresh the session."
                    )
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
