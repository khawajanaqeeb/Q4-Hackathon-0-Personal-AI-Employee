"""
orchestrator.py - Master Orchestrator for Personal AI Employee

The Orchestrator is the "nervous system" that ties all Silver Tier components together:

1. Watches /Approved/ folder for human-approved action files
2. Routes approved actions to the right executor:
   - EMAIL_*.md          → Email MCP Server (send_approved_email)
   - CLOUD_DRAFT_EMAIL_* → Email MCP Server (send approved cloud drafts)
   - LINKEDIN_POST_*     → LinkedIn Watcher (post_to_linkedin)
   - WHATSAPP_*.md       → WhatsApp (log reply — actual send is manual)
   - Generic             → ⚠️ Write NEEDS_MANUAL_ACTION notice to /Needs_Action/ + move to Done/

3. Watches /Inbox/ for new files (delegates to FileSystemWatcher)
4. Scheduled tasks:
   - Every 30 min: trigger /process-inbox (via claude --print)
   - Every day @ 8AM: trigger /morning-briefing
   - Every Sunday @ 7PM: trigger weekly audit
   - Every 30 min (local mode): merge Cloud Agent signals into Dashboard.md

5. Platinum Tier — Claim-by-move protocol:
   - claim_task(): atomic move Needs_Action/ → In_Progress/<agent>/
   - Skips files already claimed in any In_Progress/ subdirectory
   - AGENT_MODE=local: merges Cloud signals on startup + every 30 min

Usage:
    python orchestrator.py --vault AI_Employee_Vault
    python orchestrator.py --vault AI_Employee_Vault --dry-run
    python orchestrator.py --vault AI_Employee_Vault --no-schedule

Environment variables:
    VAULT_PATH          Override vault path
    DRY_RUN=true        Log actions without executing them
    SCHEDULE=false      Disable cron-style scheduling
    CLAUDE_CMD          Override claude command (default: claude)
    AGENT_MODE          "local" (default) or "cloud"
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
AGENT_MODE  = os.getenv("AGENT_MODE", "local")  # "local" or "cloud"


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


# ─── Platinum Tier: Claim-by-Move Protocol ────────────────────────────────────

def claim_task(file_path: Path, agent: str = "local") -> "Path | None":
    """
    Atomic claim: move file from Needs_Action/ → In_Progress/<agent>/.
    Returns the new path if claimed, None if already claimed.
    Prevents double-processing when Cloud and Local agents share the vault.
    """
    in_progress_agent = VAULT_PATH / "In_Progress" / agent
    in_progress_agent.mkdir(parents=True, exist_ok=True)

    dest = in_progress_agent / file_path.name
    if dest.exists():
        logger.debug(f"Already claimed by {agent}: {file_path.name}")
        return None

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would claim: {file_path.name} → In_Progress/{agent}/")
        return file_path

    try:
        shutil.move(str(file_path), str(dest))
        logger.info(f"Claimed: {file_path.name} → In_Progress/{agent}/")
        _log_event("task_claimed", {"file": file_path.name, "agent": agent})
        return dest
    except (FileNotFoundError, PermissionError) as e:
        logger.debug(f"Claim race-condition (another agent got there first): {file_path.name} — {e}")
        return None


def _is_already_in_progress(filename: str) -> bool:
    """Return True if file is in any In_Progress/ subdirectory."""
    in_progress = VAULT_PATH / "In_Progress"
    if not in_progress.exists():
        return False
    for subdir in in_progress.iterdir():
        if subdir.is_dir() and (subdir / filename).exists():
            return True
    return False


def _merge_cloud_signals():
    """Call merge_signals.py to update Dashboard.md with Cloud Agent status."""
    if DRY_RUN:
        logger.info("[DRY RUN] Would merge cloud signals")
        return
    try:
        merge_script = Path(__file__).parent / "scripts" / "merge_signals.py"
        if merge_script.exists():
            result = subprocess.run(
                [sys.executable, str(merge_script), "--vault", str(VAULT_PATH)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                logger.info("Cloud signals merged into Dashboard.md")
            else:
                logger.warning(f"merge_signals.py exited {result.returncode}: {result.stderr[:200]}")
        else:
            logger.debug("merge_signals.py not found — skipping signal merge")
    except Exception as e:
        logger.warning(f"Cloud signal merge failed: {e}")


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


def handle_linkedin(approved_file: Path):
    """Handle approved LinkedIn files: message replies or feed posts."""
    import re

    name = approved_file.name.upper()
    is_reply = "REPLY" in name

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would handle LinkedIn file: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    if is_reply:
        logger.info(f"Sending LinkedIn message reply: {approved_file.name}")
        try:
            raw = approved_file.read_text()
            sender_match = re.search(r"^sender:\s*(.+)$", raw, re.MULTILINE)
            sender = sender_match.group(1).strip() if sender_match else "Unknown"
            reply_match = re.search(r"^##\s+Reply\s*\n([\s\S]+?)(?=\n##|\Z)", raw, re.MULTILINE)
            reply_text = reply_match.group(1).strip() if reply_match else ""
            if not reply_text:
                logger.error(f"No reply text found in: {approved_file.name}")
                _move_to_done(approved_file, "no_reply_text")
                return
            sys.path.insert(0, str(Path(__file__).parent))
            from watchers.linkedin_watcher import LinkedInWatcher
            session_path = os.getenv("LINKEDIN_SESSION_PATH", ".linkedin_session")
            success = LinkedInWatcher.send_message_reply(session_path, sender, reply_text)
            if success:
                _log_event("linkedin_reply_sent", {"file": approved_file.name, "sender": sender, "result": "success"})
                _move_to_done(approved_file, "linkedin_reply_sent")
            else:
                _log_event("linkedin_reply_failed", {"file": approved_file.name, "sender": sender, "result": "failed"})
                _move_to_done(approved_file, "linkedin_reply_failed")
        except Exception as e:
            logger.error(f"LinkedIn reply handler error: {e}", exc_info=True)
            _log_event("linkedin_error", {"file": approved_file.name, "error": str(e)})
            _move_to_done(approved_file, "error")
    else:
        logger.info(f"Publishing LinkedIn post: {approved_file.name}")
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from watchers.linkedin_watcher import post_from_approved_file
            success = post_from_approved_file(str(VAULT_PATH), approved_file, dry_run=DRY_RUN)
            if success:
                _log_event("linkedin_posted", {"file": approved_file.name, "result": "success"})
            else:
                _log_event("linkedin_post_failed", {"file": approved_file.name, "result": "failed"})
        except Exception as e:
            logger.error(f"LinkedIn post handler error: {e}", exc_info=True)
            _log_event("linkedin_error", {"file": approved_file.name, "error": str(e)})


def handle_instagram(approved_file: Path):
    """Handle approved Instagram files.

    - INSTAGRAM_POST_* / APPROVAL_INSTAGRAM_POST_* → post to feed via InstagramWatcher
    - INSTAGRAM_DM_* / APPROVAL_INSTAGRAM_REPLY_* → DM replies (log + archive;
      automated DM sending is blocked by Meta on web)
    """
    name = approved_file.name.upper()
    is_post = "POST" in name or ("REPLY" not in name and "DM" not in name and "NOTIFICATION" not in name)

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would handle Instagram file: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    if is_post:
        logger.info(f"Posting to Instagram feed from: {approved_file.name}")
        try:
            raw = approved_file.read_text()
            import re
            caption_match = re.search(r"^(?:caption|content|text|post):\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
            caption = caption_match.group(1).strip() if caption_match else raw[:280]
            sys.path.insert(0, str(Path(__file__).parent))
            from watchers.instagram_watcher import InstagramWatcher
            session_path = os.getenv("INSTAGRAM_SESSION_PATH", ".instagram_session")
            result = InstagramWatcher.post_to_feed(session_path, image_path="", caption=caption, dry_run=DRY_RUN)
            if result.get("success"):
                _log_event("instagram_posted", {"file": approved_file.name, "result": "success"})
                _move_to_done(approved_file, "instagram_posted")
            else:
                logger.error(f"Instagram post failed: {result.get('error')}")
                _log_event("instagram_post_failed", {"file": approved_file.name, "error": result.get("error")})
                _move_to_done(approved_file, "instagram_post_failed")
        except Exception as e:
            logger.error(f"Instagram handler error: {e}", exc_info=True)
            _log_event("instagram_error", {"file": approved_file.name, "error": str(e)})
            _move_to_done(approved_file, "error")
    else:
        # DM notification or reply — automated DM sending blocked by Meta; archive as reviewed
        logger.info(f"Instagram DM/notification acknowledged and archived: {approved_file.name}")
        _log_event("instagram_dm_acknowledged", {"file": approved_file.name})
        _move_to_done(approved_file, "acknowledged")


def handle_facebook(approved_file: Path):
    """Handle approved Facebook files.

    - APPROVAL_FACEBOOK_REPLY_* / action == send_facebook_reply → send Messenger reply
    - FACEBOOK_POST_* / APPROVAL_FACEBOOK_POST_* → post to page via FacebookWatcher
    - FACEBOOK_NOTIFICATION_* → acknowledge and archive
    """
    import re

    name = approved_file.name.upper()
    is_reply = "REPLY" in name
    is_post = not is_reply and ("POST" in name or ("NOTIFICATION" not in name and "DM" not in name))

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would handle Facebook file: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    if is_reply:
        logger.info(f"Sending Facebook Messenger reply: {approved_file.name}")
        try:
            raw = approved_file.read_text()
            sender_match = re.search(r"^sender:\s*(.+)$", raw, re.MULTILINE)
            sender = sender_match.group(1).strip() if sender_match else "Unknown"
            reply_match = re.search(r"^##\s+Reply\s*\n([\s\S]+?)(?=\n##|\Z)", raw, re.MULTILINE)
            reply_text = reply_match.group(1).strip() if reply_match else ""
            if not reply_text:
                logger.error(f"No reply text found in: {approved_file.name}")
                _move_to_done(approved_file, "no_reply_text")
                return
            sys.path.insert(0, str(Path(__file__).parent))
            from watchers.facebook_watcher import FacebookWatcher
            session_path = os.getenv("FACEBOOK_SESSION_PATH", ".facebook_session")
            result = FacebookWatcher.send_messenger_reply(session_path, sender=sender, reply_text=reply_text)
            if result.get("success"):
                _log_event("facebook_reply_sent", {"file": approved_file.name, "sender": sender, "result": "success"})
                _move_to_done(approved_file, "facebook_reply_sent")
            else:
                logger.error(f"Facebook reply failed: {result.get('error')}")
                _log_event("facebook_reply_failed", {"file": approved_file.name, "sender": sender, "error": result.get("error")})
                _move_to_done(approved_file, "facebook_reply_failed")
        except Exception as e:
            logger.error(f"Facebook reply handler error: {e}", exc_info=True)
            _log_event("facebook_error", {"file": approved_file.name, "error": str(e)})
            _move_to_done(approved_file, "error")
    elif is_post:
        logger.info(f"Posting to Facebook from: {approved_file.name}")
        try:
            raw = approved_file.read_text()
            text_match = re.search(r"^(?:content|text|post|message):\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
            text = text_match.group(1).strip() if text_match else raw[:500]
            sys.path.insert(0, str(Path(__file__).parent))
            from watchers.facebook_watcher import FacebookWatcher
            session_path = os.getenv("FACEBOOK_SESSION_PATH", ".facebook_session")
            result = FacebookWatcher.post_to_page(session_path, text=text, dry_run=DRY_RUN)
            if result.get("success"):
                _log_event("facebook_posted", {"file": approved_file.name, "result": "success"})
                _move_to_done(approved_file, "facebook_posted")
            else:
                logger.error(f"Facebook post failed: {result.get('error')}")
                _log_event("facebook_post_failed", {"file": approved_file.name, "error": result.get("error")})
                _move_to_done(approved_file, "facebook_post_failed")
        except Exception as e:
            logger.error(f"Facebook post handler error: {e}", exc_info=True)
            _log_event("facebook_error", {"file": approved_file.name, "error": str(e)})
            _move_to_done(approved_file, "error")
    else:
        logger.info(f"Facebook notification acknowledged and archived: {approved_file.name}")
        _log_event("facebook_notification_acknowledged", {"file": approved_file.name})
        _move_to_done(approved_file, "acknowledged")


def handle_odoo(approved_file: Path):
    """Handle approved Odoo actions: create partner and draft invoice or quotation.

    Reads frontmatter from APPROVAL_ODOO_*.md:
        partner_name: Client Name
        amount: 15000
        description: Website development — Phase 1
        odoo_action: invoice   (or "quotation")
    """
    import re

    logger.info(f"Processing Odoo action: {approved_file.name}")

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would process Odoo action: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    try:
        raw = approved_file.read_text()

        def _fm(key: str, default: str = "") -> str:
            m = re.search(rf"^{key}:\s*(.+)$", raw, re.MULTILINE)
            return m.group(1).strip() if m else default

        partner_name = _fm("partner_name")
        amount_str = _fm("amount", "0")
        description = _fm("description", "Service")
        odoo_action = _fm("odoo_action", "invoice").lower()  # "invoice" or "quotation"

        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0.0

        if not partner_name:
            logger.error(f"No partner_name in Odoo action file: {approved_file.name}")
            _move_to_done(approved_file, "error_no_partner")
            return

        sys.path.insert(0, str(Path(__file__).parent))
        from mcp_servers.odoo_server import OdooClient
        odoo_dry_run = os.getenv("DRY_RUN", "true").lower() == "true" or os.getenv("ODOO_URL", "") == ""

        if odoo_dry_run:
            logger.info(f"[ODOO MOCK] Would create partner '{partner_name}' and {odoo_action} for ${amount:.2f}")
            _log_event("odoo_action_mock", {
                "file": approved_file.name,
                "partner_name": partner_name,
                "amount": amount,
                "odoo_action": odoo_action,
                "result": "mock_success",
            })
            _move_to_done(approved_file, "odoo_mock")
            return

        odoo = OdooClient(
            os.getenv("ODOO_URL", "http://localhost:8069"),
            os.getenv("ODOO_DB", "odoo"),
            os.getenv("ODOO_USERNAME", "admin"),
            os.getenv("ODOO_PASSWORD", "admin"),
        )
        odoo.authenticate()

        # Search for existing partner
        partners = odoo.search_read(
            "res.partner",
            [["name", "ilike", partner_name]],
            ["id", "name"],
            limit=1,
        )
        if partners:
            partner_id = partners[0]["id"]
            logger.info(f"Found existing Odoo partner: {partner_name} (id={partner_id})")
        else:
            partner_id = odoo.create("res.partner", {"name": partner_name, "customer_rank": 1})
            logger.info(f"Created new Odoo partner: {partner_name} (id={partner_id})")

        if odoo_action == "quotation":
            order_id = odoo.create("sale.order", {
                "partner_id": partner_id,
                "order_line": [(0, 0, {"name": description, "price_unit": amount, "product_uom_qty": 1})],
            })
            logger.info(f"Created Odoo quotation id={order_id} for {partner_name}")
            _log_event("odoo_quotation_created", {
                "file": approved_file.name,
                "partner_name": partner_name,
                "amount": amount,
                "order_id": order_id,
                "result": "success",
            })
        else:
            invoice_id = odoo.create("account.move", {
                "move_type": "out_invoice",
                "partner_id": partner_id,
                "invoice_line_ids": [(0, 0, {"name": description, "price_unit": amount, "quantity": 1})],
            })
            logger.info(f"Created Odoo draft invoice id={invoice_id} for {partner_name}")
            _log_event("odoo_invoice_created", {
                "file": approved_file.name,
                "partner_name": partner_name,
                "amount": amount,
                "invoice_id": invoice_id,
                "result": "success",
            })

        _move_to_done(approved_file, f"odoo_{odoo_action}_created")

    except Exception as e:
        logger.error(f"Odoo handler error: {e}", exc_info=True)
        _log_event("odoo_error", {"file": approved_file.name, "error": str(e)})
        _move_to_done(approved_file, "odoo_error")


def handle_twitter(approved_file: Path):
    """Handle approved Twitter/X files — post tweet via TwitterWatcher."""
    logger.info(f"Posting tweet from: {approved_file.name}")

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would tweet from: {approved_file.name}")
        _move_to_done(approved_file, "dry_run")
        return

    try:
        raw = approved_file.read_text()
        import re
        text_match = re.search(r"^(?:content|text|tweet|post|message):\s*(.+)$", raw, re.MULTILINE | re.IGNORECASE)
        text = text_match.group(1).strip() if text_match else raw[:280]
        sys.path.insert(0, str(Path(__file__).parent))
        from watchers.twitter_watcher import TwitterWatcher
        session_path = os.getenv("TWITTER_SESSION_PATH", ".twitter_session")
        result = TwitterWatcher.post_tweet(session_path, text=text, dry_run=DRY_RUN)
        if result.get("success"):
            _log_event("tweet_posted", {"file": approved_file.name, "result": "success"})
            _move_to_done(approved_file, "tweet_posted")
        else:
            logger.error(f"Tweet failed: {result.get('error')}")
            _log_event("tweet_failed", {"file": approved_file.name, "error": result.get("error")})
            _move_to_done(approved_file, "tweet_failed")
    except Exception as e:
        logger.error(f"Twitter handler error: {e}", exc_info=True)
        _log_event("twitter_error", {"file": approved_file.name, "error": str(e)})
        _move_to_done(approved_file, "error")


def handle_whatsapp(approved_file: Path):
    """Handle approved WhatsApp files.

    WhatsApp Web automation is session-only; log the intent and archive.
    Actual message sending requires manual action in WhatsApp Web.
    """
    logger.info(f"WhatsApp action acknowledged (manual send required): {approved_file.name}")
    _log_event("whatsapp_action_logged", {"file": approved_file.name, "note": "Manual send required via WhatsApp Web"})

    # Write a reminder to Needs_Action so the owner knows to send it manually
    if not DRY_RUN:
        needs_action_dir = VAULT_PATH / "Needs_Action"
        needs_action_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        notice = needs_action_dir / f"WHATSAPP_SEND_{ts}.md"
        try:
            original = approved_file.read_text()
        except Exception:
            original = "(could not read file)"
        notice.write_text(
            f"---\ntype: whatsapp_manual_send\npriority: high\ncreated: {datetime.now().isoformat()}\n---\n\n"
            f"# 📱 Send this WhatsApp Message Manually\n\n"
            f"Open WhatsApp Web and send the message below.\n\n"
            f"## Original Approval\n\n{original}\n\n"
            f"---\n_Created by Orchestrator — WhatsApp send requires manual action_\n"
        )
        logger.info(f"WhatsApp manual send notice created: {notice.name}")

    _move_to_done(approved_file, "whatsapp_logged")


def handle_generic(approved_file: Path, action: str = "unknown"):
    """
    Fallback for approved files the orchestrator cannot execute automatically.
    Writes a NEEDS_MANUAL_ACTION notice to /Needs_Action/ so the owner is alerted,
    then archives the approval file to Done/.
    """
    logger.warning(
        f"⚠️  No automated handler for action '{action}' "
        f"(file: {approved_file.name}). Manual action required — "
        f"notification written to Needs_Action/."
    )

    # Read original file for context to include in the notice
    try:
        original_content = approved_file.read_text()
    except Exception:
        original_content = "(could not read original approval file)"

    # Write a NEEDS_MANUAL_ACTION notice into Needs_Action/
    if not DRY_RUN:
        needs_action_dir = VAULT_PATH / "Needs_Action"
        needs_action_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        notice_path = needs_action_dir / f"NEEDS_MANUAL_ACTION_{ts}_{approved_file.stem[:20]}.md"
        notice_path.write_text(
            f"---\n"
            f"type: manual_action_required\n"
            f"action: {action}\n"
            f"source_file: {approved_file.name}\n"
            f"created: {datetime.now().isoformat()}\n"
            f"priority: high\n"
            f"---\n\n"
            f"# ⚠️ Manual Action Required\n\n"
            f"The orchestrator **approved** this action but has **no automated handler** for it.\n"
            f"You need to complete this manually.\n\n"
            f"## Action\n"
            f"**Type:** `{action}`\n"
            f"**Approval file:** `{approved_file.name}`\n\n"
            f"## Original Approval Details\n\n"
            f"{original_content}\n\n"
            f"---\n"
            f"_Created by: Orchestrator (unhandled action fallback)_\n"
        )
        logger.info(f"Manual action notice written: {notice_path.name}")

    _log_event("manual_action_required", {
        "file": approved_file.name,
        "action": action,
        "reason": "No automated handler for this action type",
    })

    if not DRY_RUN:
        _move_to_done(approved_file, "needs_manual_action")
    else:
        logger.info(f"[DRY RUN] Would move {approved_file.name} to Done/ and write notice")


def handle_cloud_draft(approved_file: Path):
    """
    Route a Cloud-drafted file that has been approved by the user.
    CLOUD_DRAFT_EMAIL_* → handle_email (Local sends via Email MCP)
    CLOUD_DRAFT_SOCIAL_* → dispatch to the right social handler
    """
    name = approved_file.name.upper()
    logger.info(f"Routing approved cloud draft: {approved_file.name}")

    if "EMAIL" in name:
        handle_email(approved_file)
    elif "LINKEDIN" in name:
        handle_linkedin(approved_file)
    elif "TWITTER" in name:
        handle_twitter(approved_file)
    elif "FACEBOOK" in name:
        handle_facebook(approved_file)
    elif "INSTAGRAM" in name:
        handle_instagram(approved_file)
    else:
        # Try action field in frontmatter
        try:
            import re as _re
            raw = approved_file.read_text()
            action_match = _re.search(r"^action:\s*(.+)$", raw, _re.MULTILINE)
            action = action_match.group(1).strip() if action_match else "unknown"
            if "email" in action:
                handle_email(approved_file)
            elif "linkedin" in action:
                handle_linkedin(approved_file)
            elif "twitter" in action:
                handle_twitter(approved_file)
            elif "facebook" in action:
                handle_facebook(approved_file)
            elif "instagram" in action:
                handle_instagram(approved_file)
            else:
                handle_generic(approved_file, action=f"cloud_draft_{action}")
        except Exception:
            handle_generic(approved_file, action="cloud_draft_unknown")


def route_approved_file(approved_file: Path):
    """
    Inspect the filename (and optionally frontmatter) to determine
    which handler to invoke.
    """
    name = approved_file.name.upper()
    logger.info(f"Routing approved file: {approved_file.name}")

    # Platinum Tier: Cloud-drafted files approved by human
    if name.startswith("CLOUD_DRAFT_"):
        handle_cloud_draft(approved_file)
        return

    if name.startswith("EMAIL_"):
        handle_email(approved_file)
    elif name.startswith("APPROVAL_ODOO_") or ("ODOO" in name and name.startswith("APPROVAL_")):
        handle_odoo(approved_file)
    elif name.startswith("LINKEDIN_POST_") or name.startswith("APPROVAL_LINKEDIN_"):
        handle_linkedin(approved_file)
    elif name.startswith("INSTAGRAM_") or ("INSTAGRAM" in name and name.startswith("APPROVAL_")):
        handle_instagram(approved_file)
    elif name.startswith("FACEBOOK_") or ("FACEBOOK" in name and name.startswith("APPROVAL_")):
        handle_facebook(approved_file)
    elif name.startswith("TWITTER_") or ("TWITTER" in name and name.startswith("APPROVAL_")):
        handle_twitter(approved_file)
    elif name.startswith("WHATSAPP_") or ("WHATSAPP" in name and name.startswith("APPROVAL_")):
        handle_whatsapp(approved_file)
    else:
        # Try to read the 'action' field from frontmatter
        try:
            import re
            raw = approved_file.read_text()
            action_match = re.search(r"^action:\s*(.+)$", raw, re.MULTILINE)
            action = action_match.group(1).strip() if action_match else "unknown"
            if action == "send_email":
                handle_email(approved_file)
            elif action in ("post_to_linkedin", "send_linkedin_reply"):
                handle_linkedin(approved_file)
            elif action in ("post_to_instagram", "instagram_dm", "instagram_reply"):
                handle_instagram(approved_file)
            elif action in ("post_to_facebook", "facebook_post", "send_facebook_reply"):
                handle_facebook(approved_file)
            elif action in ("post_tweet", "twitter_post"):
                handle_twitter(approved_file)
            elif action in ("send_whatsapp", "whatsapp_message"):
                handle_whatsapp(approved_file)
            elif action in ("create_client_and_invoice", "create_client_and_quotation", "odoo_action"):
                handle_odoo(approved_file)
            else:
                handle_generic(approved_file, action=action)
        except Exception:
            handle_generic(approved_file, action="unknown")


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


def _merge_signals_task():
    """Platinum Tier: merge Cloud Agent signals into Dashboard.md (local mode only)."""
    if AGENT_MODE == "local":
        _merge_cloud_signals()


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
    logger.info(f"Dry-run: {dry_run} | Scheduling: {enable_schedule} | Agent mode: {AGENT_MODE}")

    _log_event("orchestrator_started", {
        "vault": str(vault_path),
        "dry_run": dry_run,
        "scheduling": enable_schedule,
        "agent_mode": AGENT_MODE,
    })

    # Platinum Tier: merge cloud signals on startup (local mode)
    if AGENT_MODE == "local":
        logger.info("Local mode: merging cloud signals on startup...")
        _merge_cloud_signals()

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
        # Platinum Tier: merge cloud signals every 30 min in local mode
        if AGENT_MODE == "local":
            scheduled_tasks.append(
                Task("merge-signals", _merge_signals_task, interval_seconds=1800)
            )
            logger.info("Platinum: Cloud signal merge scheduled every 30 min (local mode)")
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
