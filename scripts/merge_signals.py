"""
scripts/merge_signals.py — Merge Cloud Signals into Dashboard.md (Platinum Tier)

Local-only script. Reads Cloud-written signal files from Signals/, extracts
structured status data, and upserts a "Cloud Agent Status" section in Dashboard.md.
Archives processed signals to Done/.

Called by:
  - Local orchestrator on startup
  - Local orchestrator every 30 minutes
  - User via /cloud-status skill

Usage:
    python3 scripts/merge_signals.py --vault AI_Employee_Vault
"""

import os
import re
import json
import shutil
import logging
import argparse
from pathlib import Path
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MergeSignals] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("MergeSignals")

VAULT_PATH = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault")).resolve()
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


def _parse_signal(sig_file: Path) -> dict:
    """Extract structured data from a signal file's frontmatter and body."""
    try:
        raw = sig_file.read_text()
    except Exception:
        return {}

    data = {"file": sig_file.name}

    # Parse frontmatter
    fm_match = re.search(r"^---\n([\s\S]+?)\n---", raw)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ": " in line:
                k, _, v = line.partition(": ")
                data[k.strip()] = v.strip()

    # Parse bullet-point body values
    for m in re.finditer(r"- \*\*(.+?)\*\*: (.+)", raw):
        data[m.group(1).strip()] = m.group(2).strip()

    return data


def _format_signal_section(signals: list[dict]) -> str:
    """Format signal data into a Dashboard.md section."""
    if not signals:
        return (
            "\n## ☁️ Cloud Agent Status\n\n"
            "_No cloud signals received yet._\n"
        )

    # Find most recent status signal
    status_signals = [s for s in signals if s.get("type") == "sync_status" or "CLOUD_STATUS" in s.get("file", "")]
    sync_signals = [s for s in signals if "SYNC_STATUS" in s.get("file", "")]

    # Most recent cloud status
    latest = max(signals, key=lambda s: s.get("timestamp", ""), default={})
    cloud_status = latest.get("status", "unknown")
    last_active = latest.get("last_active") or latest.get("timestamp", "unknown")
    tasks_processed = latest.get("tasks_processed", "unknown")

    # Sync status
    sync_latest = sync_signals[-1] if sync_signals else {}
    sync_status = sync_latest.get("status", "unknown")
    sync_time = sync_latest.get("timestamp", "unknown")
    files_updated = sync_latest.get("files_updated", "0")

    # Count pending cloud drafts
    pending_dir = VAULT_PATH / "Pending_Approval"
    cloud_drafts = []
    if pending_dir.exists():
        cloud_drafts = [f.name for f in pending_dir.glob("CLOUD_DRAFT_*.md")]

    # In-progress cloud tasks
    ip_cloud = VAULT_PATH / "In_Progress" / "cloud"
    in_progress = []
    if ip_cloud.exists():
        in_progress = [f.name for f in ip_cloud.glob("*.md")]

    lines = [
        "",
        "## ☁️ Cloud Agent Status",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Status | {cloud_status} |",
        f"| Last Active | {last_active} |",
        f"| Tasks Processed | {tasks_processed} |",
        f"| Vault Sync | {sync_status} ({sync_time}) |",
        f"| Files Updated (last sync) | {files_updated} |",
        f"| Pending Cloud Drafts | {len(cloud_drafts)} |",
        f"| In-Progress (Cloud) | {len(in_progress)} |",
        "",
    ]

    if cloud_drafts:
        lines.append("### Pending Cloud Drafts (awaiting your approval)")
        for d in cloud_drafts[:10]:
            lines.append(f"- [ ] `{d}`")
        lines.append("")

    if in_progress:
        lines.append("### In-Progress (Cloud claiming)")
        for ip in in_progress[:5]:
            lines.append(f"- `{ip}`")
        lines.append("")

    lines.append(f"_Last merged: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    lines.append("")

    return "\n".join(lines)


def merge_signals(vault_path: Path) -> int:
    """
    Read all Signals/CLOUD_*.md files, merge into Dashboard.md.
    Archives processed signals to Done/.
    Returns number of signals processed.
    """
    signals_dir = vault_path / "Signals"
    dashboard_path = vault_path / "Dashboard.md"

    if not signals_dir.exists():
        logger.info("No Signals/ directory found — nothing to merge.")
        return 0

    signal_files = sorted(signals_dir.glob("CLOUD_*.md")) + [signals_dir / "SYNC_STATUS.md"]
    signal_files = [f for f in signal_files if f.exists()]

    if not signal_files:
        logger.info("No cloud signal files found.")
        return 0

    # Parse all signals
    signals = [_parse_signal(f) for f in signal_files]
    signals = [s for s in signals if s]

    logger.info(f"Found {len(signals)} signal(s) to merge.")

    # Build the section
    section = _format_signal_section(signals)

    # Update Dashboard.md
    if dashboard_path.exists():
        current = dashboard_path.read_text()

        # Remove old Cloud Agent Status section
        updated = re.sub(
            r"\n## ☁️ Cloud Agent Status\n[\s\S]*?(?=\n## |\Z)",
            "",
            current,
        )
        updated = updated.rstrip() + "\n" + section
    else:
        logger.warning("Dashboard.md not found — creating minimal version.")
        updated = f"# AI Employee Dashboard\n\n_Created by merge_signals.py_\n{section}"

    if not DRY_RUN:
        dashboard_path.write_text(updated)
        logger.info("Dashboard.md updated with cloud agent status.")
    else:
        logger.info("[DRY RUN] Would update Dashboard.md")
        print(section)

    # Archive processed status signals to Done/ (keep SYNC_STATUS.md in place — it's rolling)
    done_dir = vault_path / "Done"
    done_dir.mkdir(exist_ok=True)
    archived = 0
    for sf in signal_files:
        if sf.name == "SYNC_STATUS.md":
            continue  # Rolling file — keep in place
        if not DRY_RUN:
            dest = done_dir / f"SIGNAL_{sf.name}"
            if dest.exists():
                ts = datetime.now().strftime("%H%M%S")
                dest = done_dir / f"SIGNAL_{sf.stem}_{ts}{sf.suffix}"
            shutil.move(str(sf), str(dest))
            archived += 1

    if archived:
        logger.info(f"Archived {archived} signal file(s) to Done/")

    # Log the merge
    try:
        logs_dir = vault_path / "Logs"
        logs_dir.mkdir(exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = logs_dir / f"{today}.json"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": "signals_merged",
            "actor": "MergeSignals",
            "signals_count": len(signals),
            "archived": archived,
        }
        entries = json.loads(log_file.read_text()) if log_file.exists() else []
        entries.append(entry)
        if not DRY_RUN:
            log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Log write failed: {e}")

    return len(signals)


def main():
    global VAULT_PATH, DRY_RUN  # noqa: allow CLI override of module globals
    parser = argparse.ArgumentParser(
        description="Personal AI Employee — Merge Cloud Signals (Platinum Tier)"
    )
    parser.add_argument("--vault", default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN)
    args = parser.parse_args()

    VAULT_PATH = Path(args.vault).resolve()
    DRY_RUN = args.dry_run
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    count = merge_signals(VAULT_PATH)
    logger.info(f"Merge complete — {count} signal(s) processed.")


if __name__ == "__main__":
    main()
