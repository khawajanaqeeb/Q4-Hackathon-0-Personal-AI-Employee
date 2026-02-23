#!/usr/bin/env python3
"""facebook_watcher.py - Facebook Playwright watcher for Personal AI Employee (Gold Tier).

Monitors Facebook for:
  - Page notifications (comments, mentions)
  - Messenger messages with business keywords
  - Business page activity

Creates action files in /Needs_Action/ for Claude to process.

Usage:
    python3 watchers/facebook_watcher.py --vault AI_Employee_Vault --setup
    python3 watchers/facebook_watcher.py --vault AI_Employee_Vault

Environment variables:
    FACEBOOK_SESSION_PATH  — path to Playwright persistent context dir
    DRY_RUN                — if "true", skip actual navigation
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

logger = logging.getLogger("FacebookWatcher")

ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

BUSINESS_KEYWORDS = [
    # Sales & transactions
    "invoice", "payment", "quote", "pricing", "price", "cost", "fee",
    "buy", "purchase", "order", "checkout", "refund", "discount", "offer",
    # Hiring & work
    "hire", "hiring", "job", "freelance", "contract", "retainer", "rate",
    "availability", "available", "book", "booking", "schedule",
    # Business development
    "collab", "collaboration", "partnership", "partner", "proposal",
    "project", "consulting", "consultant", "service", "agency",
    # Urgency & intent
    "urgent", "asap", "immediately", "deadline", "interested",
    "opportunity", "deal", "negotiate", "discuss", "meeting",
    # Contact intent
    "dm", "message", "email", "call", "contact", "reach out", "connect",
    "inquiry", "enquiry", "question", "help", "support",
    # Social media business
    "sponsor", "sponsorship", "promote", "promotion", "advertisement",
    "ad", "brand deal", "affiliate", "ambassador",
]

FB_URL = "https://www.facebook.com"
FB_NOTIFICATIONS_URL = "https://www.facebook.com/notifications"


class FacebookWatcher(BaseWatcher):
    """Playwright-based Facebook watcher."""

    def __init__(self, vault_path: str, session_path: str):
        super().__init__(vault_path, check_interval=180)  # every 3 min
        self.session_path = Path(session_path)
        self.dry_run = os.getenv("DRY_RUN", "false").lower() == "true"
        self._processed_ids: set = self._load_processed()

    def _load_processed(self) -> set:
        state_file = self.vault_path / ".facebook_state.json"
        if state_file.exists():
            try:
                data = json.loads(state_file.read_text())
                return set(data.get("processed_ids", []))
            except Exception:
                pass
        return set()

    def _save_processed(self):
        state_file = self.vault_path / ".facebook_state.json"
        state_file.write_text(json.dumps(
            {"processed_ids": list(self._processed_ids)[-500:]},
            indent=2,
        ))

    def check_for_updates(self) -> list:
        if self.dry_run:
            logger.info("[DRY RUN] Skipping Facebook check.")
            return []
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not installed.")
            return []
        if not self.session_path.exists():
            logger.warning(f"Facebook session not found. Run --setup first.")
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
                notifications = self._get_notifications(page)
                items.extend(notifications)
                browser.close()
        except PlaywrightTimeout:
            logger.warning("Playwright timeout during Facebook check.")
        except Exception as e:
            logger.error(f"Facebook check failed: {e}")

        return items

    def _get_notifications(self, page) -> list:
        items = []
        try:
            page.goto(FB_NOTIFICATIONS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4000)

            # Try multiple selectors — Facebook's DOM changes frequently
            SELECTORS = [
                '[role="article"]',
                '[role="listitem"]',
                '[data-pagelet="Notifications"] a',
                'div[aria-label*="notification" i]',
                'div[aria-label*="Notification" i]',
                'div[data-store-id] a',
                # Generic feed item fallback
                'div[class*="notif"] a',
            ]

            notif_items = []
            used_selector = None
            for sel in SELECTORS:
                found = page.query_selector_all(sel)
                if found:
                    notif_items = found
                    used_selector = sel
                    logger.info(f"Facebook: found {len(found)} items with selector '{sel}'")
                    break

            if not notif_items:
                # Debug: log what's on the page so we can pick the right selector
                try:
                    body_text = page.inner_text("body")
                    logger.warning(
                        f"Facebook: no notification items found with any selector. "
                        f"Page title: '{page.title()}'. "
                        f"Body snippet: {body_text[:300]!r}"
                    )
                except Exception:
                    logger.warning("Facebook: no notification items found and could not read body.")
                return items

            logger.debug(f"Facebook: using selector '{used_selector}', processing {min(15, len(notif_items))} items")

            for notif in notif_items[:15]:
                try:
                    text = notif.inner_text().strip()
                    if not text:
                        continue
                    notif_id = f"fb_{hash(text) & 0xFFFFFF:06x}"
                    if notif_id in self._processed_ids:
                        continue

                    keywords_found = [kw for kw in BUSINESS_KEYWORDS if kw in text.lower()]
                    items.append({
                        "type": "notification",
                        "id": notif_id,
                        "text": text[:500],
                        "keywords": keywords_found,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Could not fetch Facebook notifications: {e}")
        return items

    def create_action_file(self, item: dict) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"FACEBOOK_{item['type'].upper()}_{timestamp}_{item['id'][:8]}.md"
        keywords = item.get("keywords", [])
        priority = "high" if keywords else "normal"

        content = f"""---
type: facebook_{item['type']}
platform: facebook
id: {item['id']}
received: {item.get("timestamp", datetime.now().isoformat())}
priority: {priority}
status: pending
keywords_detected: {", ".join(keywords) if keywords else "none"}
---

## Facebook {item['type'].title()} Received

**Content:**
{item.get("text", "(no text)")}

## Suggested Actions
- [ ] Review the notification
- [ ] Draft response (create in /Pending_Approval/ for HITL)
- [ ] Archive after processing

## Keywords Detected
{", ".join(keywords) if keywords else "No business keywords detected."}
"""
        filepath = self.needs_action / filename
        filepath.write_text(content)
        self._processed_ids.add(item["id"])
        self._save_processed()

        self.log_event("facebook_item_detected", {
            "item_type": item["type"],
            "item_id": item["id"],
            "priority": priority,
            "file": filename,
        })
        return filepath

    @classmethod
    def post_to_page(cls, session_path: str, text: str, page_url: str = "", dry_run: bool = False) -> dict:
        """Post to Facebook page. Called by Social Media MCP server."""
        if dry_run:
            logger.info(f"[DRY RUN] Would post to Facebook: {text[:80]}...")
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
                target_url = page_url or FB_URL
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(3000)

                # Click "What's on your mind" or create post button
                post_box = page.query_selector('[data-pagelet="FeedComposer"]')
                if not post_box:
                    post_box = page.query_selector('[aria-label*="post"]')

                if post_box:
                    post_box.click()
                    page.wait_for_timeout(1500)

                    # Fill in the text
                    editor = page.query_selector('[role="textbox"][contenteditable="true"]')
                    if editor:
                        editor.fill(text)
                        page.wait_for_timeout(1000)

                        # Click Post button
                        post_btn = page.query_selector('[aria-label="Post"]')
                        if post_btn:
                            post_btn.click()
                            page.wait_for_timeout(3000)
                            browser.close()
                            return {"success": True, "text": text}

                browser.close()
                return {"success": False, "error": "Could not find post composer"}
        except Exception as e:
            return {"success": False, "error": str(e)}


def setup_session(vault_path: str, session_path: str):
    if not PLAYWRIGHT_AVAILABLE:
        print("ERROR: Playwright not installed.")
        sys.exit(1)

    session = Path(session_path)
    session.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Facebook Session Setup")
    print("=" * 60)
    print("A browser window will open. Please log in to Facebook.")
    print("After logging in, press ENTER here to save the session.")
    print("=" * 60)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(str(session), headless=False)
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto(FB_URL)
        input("\nPress ENTER after logging in to Facebook...\n")
        browser.close()

    print(f"Session saved to: {session}")


def main():
    parser = argparse.ArgumentParser(description="Facebook Watcher (Gold Tier)")
    parser.add_argument("--vault", default=str(VAULT_DEFAULT))
    parser.add_argument(
        "--session",
        default=os.getenv("FACEBOOK_SESSION_PATH", str(ROOT / ".facebook_session")),
    )
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()

    if args.setup:
        setup_session(args.vault, args.session)
        return

    watcher = FacebookWatcher(vault_path=args.vault, session_path=args.session)
    watcher.run()


if __name__ == "__main__":
    main()
