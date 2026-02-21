"""
linkedin_watcher.py - LinkedIn Watcher & Poster for Personal AI Employee

Uses Playwright to:
1. Monitor LinkedIn for unread notifications / messages
2. Post business content to LinkedIn (with HITL approval)

This is a Silver Tier watcher — requires Playwright.

Setup:
    pip install playwright
    playwright install chromium

Usage:
    # Monitor only (creates action files from notifications)
    python watchers/linkedin_watcher.py --vault AI_Employee_Vault

    # Post content from an approved post file
    python watchers/linkedin_watcher.py --vault AI_Employee_Vault --post-file /path/to/post.md

    # Dry-run (logs without acting)
    python watchers/linkedin_watcher.py --vault AI_Employee_Vault --dry-run

Environment Variables:
    LINKEDIN_SESSION_PATH   Path to persistent Chromium session (default: .linkedin_session)
    LINKEDIN_EMAIL          LinkedIn login email
    LINKEDIN_PASSWORD       LinkedIn login password
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Keywords that signal a message needs AI attention
PRIORITY_KEYWORDS = [
    "urgent", "asap", "invoice", "payment", "proposal",
    "contract", "meeting", "opportunity", "collaboration",
    "partnership", "job", "hire", "project", "quote",
]


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


class LinkedInWatcher(BaseWatcher):
    """
    Playwright-based LinkedIn watcher.

    Monitors LinkedIn for:
    - Unread messages containing priority keywords
    - New connection requests from relevant profiles
    - Mentions and comments on your posts

    Also handles posting approved business content to LinkedIn.
    """

    def __init__(self, vault_path: str, session_path: str, dry_run: bool = False):
        super().__init__(vault_path, check_interval=300)  # 5 min polling
        self.session_path = Path(session_path).resolve()
        self.dry_run = dry_run
        self.processed_ids: set = self._load_processed_ids()
        self.session_path.mkdir(parents=True, exist_ok=True)

        if dry_run:
            self.logger.info("DRY RUN mode enabled — no LinkedIn actions will be taken.")

    def _load_processed_ids(self) -> set:
        """Load previously seen notification IDs."""
        state_file = self.vault_path / ".linkedin_state.json"
        if state_file.exists():
            try:
                return set(json.loads(state_file.read_text()))
            except Exception:
                return set()
        return set()

    def _save_processed_ids(self):
        """Persist seen IDs to avoid reprocessing."""
        state_file = self.vault_path / ".linkedin_state.json"
        ids_list = list(self.processed_ids)[-500:]
        state_file.write_text(json.dumps(ids_list))

    def _get_browser_context(self, playwright, headless: bool = True):
        """Launch (or resume) a persistent Chromium browser session."""
        return playwright.chromium.launch_persistent_context(
            str(self.session_path),
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    def setup_session(self):
        """
        Interactive setup: launches a visible browser so the user can
        log in and complete any 2FA/CAPTCHA. Saves the session for
        future headless runs.
        """
        sync_playwright = _load_playwright()
        self.logger.info("Opening LinkedIn in visible browser for login/2FA...")
        self.logger.info(f"Session will be saved to: {self.session_path}")
        self.logger.info("Log in and complete any verification, then press Ctrl+C.")

        with sync_playwright() as p:
            context = self._get_browser_context(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.linkedin.com/login", timeout=15000)

            try:
                # Wait until user reaches the feed (logged in successfully)
                page.wait_for_url("**/feed/**", timeout=120000)
                self.logger.info("LinkedIn session established successfully!")
            except Exception:
                self.logger.warning("Timed out waiting for login. Try again.")
            finally:
                context.close()

    def _is_logged_in(self, page) -> bool:
        """Check if the current session is authenticated to LinkedIn."""
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=15000)
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            # Must be on the feed page itself, not redirected to login
            # (login redirect URL contains "feed" in query params, so check the path)
            return page.url.startswith("https://www.linkedin.com/feed")
        except Exception:
            return False

    def _login(self, page) -> bool:
        """Log in to LinkedIn using environment credentials."""
        email = os.getenv("LINKEDIN_EMAIL", "")
        password = os.getenv("LINKEDIN_PASSWORD", "")

        if not email or not password:
            self.logger.error(
                "LinkedIn credentials not set. "
                "Set LINKEDIN_EMAIL and LINKEDIN_PASSWORD in .env"
            )
            return False

        try:
            page.goto("https://www.linkedin.com/login", timeout=15000)
            page.wait_for_selector("#username", timeout=10000)
            page.fill("#username", email)
            page.fill("#password", password)
            page.click("[data-litms-control-urn='login-submit']")
            page.wait_for_load_state("domcontentloaded", timeout=15000)

            if "checkpoint" in page.url or "challenge" in page.url:
                self.logger.warning(
                    "LinkedIn requires manual verification (2FA/CAPTCHA). "
                    "Please complete it in the browser session."
                )
                return False

            logged_in = "feed" in page.url
            if logged_in:
                self.logger.info("LinkedIn login successful.")
            return logged_in

        except Exception as e:
            self.logger.error(f"Login failed: {e}")
            return False

    def check_for_updates(self) -> list:
        """
        Scrape LinkedIn for new notifications and messages.
        Returns list of dicts with notification/message data.
        """
        sync_playwright = _load_playwright()
        items = []

        with sync_playwright() as p:
            context = self._get_browser_context(p)
            page = context.pages[0] if context.pages else context.new_page()

            if not self._is_logged_in(page):
                if not self._login(page):
                    context.close()
                    return items

            # --- Scrape Notifications ---
            try:
                page.goto("https://www.linkedin.com/notifications/", timeout=15000)
                page.wait_for_selector(".nt-card-list", timeout=10000)

                notif_cards = page.query_selector_all(
                    ".nt-card-list .nt-card__text-container"
                )
                for card in notif_cards[:10]:  # Process top 10
                    try:
                        text = card.inner_text().strip()
                        notif_id = card.get_attribute("data-urn") or f"notif_{hash(text)}"
                        if notif_id not in self.processed_ids and len(text) > 10:
                            items.append({
                                "type": "notification",
                                "id": notif_id,
                                "text": text[:500],
                                "priority": self._detect_priority(text),
                            })
                    except Exception:
                        pass

            except Exception as e:
                self.logger.warning(f"Could not scrape notifications: {e}")

            # --- Scrape Messages (unread threads) ---
            try:
                page.goto("https://www.linkedin.com/messaging/", timeout=15000)
                page.wait_for_selector(".msg-conversations-container", timeout=10000)

                unread_threads = page.query_selector_all(
                    ".msg-conversation-listitem--unread"
                )
                for thread in unread_threads[:5]:  # Process top 5 unread
                    try:
                        sender_el = thread.query_selector(".msg-conversation-listitem__participant-names")
                        preview_el = thread.query_selector(".msg-conversation-listitem__message-snippet")
                        sender = sender_el.inner_text().strip() if sender_el else "Unknown"
                        preview = preview_el.inner_text().strip() if preview_el else ""
                        thread_id = f"msg_{hash(sender + preview)}"

                        if thread_id not in self.processed_ids:
                            # Only surface messages with priority keywords
                            if self._detect_priority(preview + " " + sender) in ("P0", "P1"):
                                items.append({
                                    "type": "message",
                                    "id": thread_id,
                                    "sender": sender,
                                    "preview": preview[:300],
                                    "priority": self._detect_priority(preview),
                                })
                    except Exception:
                        pass

            except Exception as e:
                self.logger.warning(f"Could not scrape messages: {e}")

            context.close()

        if items:
            self.logger.info(f"Found {len(items)} new LinkedIn items.")
        return items

    def _detect_priority(self, text: str) -> str:
        """Return priority based on keyword presence in text."""
        lower = text.lower()
        for kw in PRIORITY_KEYWORDS[:5]:  # P0 keywords
            if kw in lower:
                return "P1"
        for kw in PRIORITY_KEYWORDS[5:]:  # P1 keywords
            if kw in lower:
                return "P2"
        return "P3"

    def create_action_file(self, item: dict) -> Path:
        """Create a .md action file for a LinkedIn notification or message."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        item_type = item.get("type", "notification")
        priority = item.get("priority", "P2")
        item_id = str(item.get("id", timestamp))

        filename = f"LINKEDIN_{item_type.upper()}_{timestamp}.md"
        action_file = self.needs_action / filename

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would create: {filename}")
            self.processed_ids.add(item_id)
            return action_file

        if item_type == "message":
            content = f"""---
type: linkedin_message
source: linkedin
sender: {item.get('sender', 'Unknown')}
preview: "{item.get('preview', '')[:100]}"
received: {datetime.now().isoformat()}
priority: {priority}
status: pending
assigned_to: claude_code
---

## LinkedIn Message from {item.get('sender', 'Unknown')}

**Priority:** {priority}

### Message Preview

> {item.get('preview', '')}

### Suggested Actions

- [ ] Read full message on LinkedIn
- [ ] Draft reply → create approval file in /Pending_Approval/
- [ ] If sales opportunity → create Plan in /Plans/
- [ ] Archive after processing

### Notes

_Add context or action taken here._

---
*Created by: LinkedInWatcher · Silver Tier*
"""
        else:  # notification
            content = f"""---
type: linkedin_notification
source: linkedin
received: {datetime.now().isoformat()}
priority: {priority}
status: pending
assigned_to: claude_code
---

## LinkedIn Notification

**Priority:** {priority}

### Notification Text

> {item.get('text', '')}

### Suggested Actions

- [ ] Review notification on LinkedIn
- [ ] Take appropriate action (reply, like, connect)
- [ ] If action needed → create approval file in /Pending_Approval/
- [ ] Archive after processing

---
*Created by: LinkedInWatcher · Silver Tier*
"""

        action_file.write_text(content)
        self.processed_ids.add(item_id)
        self._save_processed_ids()

        self.log_event("linkedin_item_detected", {
            "type": item_type,
            "id": item_id,
            "priority": priority,
            "action_file": filename,
        })

        return action_file

    def post_to_linkedin(self, content: str, hashtags: list[str] | None = None) -> bool:
        """
        Post a business update to LinkedIn.

        Args:
            content: The post text (max ~3000 chars for LinkedIn)
            hashtags: Optional list of hashtags to append

        Returns:
            True if post succeeded, False otherwise
        """
        if hashtags:
            tag_str = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
            full_content = f"{content}\n\n{tag_str}"
        else:
            full_content = content

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would post to LinkedIn:\n{full_content[:200]}...")
            return True

        sync_playwright = _load_playwright()
        success = False

        with sync_playwright() as p:
            context = self._get_browser_context(p)
            page = context.pages[0] if context.pages else context.new_page()

            if not self._is_logged_in(page):
                if not self._login(page):
                    context.close()
                    return False

            try:
                # Navigate to feed and open the post composer
                page.goto("https://www.linkedin.com/feed/", timeout=15000)
                page.wait_for_selector(".share-box-feed-entry__trigger", timeout=10000)

                # Click "Start a post"
                page.click(".share-box-feed-entry__trigger")
                page.wait_for_selector(".ql-editor", timeout=10000)

                # Type the content
                editor = page.query_selector(".ql-editor")
                editor.click()
                editor.type(full_content, delay=20)  # Human-like typing speed

                # Wait a moment before submitting
                time.sleep(2)

                # Click "Post" button
                post_btn = page.query_selector(
                    "[data-control-name='share.post']"
                ) or page.query_selector(".share-actions__primary-action")

                if post_btn:
                    post_btn.click()
                    page.wait_for_load_state("networkidle", timeout=15000)
                    success = True
                    self.logger.info("LinkedIn post published successfully.")
                else:
                    self.logger.error("Could not find LinkedIn post button.")

            except Exception as e:
                self.logger.error(f"LinkedIn post failed: {e}")
                success = False
            finally:
                context.close()

        self.log_event("linkedin_post", {
            "content_preview": full_content[:100],
            "success": success,
        })

        return success


def post_from_approved_file(vault_path: str, post_file: Path, dry_run: bool = False):
    """
    Read an approved LinkedIn post file and publish it.

    The file should have frontmatter with:
        type: linkedin_post
        hashtags: [AI, Business, Automation]
    And the post body below the --- separator.
    """
    import re

    logger = logging.getLogger("LinkedInPoster")

    if not post_file.exists():
        logger.error(f"Post file not found: {post_file}")
        return False

    raw = post_file.read_text()

    # Parse frontmatter
    hashtags = []
    content = raw
    fm_match = re.match(r"^---\n(.*?)\n---\n(.*)", raw, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        content = fm_match.group(2).strip()
        # Extract hashtags
        ht_match = re.search(r"hashtags:\s*\[(.*?)\]", fm_text)
        if ht_match:
            hashtags = [h.strip().strip("'\"") for h in ht_match.group(1).split(",")]

    if not content:
        logger.error("Post file has no content to publish.")
        return False

    session_path = os.getenv("LINKEDIN_SESSION_PATH", ".linkedin_session")
    watcher = LinkedInWatcher(vault_path, session_path, dry_run=dry_run)
    success = watcher.post_to_linkedin(content, hashtags=hashtags)

    if success:
        # Move post file to Done/
        done_dir = Path(vault_path) / "Done"
        done_dir.mkdir(exist_ok=True)
        dest = done_dir / post_file.name
        post_file.rename(dest)
        logger.info(f"Moved post file to Done/: {dest.name}")

    return success


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — LinkedIn Watcher & Poster (Silver Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor LinkedIn for notifications/messages
  python watchers/linkedin_watcher.py --vault AI_Employee_Vault

  # Post approved content to LinkedIn
  python watchers/linkedin_watcher.py --vault AI_Employee_Vault \\
      --post-file AI_Employee_Vault/Approved/LINKEDIN_POST_2026-02-20.md

  # Dry-run (no real actions)
  python watchers/linkedin_watcher.py --vault AI_Employee_Vault --dry-run

Environment variables:
  LINKEDIN_EMAIL          LinkedIn login email
  LINKEDIN_PASSWORD       LinkedIn login password
  LINKEDIN_SESSION_PATH   Persistent browser session path (default: .linkedin_session)
  DRY_RUN=true            Enable dry-run mode
        """,
    )
    parser.add_argument(
        "--vault",
        default=str(Path(__file__).parent.parent / "AI_Employee_Vault"),
        help="Path to the AI Employee vault",
    )
    parser.add_argument(
        "--post-file",
        default=None,
        help="Path to an approved LinkedIn post .md file to publish",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DRY_RUN,
        help="Log actions without executing them",
    )
    parser.add_argument(
        "--session-path",
        default=os.getenv("LINKEDIN_SESSION_PATH", ".linkedin_session"),
        help="Path for persistent browser session",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one check then exit (useful for cron)",
    )
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Run interactive setup to log in and complete 2FA (requires display)",
    )
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        sys.exit(1)

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    # -- Setup mode: interactive login + 2FA --
    if args.setup:
        watcher = LinkedInWatcher(str(vault_path), args.session_path, dry_run=args.dry_run)
        watcher.setup_session()
        sys.exit(0)

    # -- Post mode: publish a pre-approved LinkedIn post --
    if args.post_file:
        post_file = Path(args.post_file)
        success = post_from_approved_file(str(vault_path), post_file, dry_run=args.dry_run)
        sys.exit(0 if success else 1)

    # -- Watch mode: monitor LinkedIn for new items --
    watcher = LinkedInWatcher(str(vault_path), args.session_path, dry_run=args.dry_run)

    if args.once:
        items = watcher.check_for_updates()
        for item in items:
            watcher.create_action_file(item)
        print(f"Found and processed {len(items)} LinkedIn items.")
    else:
        watcher.run()


if __name__ == "__main__":
    main()
