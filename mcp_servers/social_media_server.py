#!/usr/bin/env python3
"""social_media_server.py - Social Media MCP Server for Personal AI Employee (Gold Tier).

JSON-RPC 2.0 MCP server over stdio.
Provides tools for posting to Twitter/X, Facebook, and Instagram,
and generating social media summaries.

Tools exposed:
  - post_to_twitter    — post a tweet
  - post_to_facebook   — post to Facebook page/profile
  - post_to_instagram  — post to Instagram (via API note)
  - get_social_summary — summary of recent social activity from vault logs

Usage (standalone test):
    python3 mcp_servers/social_media_server.py --test

MCP config (.mcp.json):
    {
      "social_media": {
        "command": "python3",
        "args": ["mcp_servers/social_media_server.py"]
      }
    }
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "watchers"))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [SocialMCP] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("SocialMediaMCP")

VAULT_PATH = Path(os.getenv("VAULT_PATH", str(ROOT / "AI_Employee_Vault")))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

TWITTER_SESSION = os.getenv("TWITTER_SESSION_PATH", str(ROOT / ".twitter_session"))
FACEBOOK_SESSION = os.getenv("FACEBOOK_SESSION_PATH", str(ROOT / ".facebook_session"))
INSTAGRAM_SESSION = os.getenv("INSTAGRAM_SESSION_PATH", str(ROOT / ".instagram_session"))

# ── MCP Tool Definitions ──────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "post_to_twitter",
        "description": (
            "Post a tweet to Twitter/X. Requires an active Twitter session. "
            "The tweet must be ≤280 characters. Returns success status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Tweet text (max 280 chars)",
                    "maxLength": 280,
                }
            },
            "required": ["text"],
        },
    },
    {
        "name": "post_to_facebook",
        "description": (
            "Post a message to Facebook profile or page. "
            "Optionally target a specific page URL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Post text",
                },
                "page_url": {
                    "type": "string",
                    "description": "Optional: Facebook page URL to post on",
                    "default": "",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "post_to_instagram",
        "description": (
            "Prepare an Instagram post. Note: Instagram web posting requires "
            "the Instagram Graph API for business accounts. This tool prepares "
            "the content and logs it for manual posting or API submission."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "caption": {
                    "type": "string",
                    "description": "Post caption with hashtags",
                },
                "image_path": {
                    "type": "string",
                    "description": "Optional: path to image file",
                    "default": "",
                },
            },
            "required": ["caption"],
        },
    },
    {
        "name": "get_social_summary",
        "description": (
            "Generate a summary of recent social media activity from vault logs. "
            "Shows posts created, mentions detected, and engagement items processed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to summarize (default: 7)",
                    "default": 7,
                }
            },
        },
    },
    {
        "name": "create_social_post_approval",
        "description": (
            "Create a HITL approval file for a social media post. "
            "Use this instead of posting directly when approval is needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "description": "Platform: twitter, facebook, or instagram",
                    "enum": ["twitter", "facebook", "instagram"],
                },
                "content": {
                    "type": "string",
                    "description": "Post content",
                },
                "reason": {
                    "type": "string",
                    "description": "Why this post is being created",
                },
            },
            "required": ["platform", "content", "reason"],
        },
    },
]


def _log_action(action_type: str, details: dict):
    """Append action to today's vault log."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = VAULT_PATH / "Logs" / f"{today}.json"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": action_type,
        "actor": "SocialMediaMCP",
        "approval_status": "dry_run" if DRY_RUN else "auto_approved",
        **details,
    }
    entries = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text())
        except Exception:
            pass
    entries.append(entry)
    log_file.write_text(json.dumps(entries, indent=2))


# ── Tool Handlers ─────────────────────────────────────────────────────────────

def handle_post_to_twitter(args: dict) -> dict:
    text = args.get("text", "").strip()
    if not text:
        return {"error": "text is required"}
    if len(text) > 280:
        return {"error": f"Tweet too long: {len(text)} chars (max 280)"}

    try:
        from twitter_watcher import TwitterWatcher
        result = TwitterWatcher.post_tweet(TWITTER_SESSION, text, dry_run=DRY_RUN)
    except ImportError:
        result = {"success": DRY_RUN, "dry_run": DRY_RUN, "text": text,
                  "note": "TwitterWatcher not available — session not configured"}

    _log_action("social_post_twitter", {"text": text[:100], "result": result.get("success", False)})
    return result


def handle_post_to_facebook(args: dict) -> dict:
    text = args.get("text", "").strip()
    page_url = args.get("page_url", "")
    if not text:
        return {"error": "text is required"}

    try:
        from facebook_watcher import FacebookWatcher
        result = FacebookWatcher.post_to_page(FACEBOOK_SESSION, text, page_url, dry_run=DRY_RUN)
    except ImportError:
        result = {"success": DRY_RUN, "dry_run": DRY_RUN, "text": text,
                  "note": "FacebookWatcher not available — session not configured"}

    _log_action("social_post_facebook", {"text": text[:100], "result": result.get("success", False)})
    return result


def handle_post_to_instagram(args: dict) -> dict:
    caption = args.get("caption", "").strip()
    image_path = args.get("image_path", "")
    if not caption:
        return {"error": "caption is required"}

    # Save draft to vault for manual posting
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_file = VAULT_PATH / "Pending_Approval" / f"INSTAGRAM_POST_{timestamp}.md"
    content = f"""---
type: instagram_post_draft
platform: instagram
created: {datetime.now().isoformat()}
status: pending
---

## Instagram Post Draft

**Caption:**
{caption}

**Image:** {image_path or "(no image specified)"}

## To Post
- Use Instagram mobile app to post manually, OR
- Use Instagram Graph API (business accounts) for automated posting
- See: https://developers.facebook.com/docs/instagram-api

## To Approve (for API posting)
Move this file to /Approved/
"""
    draft_file.write_text(content)
    _log_action("social_post_instagram_draft", {"caption": caption[:100], "draft_file": draft_file.name})
    return {
        "success": True,
        "note": "Instagram post draft created in /Pending_Approval/. Post manually or via Instagram Graph API.",
        "draft_file": str(draft_file),
        "caption": caption,
    }


def handle_get_social_summary(args: dict) -> dict:
    days = args.get("days", 7)
    logs_dir = VAULT_PATH / "Logs"
    if not logs_dir.exists():
        return {"summary": "No logs found.", "days": days, "total_social_events": 0}

    from datetime import timedelta
    cutoff = datetime.now() - timedelta(days=days)

    social_events = []
    log_files = sorted(logs_dir.glob("*.json"), reverse=True)[:days + 1]

    for log_file in log_files:
        try:
            entries = json.loads(log_file.read_text())
            for entry in entries:
                event_type = entry.get("event_type", "")
                if any(kw in event_type for kw in ["twitter", "facebook", "instagram", "social"]):
                    social_events.append(entry)
        except Exception:
            continue

    # Count by platform
    counts = {"twitter": 0, "facebook": 0, "instagram": 0, "other": 0}
    for event in social_events:
        et = event.get("event_type", "")
        for platform in ("twitter", "facebook", "instagram"):
            if platform in et:
                counts[platform] += 1
                break
        else:
            counts["other"] += 1

    return {
        "days": days,
        "total_social_events": len(social_events),
        "by_platform": counts,
        "recent_events": social_events[-10:],
        "summary": (
            f"Last {days} days: {len(social_events)} social events. "
            f"Twitter: {counts['twitter']}, Facebook: {counts['facebook']}, "
            f"Instagram: {counts['instagram']}."
        ),
    }


def handle_create_social_post_approval(args: dict) -> dict:
    platform = args.get("platform", "")
    content = args.get("content", "").strip()
    reason = args.get("reason", "")

    if not platform or not content:
        return {"error": "platform and content are required"}

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"SOCIAL_{platform.upper()}_{timestamp}.md"
    approval_file = VAULT_PATH / "Pending_Approval" / filename

    expires = datetime.now().replace(hour=23, minute=59).isoformat()

    approval_content = f"""---
type: social_post_approval
platform: {platform}
created: {datetime.now().isoformat()}
expires: {expires}
status: pending
---

## Social Media Post — Approval Required

**Platform:** {platform.title()}
**Reason:** {reason}

**Content:**
{content}

## To Approve
Move this file to `/Approved/` — the orchestrator will execute the post.

## To Reject
Move this file to `/Rejected/`
"""
    approval_file.write_text(approval_content)
    _log_action("social_post_approval_created", {
        "platform": platform,
        "content": content[:100],
        "file": filename,
    })
    return {
        "success": True,
        "approval_file": str(approval_file),
        "message": f"Approval request created: {filename}. Move to /Approved/ to post.",
    }


# ── JSON-RPC 2.0 Server ───────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "post_to_twitter": handle_post_to_twitter,
    "post_to_facebook": handle_post_to_facebook,
    "post_to_instagram": handle_post_to_instagram,
    "get_social_summary": handle_get_social_summary,
    "create_social_post_approval": handle_create_social_post_approval,
}


def handle_request(request: dict) -> dict:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message, data=None):
        e = {"code": code, "message": message}
        if data:
            e["data"] = data
        return {"jsonrpc": "2.0", "id": req_id, "error": e}

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "social-media-mcp", "version": "1.0.0"},
        })

    if method == "tools/list":
        return ok({"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})

        if tool_name not in TOOL_HANDLERS:
            return err(-32601, f"Tool not found: {tool_name}")

        try:
            result = TOOL_HANDLERS[tool_name](tool_args)
            return ok({
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": "error" in result,
            })
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return err(-32603, f"Tool execution error: {e}")

    if method == "notifications/initialized":
        return None  # no response for notifications

    return err(-32601, f"Method not found: {method}")


def run_server():
    """Run MCP server over stdio (JSON-RPC 2.0)."""
    logger.info("Social Media MCP Server starting (stdio transport)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            print(json.dumps(response), flush=True)
            continue

        response = handle_request(request)
        if response is not None:
            print(json.dumps(response), flush=True)


def run_test():
    """Quick connectivity test."""
    print("Social Media MCP Server — Test Mode")
    print(f"Vault: {VAULT_PATH}")
    print(f"DRY_RUN: {DRY_RUN}")
    print(f"Twitter session: {TWITTER_SESSION}")
    print(f"Facebook session: {FACEBOOK_SESSION}")
    print(f"Instagram session: {INSTAGRAM_SESSION}")
    print("\nAvailable tools:")
    for tool in TOOLS:
        print(f"  - {tool['name']}: {tool['description'][:60]}...")

    # Test get_social_summary
    summary = handle_get_social_summary({"days": 7})
    print(f"\nSocial summary (last 7 days): {summary['summary']}")
    print("\n✅ Social Media MCP Server ready.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run_server()
