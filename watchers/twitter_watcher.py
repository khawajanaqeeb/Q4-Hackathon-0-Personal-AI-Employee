#!/usr/bin/env python3
"""twitter_watcher.py - Twitter/X Playwright watcher for Personal AI Employee (Gold Tier).

Monitors Twitter/X for:
  - Mentions (@your_handle)
  - Direct Messages with business keywords
  - Replies to your posts

Creates action files in /Needs_Action/ for Claude to process.
Supports posting via saved session (HITL-gated).

Usage:
    # First-time setup (saves session/cookies):
    python3 watchers/twitter_watcher.py --vault AI_Employee_Vault --setup

    # Normal monitoring:
    python3 watchers/twitter_watcher.py --vault AI_Employee_Vault

Environment variables:
    TWITTER_SESSION_PATH  — path to Playwright persistent context dir
    TWITTER_HANDLE        — your @handle (without @) for mention detection
    DRY_RUN               — if "true", creates action files but doesn't navigate
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add parent dir to path for base_watcher import
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("TwitterWatcher")

ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

BUSINESS_KEYWORDS = [
    "invoice", "payment", "quote", "pricing", "hire", "contract",
    "urgent", "asap", "collab", "collaboration", "project", "proposal",
    "partnership", "consulting", "service",
]

TWITTER_URL = "https://x.com"
NOTIFICATIONS_URL = "https://x.com/notifications/mentions"
DM_URL = "https://x.com/messages"


class TwitterWatcher(BaseWatcher):
    """Playwright-based Twitter/X watcher."""

    def __init__(self, vault_path: str, session_path: str, handle: str = ""):
        super().__init__(vault_path, check_interval=120)  # check every 2 min
        self.session_path = Path(session_path)
        self.handle = handle.lstrip("@")
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        self._processed_ids: set = self._load_processed()

    def _load_processed(self) -> set:
        state_file = self.vault_path / ".twitter_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                return set(data.get("processed_ids", []))
            except Exception:
                pass
        return set()

    def _save_processed(self):
        state_file = self.vault_path / ".twitter_state.json"
        state_file.write_text(json.dumps(
            {"processed_ids": list(self._processed_ids)[-500:]},  # keep last 500
            indent=2,
        ))

    def check_for_updates(self) -> list:
        if self.dry_run:
            logger.info("[DRY RUN] Skipping Twitter check.")
            return []
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not installed. Run: pip3 install playwright && playwright install chromium")
            return []
        if not self.session_path.exists():
            logger.warning(f"Twitter session not found at {self.session_path}. Run --setup first.")
            return []

        items = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    str(self.session_path),
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                page = browser.pages[0] if browser.pages else browser.new_page()

                # Check mentions
                mentions = self._get_mentions(page)
                items.extend(mentions)

                # Check DMs
                dms = self._get_dms(page)
                items.extend(dms)

                browser.close()
        except PlaywrightTimeout:
            logger.warning("Playwright timeout during Twitter check.")
        except Exception as e:
            logger.error(f"Twitter check failed: {e}")

        return items

    def _get_mentions(self, page) -> list:
        items = []
        try:
            page.goto(NOTIFICATIONS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Collect mention tweets
            tweets = page.query_selector_all('[data-testid="tweet"]')
            for tweet in tweets[:20]:
                try:
                    tweet_text = tweet.inner_text()
                    # Try to get a unique identifier
                    links = tweet.query_selector_all("a[href*='/status/']")
                    tweet_id = None
                    for link in links:
                        href = link.get_attribute("href") or ""
                        if "/status/" in href:
                            tweet_id = href.split("/status/")[-1].split("/")[0]
                            break

                    if not tweet_id or tweet_id in self._processed_ids:
                        continue

                    items.append({
                        "type": "mention",
                        "id": tweet_id,
                        "text": tweet_text[:500],
                        "url": f"https://x.com/i/web/status/{tweet_id}",
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not fetch mentions: {e}")
        return items

    def _get_dms(self, page) -> list:
        items = []
        try:
            page.goto(DM_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Look for unread DM conversations
            conv_items = page.query_selector_all('[data-testid="conversation"]')
            for conv in conv_items[:10]:
                try:
                    text = conv.inner_text().lower()
                    if not any(kw in text for kw in BUSINESS_KEYWORDS):
                        continue

                    conv_id = f"dm_{hash(text) & 0xFFFFFF:06x}"
                    if conv_id in self._processed_ids:
                        continue

                    items.append({
                        "type": "dm",
                        "id": conv_id,
                        "text": conv.inner_text()[:500],
                        "url": DM_URL,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not fetch DMs: {e}")
        return items

    def create_action_file(self, item: dict) -> Path:
        item_type = item.get("type", "tweet")
        item_id = item.get("id", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"TWITTER_{item_type.upper()}_{timestamp}_{item_id[:8]}.md"

        keywords_found = [kw for kw in BUSINESS_KEYWORDS if kw in item.get("text", "").lower()]
        priority = "high" if keywords_found else "normal"

        content = f"""---
type: twitter_{item_type}
platform: twitter_x
id: {item_id}
received: {item.get("timestamp", datetime.now().isoformat())}
priority: {priority}
status: pending
keywords_detected: {", ".join(keywords_found) if keywords_found else "none"}
url: {item.get("url", "")}
---

## Twitter/X {item_type.title()} Received

**Content:**
{item.get("text", "(no text)")}

## Suggested Actions
- [ ] Review the {item_type}
- [ ] Draft reply (create in /Pending_Approval/ for HITL)
- [ ] Follow up if business opportunity detected
- [ ] Archive after processing

## Keywords Detected
{", ".join(keywords_found) if keywords_found else "No business keywords detected."}
"""
        filepath = self.needs_action / filename
        filepath.write_text(content)
        self._processed_ids.add(item_id)
        self._save_processed()

        self.log_event("twitter_item_detected", {
            "item_type": item_type,
            "item_id": item_id,
            "priority": priority,
            "file": filename,
        })
        return filepath

    @classmethod
    def post_tweet(cls, session_path: str, text: str, dry_run: bool = False) -> dict:
        """Post a tweet. Called by Social Media MCP server."""
        if dry_run:
            logger.info(f"[DRY RUN] Would post tweet: {text[:80]}...")
            return {"success": True, "dry_run": True, "text": text}

        if not PLAYWRIGHT_AVAILABLE:
            return {"success": False, "error": "Playwright not available"}

        session = Path(session_path)
        if not session.exists():
            return {"success": False, "error": f"Session not found: {session_path}"}

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    str(session),
                    headless=True,
                    args=["--no-sandbox"],
                )
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.goto(TWITTER_URL, wait_until="domcontentloaded", timeout=30000)

                # Click compose button
                compose = page.query_selector('[data-testid="SideNav_NewTweet_Button"]')
                if not compose:
                    compose = page.query_selector('[aria-label="Post"]')
                if compose:
                    compose.click()
                    page.wait_for_timeout(2000)

                # Type text
                editor = page.query_selector('[data-testid="tweetTextarea_0"]')
                if editor:
                    editor.fill(text)
                    page.wait_for_timeout(1000)

                    # Click Post button
                    post_btn = page.query_selector('[data-testid="tweetButtonInline"]')
                    if not post_btn:
                        post_btn = page.query_selector('[data-testid="tweetButton"]')
                    if post_btn:
                        post_btn.click()
                        page.wait_for_timeout(3000)
                        browser.close()
                        return {"success": True, "text": text}

                browser.close()
                return {"success": False, "error": "Could not find tweet button"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def setup_session(vault_path: str, session_path: str):
    """Interactive setup: open browser for manual login, then save session."""
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        print("Install: pip3 install playwright && playwright install chromium")
        sys.exit(1)

    session = Path(session_path)
    session.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Twitter/X Session Setup")
    print("=" * 60)
    print(f"A browser window will open. Please log in to Twitter/X.")
    print(f"After logging in, press ENTER here to save the session.")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            str(session),
            headless=False,
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(TWITTER_URL)
        input("\nPress ENTER after logging in to Twitter/X...\n")
        browser.close()

    print(f"Session saved to: {session}")
    print("You can now run the watcher without --setup.")


def main():
    parser = argparse.ArgumentParser(description="Twitter/X Watcher (Gold Tier)")
    parser.add_argument("--vault", default=str(VAULT_DEFAULT), help="Path to AI_Employee_Vault")
    parser.add_argument(
        "--session",
        default=os.getenv("TWITTER_SESSION_PATH", str(ROOT / ".twitter_session")),
        help="Path to Playwright persistent context (session) dir",
    )
    parser.add_argument(
        "--handle",
        default=os.getenv("TWITTER_HANDLE", ""),
        help="Your Twitter handle (without @)",
    )
    parser.add_argument("--setup", action="store_true", help="Run interactive session setup")
    args = parser.parse_args()

    if args.setup:
        setup_session(args.vault, args.session)
        return

    watcher = TwitterWatcher(
        vault_path=args.vault,
        session_path=args.session,
        handle=args.handle,
    )
    watcher.run()


if __name__ == "__main__":
    main()
