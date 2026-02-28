#!/usr/bin/env python3
"""ralph_wiggum_hook.py - Claude Code Stop Hook for autonomous multi-step task completion.

Gold Tier: The "Ralph Wiggum" persistence pattern.

How it works:
  1. Claude works on a task.
  2. Claude tries to stop (exit).
  3. This Stop hook runs.
  4. If Needs_Action/ still has unprocessed items → block exit, re-inject prompt.
  5. If Needs_Action/ is empty OR max iterations reached → allow exit.

Claude Code Stop hook protocol:
  - Exit 0 → allow Claude to stop
  - Exit 2 + output to stdout → block stop, feed output back as next prompt

Reference: https://github.com/anthropics/claude-code/tree/main/.claude/plugins/ralph-wiggum

Configuration in .claude/settings.json:
  {
    "hooks": {
      "Stop": [{"hooks": [{"type": "command", "command": "python3 scripts/ralph_wiggum_hook.py"}]}]
    }
  }

State file: /tmp/ralph_wiggum_state.json
  {
    "task_prompt": "Process all files in /Needs_Action",
    "completion_promise": "TASK_COMPLETE",
    "iteration": 0,
    "max_iterations": 10,
    "vault_path": "/path/to/AI_Employee_Vault",
    "active": true
  }
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

STATE_FILE = Path("/tmp/ralph_wiggum_state.json")
ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

DEFAULT_STATE = {
    "task_prompt": (
        "Check /Needs_Action folder. If there are unprocessed items, "
        "read Company_Handbook.md first, then process each item: create a plan in /Plans/, "
        "execute or create approval in /Pending_Approval/, log to /Logs/, "
        "update Dashboard.md, and move the source file to /Done/. "
        "When ALL items are processed, output: <promise>TASK_COMPLETE</promise>"
    ),
    "completion_promise": "TASK_COMPLETE",
    "iteration": 0,
    "max_iterations": 10,
    "vault_path": str(VAULT_DEFAULT),
    "active": True,
}


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    # No state file = Ralph Wiggum not activated. Exit silently.
    return {"active": False}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def has_unprocessed_items(vault_path: str) -> bool:
    """Check if Needs_Action folder has .md files to process."""
    needs_action = Path(vault_path) / "Needs_Action"
    if not needs_action.exists():
        return False
    items = [f for f in needs_action.iterdir() if f.suffix == ".md" and not f.name.startswith(".")]
    return len(items) > 0


def check_completion_promise(transcript_path: str | None) -> bool:
    """Check if Claude output the completion promise in the last session."""
    if not transcript_path:
        return False
    # Claude Code sets CLAUDE_TRANSCRIPT_PATH env var on some versions
    try:
        transcript = Path(transcript_path).read_text()
        return "TASK_COMPLETE" in transcript
    except (OSError, TypeError):
        return False


def main():
    state = load_state()

    # If Ralph Wiggum is not active, allow exit
    if not state.get("active", False):
        sys.exit(0)

    vault_path = state.get("vault_path", str(VAULT_DEFAULT))
    max_iterations = state.get("max_iterations", 10)
    current_iteration = state.get("iteration", 0)

    # Check max iterations guard
    if current_iteration >= max_iterations:
        print(
            f"[Ralph Wiggum] Max iterations ({max_iterations}) reached. "
            "Allowing exit. Please review unprocessed items manually.",
            file=sys.stderr,
        )
        state["active"] = False
        save_state(state)
        sys.exit(0)

    # Check if completion promise was given
    transcript_path = os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    if check_completion_promise(transcript_path):
        print("[Ralph Wiggum] Completion promise detected. Task complete.", file=sys.stderr)
        state["active"] = False
        save_state(state)
        sys.exit(0)

    # Check if Needs_Action still has items
    if not has_unprocessed_items(vault_path):
        print("[Ralph Wiggum] Needs_Action is empty. Task complete.", file=sys.stderr)
        state["active"] = False
        save_state(state)
        sys.exit(0)

    # Still work to do — block exit and re-inject prompt
    state["iteration"] = current_iteration + 1
    save_state(state)

    prompt = state.get("task_prompt", DEFAULT_STATE["task_prompt"])
    iteration_info = f"[Ralph Wiggum Loop — iteration {state['iteration']}/{max_iterations}]"
    needs_action = Path(vault_path) / "Needs_Action"
    remaining = [f.name for f in needs_action.iterdir() if f.suffix == ".md" and not f.name.startswith(".")]

    output = (
        f"{iteration_info}\n\n"
        f"There are still {len(remaining)} unprocessed item(s) in /Needs_Action:\n"
        + "\n".join(f"  - {name}" for name in remaining[:10])
        + f"\n\n{prompt}"
    )

    # Exit code 2 = block stop + feed output back to Claude
    print(output)
    sys.exit(2)


if __name__ == "__main__":
    main()
