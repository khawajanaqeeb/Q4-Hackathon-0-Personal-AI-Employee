"""
email_server.py - Email MCP Server for Personal AI Employee

A Model Context Protocol (MCP) server that exposes email capabilities
to Claude Code. Implements the MCP spec (JSON-RPC 2.0 over stdio).

Tools exposed:
  - send_email    Send an email via SMTP (requires prior approval)
  - draft_email   Save a draft to /Pending_Approval/ (no approval needed)
  - list_drafts   List pending email drafts in /Pending_Approval/

Configuration via environment variables (.env):
  SMTP_HOST         SMTP server hostname (e.g., smtp.gmail.com)
  SMTP_PORT         SMTP port (default: 587)
  SMTP_USER         Your email address
  SMTP_PASSWORD     App-specific password (not your main password!)
  SMTP_FROM_NAME    Display name for sent emails
  VAULT_PATH        Path to the AI Employee vault
  DRY_RUN=true      Log only, no real emails sent

Gmail SMTP Setup:
  1. Enable 2FA on your Google account
  2. Go to Google Account → Security → App Passwords
  3. Generate a password for "Mail" + "Windows Computer"
  4. Use that password as SMTP_PASSWORD

Usage (as MCP server — stdio transport):
  python mcp_servers/email_server.py

Usage (standalone for testing):
  python mcp_servers/email_server.py --test
  python mcp_servers/email_server.py --send-approved AI_Employee_Vault/Approved/EMAIL_draft.md
"""

import os
import sys
import json
import logging
import smtplib
import argparse
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# Load .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EmailMCP] %(levelname)s: %(message)s",
    stream=sys.stderr,  # MCP servers must write logs to stderr, not stdout
)
logger = logging.getLogger("EmailMCPServer")

# ─── Config from environment ──────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM_NAME", "AI Employee")
VAULT_PATH    = Path(os.getenv("VAULT_PATH", "AI_Employee_Vault")).resolve()
DRY_RUN       = os.getenv("DRY_RUN", "false").lower() == "true"


# ─── Email utilities ──────────────────────────────────────────────────────────

def _send_smtp(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    """
    Send an email via SMTP with TLS.
    Returns {"success": bool, "message": str}.
    """
    if DRY_RUN:
        logger.info(f"[DRY RUN] Would send email to {to}: {subject}")
        return {"success": True, "message": f"[DRY RUN] Email to {to} logged (not sent)."}

    if not SMTP_USER or not SMTP_PASSWORD:
        return {
            "success": False,
            "message": "SMTP credentials not configured. Set SMTP_USER and SMTP_PASSWORD in .env",
        }

    try:
        msg = MIMEMultipart()
        msg["From"]    = f"{SMTP_FROM} <{SMTP_USER}>"
        msg["To"]      = to
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        if attachment_path:
            att_path = Path(attachment_path)
            if att_path.exists():
                with open(att_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={att_path.name}",
                    )
                    msg.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [to], msg.as_string())

        logger.info(f"Email sent successfully to {to}: {subject}")
        _log_to_vault("email_sent", {"to": to, "subject": subject, "result": "success"})
        return {"success": True, "message": f"Email sent to {to}."}

    except smtplib.SMTPAuthenticationError:
        return {"success": False, "message": "SMTP authentication failed. Check SMTP_USER and SMTP_PASSWORD."}
    except smtplib.SMTPException as e:
        return {"success": False, "message": f"SMTP error: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}


def _save_draft(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
    """
    Save an email draft to /Pending_Approval/ without sending.
    Returns {"success": bool, "file": str}.
    """
    pending_dir = VAULT_PATH / "Pending_Approval"
    pending_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_subject = "".join(c if c.isalnum() else "_" for c in subject)[:30]
    filename = f"EMAIL_{safe_subject}_{timestamp}.md"
    draft_file = pending_dir / filename

    content = f"""---
type: email_draft
action: send_email
to: {to}
subject: {subject}
attachment: {attachment_path or "none"}
created: {datetime.now().isoformat()}
status: pending_approval
expires: {datetime.now().replace(hour=23, minute=59).isoformat()}
---

## Email Draft — Awaiting Approval

**To:** {to}
**Subject:** {subject}

### Body

{body}

{"### Attachment" + chr(10) + f"`{attachment_path}`" if attachment_path else ""}

---

## How to Approve

Move this file to `/Approved/` folder to send the email.
Move to `/Rejected/` to discard.

The orchestrator will detect the approval and send via Email MCP server.

---
*Drafted by: Email MCP Server · Silver Tier*
"""
    draft_file.write_text(content)
    logger.info(f"Draft saved: {filename}")
    _log_to_vault("email_drafted", {"to": to, "subject": subject, "file": filename})
    return {"success": True, "file": str(draft_file), "filename": filename}


def _list_drafts() -> list:
    """List pending email drafts in /Pending_Approval/."""
    pending_dir = VAULT_PATH / "Pending_Approval"
    if not pending_dir.exists():
        return []
    drafts = []
    for f in pending_dir.glob("EMAIL_*.md"):
        try:
            raw = f.read_text()
            # Quick frontmatter parse
            lines = raw.split("\n")
            to_line = next((l for l in lines if l.startswith("to:")), "")
            subj_line = next((l for l in lines if l.startswith("subject:")), "")
            drafts.append({
                "file": f.name,
                "to": to_line.replace("to:", "").strip(),
                "subject": subj_line.replace("subject:", "").strip(),
                "path": str(f),
            })
        except Exception:
            pass
    return drafts


def _log_to_vault(event_type: str, details: dict):
    """Append a log entry to the vault's daily log file."""
    try:
        logs_dir = VAULT_PATH / "Logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = logs_dir / f"{today}.json"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "actor": "EmailMCPServer",
            **details,
        }

        entries = []
        if log_file.exists():
            try:
                entries = json.loads(log_file.read_text())
            except Exception:
                entries = []
        entries.append(entry)
        log_file.write_text(json.dumps(entries, indent=2))
    except Exception as e:
        logger.warning(f"Could not write to vault log: {e}")


# ─── MCP Protocol Implementation (JSON-RPC 2.0 over stdio) ───────────────────

SERVER_INFO = {
    "name": "email-server",
    "version": "1.0.0",
}

CAPABILITIES = {
    "tools": {},
}

TOOLS = [
    {
        "name": "send_email",
        "description": (
            "Send an email via SMTP. IMPORTANT: Only call this tool after the user "
            "has explicitly approved the action (file moved to /Approved/). "
            "For new drafts, use draft_email instead."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text (plain text or Markdown)",
                },
                "attachment_path": {
                    "type": "string",
                    "description": "Optional: absolute path to a file to attach",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "draft_email",
        "description": (
            "Save an email as a draft in /Pending_Approval/ without sending it. "
            "Always use this for new emails — the human will approve before sending."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient email address",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject line",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text",
                },
                "attachment_path": {
                    "type": "string",
                    "description": "Optional: path to a file to attach when sent",
                },
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "list_drafts",
        "description": "List pending email drafts waiting for approval in /Pending_Approval/",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def handle_request(request: dict) -> dict:
    """Dispatch a JSON-RPC 2.0 request to the appropriate handler."""
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    def success(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def error(code: int, message: str):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return success({
            "protocolVersion": "2024-11-05",
            "capabilities": CAPABILITIES,
            "serverInfo": SERVER_INFO,
        })

    elif method == "notifications/initialized":
        # Client notification — no response needed (but we handle it gracefully)
        return None

    elif method == "tools/list":
        return success({"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})

        if tool_name == "send_email":
            result = _send_smtp(
                to=args.get("to", ""),
                subject=args.get("subject", ""),
                body=args.get("body", ""),
                attachment_path=args.get("attachment_path"),
            )
            text = result["message"]
            return success({
                "content": [{"type": "text", "text": text}],
                "isError": not result["success"],
            })

        elif tool_name == "draft_email":
            result = _save_draft(
                to=args.get("to", ""),
                subject=args.get("subject", ""),
                body=args.get("body", ""),
                attachment_path=args.get("attachment_path"),
            )
            text = (
                f"Draft saved: {result.get('filename', 'unknown')}\n"
                f"Location: {result.get('file', '')}\n"
                "Move to /Approved/ to send, or /Rejected/ to discard."
            )
            return success({
                "content": [{"type": "text", "text": text}],
                "isError": not result["success"],
            })

        elif tool_name == "list_drafts":
            drafts = _list_drafts()
            if not drafts:
                text = "No pending email drafts found in /Pending_Approval/."
            else:
                lines = [f"Found {len(drafts)} pending email draft(s):\n"]
                for d in drafts:
                    lines.append(f"- {d['file']} → To: {d['to']} | Subject: {d['subject']}")
                text = "\n".join(lines)
            return success({
                "content": [{"type": "text", "text": text}],
            })

        else:
            return error(-32601, f"Unknown tool: {tool_name}")

    elif method == "ping":
        return success({})

    else:
        return error(-32601, f"Method not found: {method}")


def run_server():
    """
    Run the MCP server — reads JSON-RPC requests from stdin,
    writes responses to stdout. Logs go to stderr.
    """
    logger.info(f"Email MCP Server starting (vault: {VAULT_PATH}, dry_run: {DRY_RUN})")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        try:
            request = json.loads(raw_line)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            print(json.dumps(response), flush=True)
            continue

        try:
            response = handle_request(request)
        except Exception as e:
            logger.error(f"Handler error for {request.get('method')}: {e}", exc_info=True)
            response = {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            }

        # Some messages are notifications (no id) — don't send a response
        if response is not None:
            print(json.dumps(response), flush=True)


# ─── Standalone helpers (for testing & orchestrator use) ─────────────────────

def send_approved_email(approved_file: Path) -> bool:
    """
    Parse an approved email file and send it.
    Called by the orchestrator when a file lands in /Approved/.
    """
    import re

    if not approved_file.exists():
        logger.error(f"Approved file not found: {approved_file}")
        return False

    raw = approved_file.read_text()

    # Parse frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", raw, re.DOTALL)
    if not fm_match:
        logger.error(f"No frontmatter found in: {approved_file.name}")
        return False

    fm_text = fm_match.group(1)

    def get_field(field: str, default: str = "") -> str:
        m = re.search(rf"^{field}:\s*(.+)$", fm_text, re.MULTILINE)
        return m.group(1).strip() if m else default

    action_type = get_field("type")
    if action_type not in ("email_draft", "email"):
        logger.warning(f"Not an email file: {action_type}")
        return False

    to = get_field("to")
    subject = get_field("subject")
    attachment = get_field("attachment")
    attachment = None if attachment in ("none", "") else attachment

    # Extract body (everything after the frontmatter and headings)
    body_match = re.search(r"### Body\n+(.*?)(\n---|\Z)", raw, re.DOTALL)
    body = body_match.group(1).strip() if body_match else ""

    if not to or not subject:
        logger.error(f"Missing to/subject in: {approved_file.name}")
        return False

    result = _send_smtp(to=to, subject=subject, body=body, attachment_path=attachment)

    if result["success"]:
        # Move to Done/
        done_dir = VAULT_PATH / "Done"
        done_dir.mkdir(exist_ok=True)
        dest = done_dir / approved_file.name
        approved_file.rename(dest)
        logger.info(f"Email sent. Moved to Done/: {dest.name}")

    return result["success"]


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Email MCP Server (Silver Tier)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)           Run as MCP server (stdin/stdout JSON-RPC 2.0)
  --test              Run SMTP connectivity test
  --send-approved     Send an approved email file and move to Done/
  --list-drafts       List pending email drafts

Examples:
  # Start as MCP server (used by Claude Code)
  python mcp_servers/email_server.py

  # Test SMTP connection
  python mcp_servers/email_server.py --test

  # Send a specific approved email
  python mcp_servers/email_server.py --send-approved AI_Employee_Vault/Approved/EMAIL_draft.md

  # Dry-run (no real emails)
  DRY_RUN=true python mcp_servers/email_server.py --test
        """,
    )
    parser.add_argument("--test", action="store_true", help="Test SMTP connection")
    parser.add_argument("--send-approved", metavar="FILE", help="Send an approved email file")
    parser.add_argument("--list-drafts", action="store_true", help="List pending email drafts")
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN)
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    if args.test:
        print(f"SMTP Config: {SMTP_HOST}:{SMTP_PORT} as {SMTP_USER}")
        if DRY_RUN:
            print("[DRY RUN] Would connect to SMTP (skipped)")
            return
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
                s.ehlo()
                s.starttls()
                s.login(SMTP_USER, SMTP_PASSWORD)
                print("✓ SMTP connection successful!")
        except Exception as e:
            print(f"✗ SMTP connection failed: {e}")

    elif args.send_approved:
        success = send_approved_email(Path(args.send_approved))
        sys.exit(0 if success else 1)

    elif args.list_drafts:
        drafts = _list_drafts()
        if not drafts:
            print("No pending email drafts found.")
        else:
            print(f"Found {len(drafts)} draft(s):")
            for d in drafts:
                print(f"  - {d['file']} → {d['to']} | {d['subject']}")

    else:
        run_server()


if __name__ == "__main__":
    main()
