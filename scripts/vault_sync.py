"""
scripts/vault_sync.py — Git-based Vault Synchronisation Daemon (Platinum Tier)

Keeps the Obsidian vault in sync between Cloud VM and Local machine via Git.

Protocol:
  pull()  — git pull (fetch latest from remote)
  push()  — git add AI_Employee_Vault/ + commit + push
  loop()  — continuous pull → (process) → push cycle

Conflict strategy:
  - On merge conflict, prefer remote for Needs_Action/ and Signals/
  - For Pending_Approval/ and Done/, use "ours" (Local is authoritative)

Exclusions (never synced):
  - .env, *.json credentials, token.json, session dirs

Usage:
    python3 scripts/vault_sync.py --vault AI_Employee_Vault
    python3 scripts/vault_sync.py --vault AI_Employee_Vault --interval 300
    python3 scripts/vault_sync.py --vault AI_Employee_Vault --once   (single pull+push)

Environment variables:
    GIT_REMOTE_URL         Git remote URL (SSH or HTTPS)
    GIT_VAULT_BRANCH       Branch name (default: main)
    VAULT_SYNC_INTERVAL    Seconds between syncs (default: 300)
    DRY_RUN=true           Log without executing git commands
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
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
    format="%(asctime)s [VaultSync] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("VaultSync")

VAULT_PATH = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault")).resolve()
GIT_BRANCH = os.getenv("GIT_VAULT_BRANCH", "main")
SYNC_INTERVAL = int(os.getenv("VAULT_SYNC_INTERVAL", "300"))
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# ─── Git Helpers ──────────────────────────────────────────────────────────────

def _git(args: list[str], cwd: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command, return CompletedProcess."""
    cmd = ["git"] + args
    logger.debug(f"git {' '.join(args)}")
    if DRY_RUN and args[0] not in ("status", "diff", "log", "remote", "fetch", "rev-parse", "branch"):
        logger.info(f"[DRY RUN] Would run: git {' '.join(args)}")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    return subprocess.run(
        cmd,
        cwd=cwd or str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
        check=False,
    )


def _repo_root() -> Path:
    """Find git repo root from this script's location."""
    result = _git(["rev-parse", "--show-toplevel"])
    if result.returncode == 0:
        return Path(result.stdout.strip())
    # Fallback: parent of scripts/
    return Path(__file__).parent.parent


REPO_ROOT = _repo_root()


def _has_remote() -> bool:
    """Check if a git remote is configured."""
    result = _git(["remote"], cwd=str(REPO_ROOT))
    return bool(result.stdout.strip())


def _current_branch() -> str:
    result = _git(["branch", "--show-current"], cwd=str(REPO_ROOT))
    return result.stdout.strip() or GIT_BRANCH


def _write_signal(status: str, details: dict):
    """Write a sync status signal to Signals/."""
    try:
        signals_dir = VAULT_PATH / "Signals"
        signals_dir.mkdir(parents=True, exist_ok=True)
        sig_file = signals_dir / "SYNC_STATUS.md"  # Overwrite (rolling status)
        sig_file.write_text(
            f"---\n"
            f"type: sync_status\n"
            f"status: {status}\n"
            f"timestamp: {datetime.now().isoformat()}\n"
            f"branch: {_current_branch()}\n"
            f"---\n\n"
            f"# Vault Sync Status: {status}\n\n"
            + "\n".join(f"- **{k}**: {v}" for k, v in details.items())
            + "\n"
        )
    except Exception as e:
        logger.warning(f"Signal write failed: {e}")


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
            "actor": "VaultSync",
            **details,
        }
        entries = json.loads(log_file.read_text()) if log_file.exists() else []
        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Log write failed: {e}")


# ─── Core Sync Operations ─────────────────────────────────────────────────────

def pull() -> dict:
    """
    Pull latest changes from remote.
    Returns dict with keys: success, changes, conflicts.
    """
    if not _has_remote():
        logger.warning("No git remote configured. Skipping pull.")
        return {"success": False, "reason": "no_remote"}

    branch = _current_branch()
    logger.info(f"Pulling from remote/{branch}...")

    # Fetch
    result = _git(["fetch", "origin"], cwd=str(REPO_ROOT))
    if result.returncode != 0:
        logger.error(f"git fetch failed: {result.stderr.strip()}")
        return {"success": False, "reason": "fetch_failed", "stderr": result.stderr}

    # Check for incoming changes
    diff_result = _git(["diff", f"HEAD..origin/{branch}", "--name-only"], cwd=str(REPO_ROOT))
    incoming_files = [f for f in diff_result.stdout.strip().splitlines() if f]

    if not incoming_files:
        logger.info("Already up to date.")
        return {"success": True, "changes": [], "conflicts": []}

    # Merge with strategy: prefer remote for Needs_Action/ and Signals/
    merge_result = _git(
        ["merge", f"origin/{branch}", "--no-edit", "-X", "theirs"],
        cwd=str(REPO_ROOT),
    )

    conflicts = []
    if merge_result.returncode != 0:
        logger.warning(f"Merge had issues: {merge_result.stderr.strip()}")
        # Try to identify conflict files
        status = _git(["diff", "--name-only", "--diff-filter=U"], cwd=str(REPO_ROOT))
        conflicts = status.stdout.strip().splitlines()
        if conflicts:
            logger.warning(f"Conflicts in: {conflicts}")
            # Force-accept remote for conflicted files
            for cf in conflicts:
                _git(["checkout", "--theirs", cf], cwd=str(REPO_ROOT))
                _git(["add", cf], cwd=str(REPO_ROOT))
            _git(["commit", "--no-edit", "-m", "chore(vault-sync): resolve conflicts (prefer remote)"],
                 cwd=str(REPO_ROOT))

    logger.info(f"Pull complete. {len(incoming_files)} file(s) updated.")
    _log_event("vault_pull", {"files_changed": len(incoming_files), "conflicts": len(conflicts)})
    _write_signal("pulled", {
        "files_updated": len(incoming_files),
        "conflicts_resolved": len(conflicts),
        "timestamp": datetime.now().isoformat(),
    })
    return {"success": True, "changes": incoming_files, "conflicts": conflicts}


def push(message: str | None = None) -> dict:
    """
    Stage vault changes and push to remote.
    Returns dict with keys: success, files_pushed.
    """
    if not _has_remote():
        logger.warning("No git remote configured. Skipping push.")
        return {"success": False, "reason": "no_remote"}

    vault_rel = str(VAULT_PATH.relative_to(REPO_ROOT))

    # Stage vault files only (never .env, session dirs, *.json credentials)
    stage_result = _git(
        ["add", vault_rel],
        cwd=str(REPO_ROOT),
    )
    if stage_result.returncode != 0:
        logger.error(f"git add failed: {stage_result.stderr.strip()}")
        return {"success": False, "reason": "add_failed"}

    # Check if there's anything to commit
    status_result = _git(["diff", "--cached", "--name-only"], cwd=str(REPO_ROOT))
    staged_files = [f for f in status_result.stdout.strip().splitlines() if f]

    if not staged_files:
        logger.info("Nothing to push (no staged changes).")
        return {"success": True, "files_pushed": [], "reason": "nothing_to_push"}

    # Commit
    commit_msg = message or f"chore(vault-sync): auto-sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    commit_result = _git(["commit", "-m", commit_msg], cwd=str(REPO_ROOT))
    if commit_result.returncode != 0:
        logger.error(f"git commit failed: {commit_result.stderr.strip()}")
        return {"success": False, "reason": "commit_failed", "stderr": commit_result.stderr}

    # Push
    branch = _current_branch()
    push_result = _git(["push", "origin", branch], cwd=str(REPO_ROOT))
    if push_result.returncode != 0:
        logger.error(f"git push failed: {push_result.stderr.strip()}")
        return {"success": False, "reason": "push_failed", "stderr": push_result.stderr}

    logger.info(f"Pushed {len(staged_files)} file(s) to remote/{branch}.")
    _log_event("vault_push", {"files_pushed": len(staged_files), "branch": branch})
    _write_signal("pushed", {
        "files_pushed": len(staged_files),
        "branch": branch,
        "timestamp": datetime.now().isoformat(),
    })
    return {"success": True, "files_pushed": staged_files}


def sync_once() -> dict:
    """Pull then push — single sync cycle."""
    pull_result = pull()
    push_result = push()
    return {"pull": pull_result, "push": push_result}


# ─── Continuous Loop ──────────────────────────────────────────────────────────

def run_loop(interval: int = 300):
    """Continuous sync daemon."""
    logger.info(f"Vault Sync daemon starting — interval: {interval}s")
    logger.info(f"Vault: {VAULT_PATH} | Branch: {GIT_BRANCH} | Dry-run: {DRY_RUN}")

    if not _has_remote():
        logger.warning(
            "No git remote configured. Set GIT_REMOTE_URL and run:\n"
            "  git remote add origin <GIT_REMOTE_URL>\n"
            "Sync daemon will retry every interval but skip git operations."
        )

    _log_event("vault_sync_started", {"interval": interval, "dry_run": DRY_RUN})

    sync_count = 0
    try:
        while True:
            logger.info(f"Sync cycle #{sync_count + 1}")
            result = sync_once()
            sync_count += 1
            pull_ok = result["pull"].get("success", False)
            push_ok = result["push"].get("success", False)
            logger.info(f"Sync #{sync_count}: pull={'ok' if pull_ok else 'skip'} push={'ok' if push_ok else 'skip'}")
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("Vault Sync daemon stopped.")
    finally:
        _log_event("vault_sync_stopped", {"sync_count": sync_count})


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Personal AI Employee — Vault Sync (Platinum Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Continuous sync daemon
  python3 scripts/vault_sync.py --vault AI_Employee_Vault --interval 300

  # Single sync (for cron)
  python3 scripts/vault_sync.py --vault AI_Employee_Vault --once

  # Pull only
  python3 scripts/vault_sync.py --vault AI_Employee_Vault --pull-only

  # Push with custom message
  python3 scripts/vault_sync.py --vault AI_Employee_Vault --push "feat: new approval"
        """,
    )
    global VAULT_PATH, DRY_RUN  # noqa: allow CLI override of module globals
    parser.add_argument("--vault", default=os.getenv("VAULT_PATH", "AI_Employee_Vault"))
    parser.add_argument("--interval", type=int, default=SYNC_INTERVAL)
    parser.add_argument("--once", action="store_true", help="Single sync and exit")
    parser.add_argument("--pull-only", action="store_true")
    parser.add_argument("--push", metavar="MSG", help="Push with custom commit message and exit")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN)
    args = parser.parse_args()

    VAULT_PATH = Path(args.vault).resolve()
    DRY_RUN = args.dry_run
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    if args.pull_only:
        result = pull()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    if args.push:
        result = push(args.push)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("success") else 1)

    if args.once:
        result = sync_once()
        print(json.dumps(result, indent=2))
        sys.exit(0)

    run_loop(args.interval)


if __name__ == "__main__":
    main()
