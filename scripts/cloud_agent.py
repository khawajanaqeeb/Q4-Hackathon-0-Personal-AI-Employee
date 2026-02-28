"""
scripts/cloud_agent.py — Cloud Agent Orchestrator (Platinum Tier)

Runs 24/7 on a Cloud VM. Claims tasks from Needs_Action/ by atomic move to
In_Progress/cloud/, drafts email/social replies, writes CLOUD_DRAFT_* files to
Pending_Approval/, and publishes status signals to Signals/.

Work-zone restrictions (enforced):
  - NEVER touches WhatsApp sessions or payment portals
  - NEVER writes Dashboard.md directly (writes to Signals/ only)
  - NEVER executes approved sends (Local does that)
  - Email & social: draft-only, HITL-gated via Pending_Approval/

Usage:
    python3 scripts/cloud_agent.py --vault AI_Employee_Vault
    python3 scripts/cloud_agent.py --vault AI_Employee_Vault --dry-run
    python3 scripts/cloud_agent.py --vault AI_Employee_Vault --once   (single pass)

Environment variables:
    AGENT_MODE=cloud         Must be "cloud" to activate cloud-specific logic
    VAULT_PATH               Override vault path
    DRY_RUN=true             Log without writing files
    CLOUD_POLL_INTERVAL=30   Seconds between Needs_Action/ polls
"""

import os
import sys
import json
import time
import shutil
import logging
import argparse
import re
from pathlib import Path
from datetime import datetime

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CloudAgent] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("CloudAgent")

VAULT_PATH = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault")).resolve()
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
AGENT_MODE = os.getenv("AGENT_MODE", "local")
POLL_INTERVAL = int(os.getenv("CLOUD_POLL_INTERVAL", "30"))

# ─── Safety Check ─────────────────────────────────────────────────────────────

CLOUD_FORBIDDEN_PREFIXES = (
    "WHATSAPP_",
    "PAYMENT_",
    "BANKING_",
)

CLOUD_FORBIDDEN_ACTIONS = {
    "send_whatsapp",
    "whatsapp_message",
    "process_payment",
    "bank_transfer",
}


def _is_forbidden_for_cloud(filename: str, action: str = "") -> bool:
    """Return True if this task is in the cloud-forbidden work zone."""
    name = filename.upper()
    if any(name.startswith(p) for p in CLOUD_FORBIDDEN_PREFIXES):
        return True
    if action in CLOUD_FORBIDDEN_ACTIONS:
        return True
    return False


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _log_event(event_type: str, details: dict):
    """Append to vault's daily log."""
    try:
        logs_dir = VAULT_PATH / "Logs"
        logs_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = logs_dir / f"{today}.json"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "actor": "CloudAgent",
            **details,
        }
        entries = json.loads(log_file.read_text()) if log_file.exists() else []
        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Log write failed: {e}")


def _frontmatter(text: str, key: str, default: str = "") -> str:
    """Extract a frontmatter key value from markdown text."""
    m = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip() if m else default


def _write_signal(status: str, details: dict):
    """Write a status signal file to Signals/ for Local to merge into Dashboard."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would write signal: {status}")
        return
    try:
        signals_dir = VAULT_PATH / "Signals"
        signals_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        sig_file = signals_dir / f"CLOUD_STATUS_{ts}.md"
        sig_file.write_text(
            f"---\n"
            f"agent: cloud\n"
            f"status: {status}\n"
            f"timestamp: {datetime.now().isoformat()}\n"
            f"---\n\n"
            f"# Cloud Agent Signal: {status}\n\n"
            + "\n".join(f"- **{k}**: {v}" for k, v in details.items())
            + "\n"
        )
        logger.info(f"Signal written: {sig_file.name}")
    except Exception as e:
        logger.warning(f"Signal write failed: {e}")


# ─── Claim Protocol ───────────────────────────────────────────────────────────

def claim_task(file_path: Path) -> Path | None:
    """
    Atomic claim: move file from Needs_Action/ → In_Progress/cloud/.
    Returns the new path if claimed, None if already claimed by another agent.
    """
    in_progress_cloud = VAULT_PATH / "In_Progress" / "cloud"
    in_progress_cloud.mkdir(parents=True, exist_ok=True)

    dest = in_progress_cloud / file_path.name
    if dest.exists():
        logger.debug(f"Already claimed: {file_path.name}")
        return None

    if DRY_RUN:
        logger.info(f"[DRY RUN] Would claim: {file_path.name}")
        return file_path  # pretend we claimed it

    try:
        shutil.move(str(file_path), str(dest))
        logger.info(f"Claimed: {file_path.name} → In_Progress/cloud/")
        _log_event("task_claimed", {"file": file_path.name, "agent": "cloud"})
        return dest
    except (FileNotFoundError, PermissionError) as e:
        # Another agent claimed it first (race condition — expected)
        logger.debug(f"Claim failed (likely already claimed): {file_path.name} — {e}")
        return None


def release_to_done(claimed_file: Path, note: str = ""):
    """Move a claimed file to Done/ after processing."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would move to Done/: {claimed_file.name}")
        return
    done_dir = VAULT_PATH / "Done"
    done_dir.mkdir(exist_ok=True)
    dest = done_dir / claimed_file.name
    if dest.exists():
        ts = datetime.now().strftime("%H%M%S")
        dest = done_dir / f"{claimed_file.stem}_{ts}{claimed_file.suffix}"
    shutil.move(str(claimed_file), str(dest))
    logger.info(f"Released to Done/: {dest.name}" + (f" ({note})" if note else ""))


def release_back(claimed_file: Path, reason: str = ""):
    """Return a file to Needs_Action/ if we can't process it."""
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would release back to Needs_Action/: {claimed_file.name}")
        return
    needs_action = VAULT_PATH / "Needs_Action"
    needs_action.mkdir(exist_ok=True)
    dest = needs_action / claimed_file.name
    shutil.move(str(claimed_file), str(dest))
    logger.info(f"Released back to Needs_Action/: {dest.name}" + (f" ({reason})" if reason else ""))


# ─── Draft Writers ────────────────────────────────────────────────────────────

def draft_email_reply(claimed_file: Path):
    """
    Read an email action file, draft a reply, write CLOUD_DRAFT_EMAIL_*.md
    to Pending_Approval/ for human review before Local sends it.
    """
    logger.info(f"Drafting email reply for: {claimed_file.name}")

    try:
        raw = claimed_file.read_text()
        sender = _frontmatter(raw, "sender", "Unknown Sender")
        subject = _frontmatter(raw, "subject", "Re: Your message")
        email_addr = _frontmatter(raw, "email", "")
        urgency = _frontmatter(raw, "urgency", "normal")
        summary = _frontmatter(raw, "summary", "")

        # Extract body for context
        body_match = re.search(r"## (?:Body|Content|Email Body)\s*\n([\s\S]+?)(?=\n##|\Z)", raw)
        body = body_match.group(1).strip() if body_match else raw[:500]

        # Generate a context-aware draft reply
        reply_subject = subject if subject.startswith("Re:") else f"Re: {subject}"

        # Build a professional draft reply template
        draft_reply = (
            f"Hi {sender.split()[0] if sender != 'Unknown Sender' else 'there'},\n\n"
            f"Thank you for reaching out regarding: {subject}.\n\n"
            f"[CLOUD DRAFT — Please review and personalise before sending]\n\n"
            f"I've received your message and will review the details you've shared. "
        )

        if "urgent" in urgency.lower() or "high" in urgency.lower():
            draft_reply += (
                "Given the urgency, I'll prioritise this and get back to you shortly.\n\n"
            )
        else:
            draft_reply += (
                "I'll get back to you with a full response as soon as possible.\n\n"
            )

        if summary:
            draft_reply += f"In the meantime, regarding your point about '{summary}': [ADD YOUR RESPONSE HERE]\n\n"

        draft_reply += (
            "Best regards,\n"
            "[Your Name]\n"
        )

        # Build the approval file
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        approval_name = f"CLOUD_DRAFT_EMAIL_{ts}_{claimed_file.stem[:20]}.md"

        content = (
            f"---\n"
            f"type: cloud_draft_email\n"
            f"source_file: {claimed_file.name}\n"
            f"action: send_email\n"
            f"sender: {sender}\n"
            f"email: {email_addr}\n"
            f"subject: {reply_subject}\n"
            f"urgency: {urgency}\n"
            f"drafted_by: cloud_agent\n"
            f"drafted_at: {datetime.now().isoformat()}\n"
            f"status: pending_approval\n"
            f"---\n\n"
            f"# Cloud Draft: Email Reply\n\n"
            f"**From:** {sender} ({email_addr})\n"
            f"**Subject:** {reply_subject}\n"
            f"**Urgency:** {urgency}\n\n"
            f"## Original Message Summary\n\n"
            f"{summary or body[:300]}\n\n"
            f"## Drafted Reply\n\n"
            f"{draft_reply}\n\n"
            f"---\n"
            f"## Instructions\n\n"
            f"1. Review and edit the drafted reply above\n"
            f"2. Move this file to `Approved/` when satisfied\n"
            f"3. Local orchestrator will send via Email MCP\n\n"
            f"_Drafted by Cloud Agent — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_\n"
        )

        if not DRY_RUN:
            pending_dir = VAULT_PATH / "Pending_Approval"
            pending_dir.mkdir(exist_ok=True)
            approval_file = pending_dir / approval_name
            approval_file.write_text(content)
            logger.info(f"Email draft written: {approval_file.name}")
            _log_event("email_draft_created", {
                "source": claimed_file.name,
                "draft": approval_name,
                "sender": sender,
                "subject": reply_subject,
            })
        else:
            logger.info(f"[DRY RUN] Would write email draft: {approval_name}")

        release_to_done(claimed_file, "email_draft_created")

    except Exception as e:
        logger.error(f"Email draft failed for {claimed_file.name}: {e}", exc_info=True)
        _log_event("email_draft_error", {"file": claimed_file.name, "error": str(e)})
        release_back(claimed_file, "draft_error")


def draft_social_post(claimed_file: Path):
    """
    Read a social post action file, draft post content, write CLOUD_DRAFT_SOCIAL_*.md
    to Pending_Approval/ for human review before Local posts it.
    """
    logger.info(f"Drafting social post for: {claimed_file.name}")

    try:
        raw = claimed_file.read_text()
        platform = _frontmatter(raw, "platform", "social")
        topic = _frontmatter(raw, "topic", "business update")
        tone = _frontmatter(raw, "tone", "professional")
        context = _frontmatter(raw, "context", "")

        # Extract any content block
        content_match = re.search(r"## (?:Content|Context|Details)\s*\n([\s\S]+?)(?=\n##|\Z)", raw)
        content_ctx = content_match.group(1).strip() if content_match else context or topic

        # Generate a platform-appropriate draft
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        platform_upper = platform.upper()
        if "LINKEDIN" in platform_upper:
            draft_content = (
                f"[CLOUD DRAFT — LinkedIn Post]\n\n"
                f"Excited to share an update on {topic}.\n\n"
                f"{content_ctx}\n\n"
                f"What are your thoughts? I'd love to hear from my network.\n\n"
                f"#Business #Growth #{topic.replace(' ', '')}"
            )
        elif "TWITTER" in platform_upper or "X" in platform_upper:
            draft_content = (
                f"[CLOUD DRAFT — Tweet]\n\n"
                f"Update on {topic}: {content_ctx[:200]}\n\n"
                f"#{topic.replace(' ', '')} #AI"
            )
        elif "INSTAGRAM" in platform_upper:
            draft_content = (
                f"[CLOUD DRAFT — Instagram]\n\n"
                f"{content_ctx}\n\n"
                f"#{topic.replace(' ', '')} #business #growth"
            )
        elif "FACEBOOK" in platform_upper:
            draft_content = (
                f"[CLOUD DRAFT — Facebook]\n\n"
                f"Sharing an update about {topic}.\n\n"
                f"{content_ctx}"
            )
        else:
            draft_content = (
                f"[CLOUD DRAFT — Social Post]\n\n"
                f"Topic: {topic}\n\n"
                f"{content_ctx}"
            )

        approval_name = f"CLOUD_DRAFT_SOCIAL_{platform.upper()}_{ts}_{claimed_file.stem[:15]}.md"

        file_content = (
            f"---\n"
            f"type: cloud_draft_social\n"
            f"source_file: {claimed_file.name}\n"
            f"action: post_to_{platform.lower()}\n"
            f"platform: {platform}\n"
            f"topic: {topic}\n"
            f"tone: {tone}\n"
            f"drafted_by: cloud_agent\n"
            f"drafted_at: {datetime.now().isoformat()}\n"
            f"status: pending_approval\n"
            f"---\n\n"
            f"# Cloud Draft: {platform.title()} Post\n\n"
            f"**Platform:** {platform.title()}\n"
            f"**Topic:** {topic}\n"
            f"**Tone:** {tone}\n\n"
            f"## Drafted Content\n\n"
            f"{draft_content}\n\n"
            f"---\n"
            f"## Instructions\n\n"
            f"1. Review and edit the drafted post above\n"
            f"2. Move this file to `Approved/` when satisfied\n"
            f"3. Local orchestrator will post via Social Media MCP\n\n"
            f"_Drafted by Cloud Agent — {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}_\n"
        )

        if not DRY_RUN:
            pending_dir = VAULT_PATH / "Pending_Approval"
            pending_dir.mkdir(exist_ok=True)
            approval_file = pending_dir / approval_name
            approval_file.write_text(file_content)
            logger.info(f"Social draft written: {approval_file.name}")
            _log_event("social_draft_created", {
                "source": claimed_file.name,
                "draft": approval_name,
                "platform": platform,
            })
        else:
            logger.info(f"[DRY RUN] Would write social draft: {approval_name}")

        release_to_done(claimed_file, "social_draft_created")

    except Exception as e:
        logger.error(f"Social draft failed for {claimed_file.name}: {e}", exc_info=True)
        _log_event("social_draft_error", {"file": claimed_file.name, "error": str(e)})
        release_back(claimed_file, "draft_error")


def skip_forbidden(claimed_file: Path, reason: str):
    """Release forbidden-for-cloud task back to Needs_Action for Local to handle."""
    logger.info(f"Skipping (cloud-forbidden): {claimed_file.name} — {reason}")
    _log_event("task_skipped_cloud_forbidden", {
        "file": claimed_file.name,
        "reason": reason,
    })
    release_back(claimed_file, f"cloud_forbidden:{reason}")


# ─── Router ───────────────────────────────────────────────────────────────────

def route_task(claimed_file: Path):
    """Inspect the file and dispatch to the right cloud handler."""
    name = claimed_file.name.upper()

    try:
        raw = claimed_file.read_text()
    except Exception as e:
        logger.error(f"Cannot read claimed file {claimed_file.name}: {e}")
        return

    action = _frontmatter(raw, "action", "")
    file_type = _frontmatter(raw, "type", "")

    # Safety: check for cloud-forbidden work
    if _is_forbidden_for_cloud(claimed_file.name, action):
        skip_forbidden(claimed_file, f"forbidden prefix/action: {action or name}")
        return

    # Email triage → draft reply
    if (
        name.startswith("EMAIL_")
        or file_type in ("email_action", "inbound_email", "gmail_message")
        or action in ("reply_email", "triage_email", "send_email")
    ):
        draft_email_reply(claimed_file)
        return

    # Social post drafts
    if (
        any(kw in name for kw in ("LINKEDIN_", "TWITTER_", "FACEBOOK_", "INSTAGRAM_", "SOCIAL_POST_"))
        or file_type in ("social_post_request", "post_request")
        or action in ("post_to_linkedin", "post_to_twitter", "post_to_facebook", "post_to_instagram", "social_post")
    ):
        # Cloud only drafts — never posts directly
        if "POST" in name or action.startswith("post_"):
            draft_social_post(claimed_file)
            return

    # Unknown — release back for Local to handle
    logger.info(f"No cloud handler for: {claimed_file.name} (action={action}) — releasing to Needs_Action/")
    _log_event("task_no_cloud_handler", {"file": claimed_file.name, "action": action})
    release_back(claimed_file, "no_cloud_handler")


# ─── Already-Claimed Check ────────────────────────────────────────────────────

def _is_already_claimed(filename: str) -> bool:
    """Check if file exists in any In_Progress/ subdirectory."""
    in_progress = VAULT_PATH / "In_Progress"
    for subdir in in_progress.iterdir():
        if subdir.is_dir() and (subdir / filename).exists():
            return True
    return False


# ─── Main Loop ────────────────────────────────────────────────────────────────

def run_once(vault_path: Path) -> int:
    """
    Single pass: claim and process all eligible files in Needs_Action/.
    Returns number of tasks processed.
    """
    needs_action = vault_path / "Needs_Action"
    if not needs_action.exists():
        return 0

    processed = 0
    files = sorted(needs_action.glob("*.md"))

    for f in files:
        if f.name.startswith(".") or f.name == ".gitkeep":
            continue
        if _is_already_claimed(f.name):
            logger.debug(f"Skipping already-claimed: {f.name}")
            continue

        claimed = claim_task(f)
        if claimed is None:
            continue

        route_task(claimed)
        processed += 1

    return processed


def run_agent(vault_path: Path, poll_interval: int = 30):
    """Continuous cloud agent loop."""
    logger.info(f"Cloud Agent starting — vault: {vault_path}")
    logger.info(f"Mode: {AGENT_MODE} | Dry-run: {DRY_RUN} | Poll: {poll_interval}s")

    if AGENT_MODE != "cloud":
        logger.warning(
            "AGENT_MODE is not 'cloud'. Set AGENT_MODE=cloud in .env to enable "
            "cloud-specific work-zone restrictions."
        )

    _log_event("cloud_agent_started", {
        "vault": str(vault_path),
        "dry_run": DRY_RUN,
        "poll_interval": poll_interval,
    })

    tasks_total = 0
    last_signal = datetime.now()

    try:
        while True:
            count = run_once(vault_path)
            tasks_total += count

            if count > 0:
                logger.info(f"Processed {count} task(s) this pass. Total: {tasks_total}")

            # Write status signal every 15 minutes
            now = datetime.now()
            if (now - last_signal).seconds >= 900:
                _write_signal("active", {
                    "last_active": now.isoformat(),
                    "tasks_processed": tasks_total,
                    "poll_interval_s": poll_interval,
                })
                last_signal = now

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        logger.info("Cloud Agent shutdown requested.")
    finally:
        _log_event("cloud_agent_stopped", {"tasks_total": tasks_total})
        _write_signal("stopped", {
            "stopped_at": datetime.now().isoformat(),
            "tasks_processed": tasks_total,
        })
        logger.info("Cloud Agent stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Personal AI Employee — Cloud Agent (Platinum Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run continuously (cloud mode)
  AGENT_MODE=cloud python3 scripts/cloud_agent.py --vault AI_Employee_Vault

  # Single pass (for cron / testing)
  python3 scripts/cloud_agent.py --vault AI_Employee_Vault --once

  # Dry-run (no file writes)
  python3 scripts/cloud_agent.py --vault AI_Employee_Vault --dry-run
        """,
    )
    parser.add_argument("--vault", default=str(VAULT_PATH), help="Path to the AI Employee vault")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN)
    parser.add_argument("--once", action="store_true", help="Single pass and exit")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL, help="Poll interval in seconds")
    args = parser.parse_args()

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    if args.once:
        count = run_once(vault_path)
        logger.info(f"Single pass complete — {count} task(s) processed.")
        sys.exit(0)

    run_agent(vault_path, poll_interval=args.interval)


if __name__ == "__main__":
    main()
