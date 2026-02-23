#!/usr/bin/env python3
"""instagram_watcher.py - Instagram Playwright watcher for Personal AI Employee (Gold Tier).

Monitors Instagram for:
  - Notifications (mentions, comments, DMs)
  - Direct messages with business keywords
  - Business account activity

Creates action files in /Needs_Action/ for Claude to process.

Usage:
    python3 watchers/instagram_watcher.py --vault AI_Employee_Vault --setup
    python3 watchers/instagram_watcher.py --vault AI_Employee_Vault

Environment variables:
    INSTAGRAM_SESSION_PATH  — path to Playwright persistent context dir
    DRY_RUN                 — if "true", skip actual navigation
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("InstagramWatcher")

ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

BUSINESS_KEYWORDS = [
    "collab", "collaboration", "partner", "sponsor", "paid", "promote",
    "pricing", "rate", "invoice", "deal", "hire", "project", "service",
    "dm", "contact", "inquiry", "interested",
]

INSTAGRAM_URL = "https://www.instagram.com"
INSTAGRAM_INBOX_URL = "https://www.instagram.com/direct/inbox/"


class InstagramWatcher(BaseWatcher):
    """Playwright-based Instagram watcher."""

    def __init__(self, vault_path: str, session_path: str):
        super().__init__(vault_path, check_interval=180)  # every 3 min
        self.session_path = Path(session_path)
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        self._processed_ids: set = self._load_processed()

    def _load_processed(self) -> set:
        state_file = self.vault_path / ".instagram_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                return set(data.get("processed_ids", []))
            except Exception:
                pass
        return set()

    def _save_processed(self):
        state_file = self.vault_path / ".instagram_state.json"
        state_file.write_text(json.dumps(
            {"processed_ids": list(self._processed_ids)[-500:]},
            indent=2,
        ))

    def check_for_updates(self) -> list:
        if self.dry_run:
            logger.info("[DRY RUN] Skipping Instagram check.")
            return []
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not installed.")
            return []
        if not self.session_path.exists():
            logger.warning("Instagram session not found. Run --setup first.")
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
                items.extend(self._get_notifications(page))
                items.extend(self._get_dms(page))
                browser.close()
        except PlaywrightTimeout:
            logger.warning("Playwright timeout during Instagram check.")
        except Exception as e:
            logger.error(f"Instagram check failed: {e}")

        return items

    def _get_notifications(self, page) -> list:
        items = []
        try:
            page.goto(INSTAGRAM_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # Use page.click() with fresh selector to avoid stale element reference
            try:
                page.click('[aria-label="Notifications"]', timeout=5000)
                page.wait_for_timeout(2000)
            except Exception:
                # Try alternate selectors if first fails
                try:
                    page.click('a[href="/accounts/activity/"]', timeout=3000)
                    page.wait_for_timeout(2000)
                except Exception:
                    logger.debug("Notifications button not found — skipping")
                    return items

            notif_items = page.query_selector_all('[role="listitem"]')
            for item in notif_items[:15]:
                    try:
                        text = item.inner_text()
                        item_id = f"ig_notif_{hash(text) & 0xFFFFFF:06x}"
                        if item_id in self._processed_ids:
                            continue
                        keywords_found = [kw for kw in BUSINESS_KEYWORDS if kw in text.lower()]
                        items.append({
                            "type": "notification",
                            "id": item_id,
                            "text": text[:500],
                            "keywords": keywords_found,
                            "timestamp": datetime.now().isoformat(),
                        })
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Could not fetch Instagram notifications: {e}")
        return items

    def _get_dms(self, page) -> list:
        items = []
        try:
            page.goto(INSTAGRAM_INBOX_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

            # Find unread DM threads
            threads = page.query_selector_all('[role="listitem"]')
            for thread in threads[:10]:
                try:
                    text = thread.inner_text()
                    keywords_found = [kw for kw in BUSINESS_KEYWORDS if kw in text.lower()]
                    if not keywords_found:
                        continue
                    thread_id = f"ig_dm_{hash(text) & 0xFFFFFF:06x}"
                    if thread_id in self._processed_ids:
                        continue
                    items.append({
                        "type": "dm",
                        "id": thread_id,
                        "text": text[:500],
                        "keywords": keywords_found,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not fetch Instagram DMs: {e}")
        return items

    def create_action_file(self, item: dict) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"INSTAGRAM_{item['type'].upper()}_{timestamp}_{item['id'][:8]}.md"
        keywords = item.get("keywords", [])
        priority = "high" if keywords else "normal"

        content = f"""---
type: instagram_{item['type']}
platform: instagram
id: {item['id']}
received: {item.get("timestamp", datetime.now().isoformat())}
priority: {priority}
status: pending
keywords_detected: {", ".join(keywords) if keywords else "none"}
---

## Instagram {item['type'].title()} Received

**Content:**
{item.get("text", "(no text)")}

## Suggested Actions
- [ ] Review the {item['type']}
- [ ] Draft response (create in /Pending_Approval/ for HITL if needed)
- [ ] Consider collaboration opportunity if relevant
- [ ] Archive after processing

## Keywords Detected
{", ".join(keywords) if keywords else "No business keywords detected."}
"""
        filepath = self.needs_action / filename
        filepath.write_text(content)
        self._processed_ids.add(item["id"])
        self._save_processed()

        self.log_event("instagram_item_detected", {
            "item_type": item["type"],
            "item_id": item["id"],
            "priority": priority,
            "file": filename,
        })
        return filepath

    @classmethod
    def post_to_feed(cls, session_path: str, image_path: str, caption: str, dry_run: bool = False) -> dict:
        """Post to Instagram feed. Requires an image. Called by Social Media MCP server."""
        if dry_run:
            logger.info(f"[DRY RUN] Would post to Instagram: {caption[:80]}...")
            return {"success": True, "dry_run": True, "caption": caption}

        if not PLAYWRIGHT_AVAILABLE:
            return {"success": False, "error": "Playwright not available"}

        # Instagram posting via web is limited; note this for users
        return {
            "success": False,
            "error": (
                "Instagram web posting requires the mobile app or official API. "
                "Use Instagram Graph API (business accounts) for programmatic posting. "
                "See: https://developers.facebook.com/docs/instagram-api"
            ),
            "note": "Caption prepared: " + caption[:200],
        }

    @classmethod
    def post_story_text(cls, session_path: str, text: str, dry_run: bool = False) -> dict:
        """Post a text story to Instagram (via web automation)."""
        if dry_run:
            return {"success": True, "dry_run": True, "text": text}
        # Story posting via web is similarly restricted
        return {
            "success": False,
            "error": "Instagram story posting requires the mobile app or Instagram Graph API.",
            "prepared_text": text,
        }


def setup_session(vault_path: str, session_path: str):
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        sys.exit(1)

    session = Path(session_path)
    session.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Instagram Session Setup")
    print("=" * 60)
    print("A browser window will open. Please log in to Instagram.")
    print("After logging in, press ENTER here to save the session.")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(str(session), headless=False)
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(INSTAGRAM_URL)
        input("\nPress ENTER after logging in to Instagram...\n")
        browser.close()

    print(f"Session saved to: {session}")


def main():
    parser = argparse.ArgumentParser(description="Instagram Watcher (Gold Tier)")
    parser.add_argument("--vault", default=str(VAULT_DEFAULT))
    parser.add_argument(
        "--session",
        default=os.getenv("INSTAGRAM_SESSION_PATH", str(ROOT / ".instagram_session")),
    )
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()

    if args.setup:
        setup_session(args.vault, args.session)
        return

    watcher = InstagramWatcher(vault_path=args.vault, session_path=args.session)
    watcher.run()


if __name__ == "__main__":
    main()
