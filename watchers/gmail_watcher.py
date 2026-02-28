"""
gmail_watcher.py - Gmail Watcher for Personal AI Employee

Monitors Gmail for unread important messages and creates action files
in /Needs_Action/ for Claude to process.

Requirements:
  pip install google-auth google-auth-oauthlib google-api-python-client

Setup:
  1. Enable Gmail API at console.cloud.google.com
  2. Create OAuth 2.0 credentials (Desktop app)
  3. Download credentials.json to this directory
  4. Run once interactively to authorize: python gmail_watcher.py --setup
  5. Then run normally: python gmail_watcher.py --vault ./AI_Employee_Vault

Environment variables:
  GMAIL_CREDENTIALS_PATH  Path to credentials.json (default: ./credentials.json)
  GMAIL_TOKEN_PATH        Path to token.json (default: ./token.json)
  DRY_RUN=true            Log actions without creating files
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent))
from base_watcher import BaseWatcher

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# gmail.send is needed for auto-reply.  Adding it requires re-running --setup
# once to re-authorize (delete watchers/token.json to force re-auth).
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Keywords that flag an email as needing human review / Claude processing.
# Emails whose snippet contains NONE of these get an auto-reply instead.
BUSINESS_KEYWORDS = [
    # Money & transactions
    "invoice", "payment", "quote", "quotation", "pricing", "price", "cost",
    "fee", "refund", "budget", "deposit", "contract", "proposal",
    # Work & hiring
    "hire", "hiring", "job", "freelance", "retainer", "project", "scope",
    "deliverable", "deadline", "milestone",
    # Business development
    "partnership", "collaboration", "opportunity", "consulting", "agency",
    "service", "meeting", "call", "discuss", "negotiate",
    # Urgency
    "urgent", "asap", "immediately", "emergency", "critical", "legal",
    "dispute", "complaint", "issue", "problem", "broken", "outage",
]

# Auto-reply text for low-priority emails.  Override via GMAIL_AUTO_REPLY in .env
GMAIL_AUTO_REPLY = os.getenv(
    "GMAIL_AUTO_REPLY",
    "Thank you for your email! I've received your message and will respond as soon as possible. "
    "If this is urgent or relates to a business matter, please mention it in your follow-up "
    "and I'll prioritise it accordingly.",
)


class GmailWatcher(BaseWatcher):
    """
    Monitors Gmail for unread important messages.

    Polls every 2 minutes (120 seconds) to stay within Gmail API quotas.
    Only processes messages flagged as 'important' by Gmail to reduce noise.
    """

    def __init__(self, vault_path: str, credentials_path: str, token_path: str):
        super().__init__(vault_path, check_interval=120)
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)
        self.processed_ids: set = self._load_processed_ids()
        self.service = None
        self._init_gmail()

    def _load_processed_ids(self) -> set:
        """Load previously processed message IDs to avoid duplicates."""
        state_file = self.vault_path / ".gmail_state.json"
        if state_file.exists():
            try:
                return set(json.loads(state_file.read_text()))
            except Exception:
                return set()
        return set()

    def _save_processed_ids(self):
        """Persist processed IDs to avoid reprocessing after restart."""
        state_file = self.vault_path / ".gmail_state.json"
        # Keep only last 1000 IDs to prevent unbounded growth
        ids_list = list(self.processed_ids)[-1000:]
        state_file.write_text(json.dumps(ids_list))

    def _init_gmail(self):
        """Authenticate with Gmail API."""
        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            creds = None
            if self.token_path.exists():
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not self.credentials_path.exists():
                        raise FileNotFoundError(
                            f"credentials.json not found at {self.credentials_path}. "
                            "Download from Google Cloud Console."
                        )
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), SCOPES
                    )
                    # WSL2: disable auto browser-open (gio/xdg-open unavailable).
                    # A local callback server starts on a random port — copy the
                    # printed URL into your Windows browser to complete auth.
                    # localhost ports are forwarded from Windows → WSL2 automatically.
                    print("\n" + "="*60)
                    print("ACTION REQUIRED: Open the URL below in your Windows browser.")
                    print("After authorising, the page will redirect to localhost")
                    print("and the token will be saved automatically.")
                    print("="*60 + "\n")
                    creds = flow.run_local_server(port=0, open_browser=False)
                self.token_path.write_text(creds.to_json())

            self.service = build("gmail", "v1", credentials=creds)
            self.logger.info("Gmail API authenticated successfully.")

        except ImportError:
            self.logger.error(
                "Gmail dependencies not installed. Run: pip install google-auth "
                "google-auth-oauthlib google-api-python-client"
            )
            raise

    def check_for_updates(self) -> list:
        """Fetch unread important messages not yet processed."""
        results = self.service.users().messages().list(
            userId="me",
            q="is:unread is:important",
            maxResults=10,
        ).execute()

        messages = results.get("messages", [])
        new_messages = [m for m in messages if m["id"] not in self.processed_ids]
        if new_messages:
            self.logger.info(f"Found {len(new_messages)} new important messages.")
        return new_messages

    def _send_auto_reply(self, message_id: str, thread_id: str, headers: dict) -> bool:
        """Send an auto-reply to a Gmail message using the Gmail API.

        Constructs a proper RFC 2822 reply with In-Reply-To / References headers
        so the reply appears in the same thread.
        """
        import base64
        from email.mime.text import MIMEText

        try:
            to_addr = headers.get("From", "")
            if not to_addr:
                return False

            subject = headers.get("Subject", "")
            reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
            msg_id_header = headers.get("Message-ID", message_id)

            reply = MIMEText(GMAIL_AUTO_REPLY)
            reply["To"] = to_addr
            reply["Subject"] = reply_subject
            reply["In-Reply-To"] = msg_id_header
            reply["References"] = msg_id_header

            raw = base64.urlsafe_b64encode(reply.as_bytes()).decode()
            self.service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id},
            ).execute()
            self.logger.info(f"Auto-replied to email from: {to_addr}")
            return True
        except Exception as e:
            self.logger.error(f"Gmail auto-reply failed: {e}")
            return False

    def create_action_file(self, message: dict) -> Path:
        """Create a .md action file from a Gmail message.

        Emails whose snippet contains business keywords go to Needs_Action/
        for Claude to process.  All other emails receive an auto-reply and
        are logged to Done/ without entering the review queue.
        """
        msg = self.service.users().messages().get(
            userId="me",
            id=message["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date", "To", "Message-ID"],
        ).execute()

        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        snippet = msg.get("snippet", "")
        labels = msg.get("labelIds", [])
        thread_id = msg.get("threadId", message["id"])

        # Determine priority from labels
        priority = "P1" if "IMPORTANT" in labels else "P2"
        if "CATEGORY_PERSONAL" in labels:
            priority = "P1"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"EMAIL_{timestamp}_{message['id'][:8]}.md"

        # ── Auto-reply path: no business keywords in snippet ───────────────
        snippet_lower = snippet.lower()
        has_keywords = any(kw in snippet_lower for kw in BUSINESS_KEYWORDS)

        if not has_keywords:
            done_dir = self.vault_path / "Done"
            done_dir.mkdir(exist_ok=True)
            done_file = done_dir / filename

            if DRY_RUN:
                self.logger.info(
                    f"[DRY RUN] Would auto-reply to email from: {headers.get('From', 'Unknown')}"
                )
            else:
                success = self._send_auto_reply(message["id"], thread_id, headers)
                done_file.write_text(
                    f"---\ntype: email_auto_replied\n"
                    f"from: {headers.get('From', 'Unknown')}\n"
                    f"subject: {headers.get('Subject', 'No Subject')}\n"
                    f"created: {datetime.now().isoformat()}\nauto_reply_sent: {success}\n---\n\n"
                    f"Auto-replied to email (no business keywords detected in snippet).\n\n"
                    f"**Reply sent:** {GMAIL_AUTO_REPLY}\n"
                )
                self.log_event("email_auto_reply_sent", {
                    "message_id": message["id"],
                    "from": headers.get("From", "Unknown"),
                    "subject": headers.get("Subject", "No Subject"),
                    "success": success,
                })

            self.processed_ids.add(message["id"])
            self._save_processed_ids()
            return done_file
        # ───────────────────────────────────────────────────────────────────

        action_file = self.needs_action / filename

        if DRY_RUN:
            self.logger.info(f"[DRY RUN] Would create: {action_file.name}")
            self.processed_ids.add(message["id"])
            return action_file

        content = f"""---
type: email
source: gmail
message_id: {message['id']}
from: {headers.get('From', 'Unknown')}
to: {headers.get('To', 'Unknown')}
subject: {headers.get('Subject', 'No Subject')}
date: {headers.get('Date', 'Unknown')}
received: {datetime.now().isoformat()}
priority: {priority}
status: pending
assigned_to: claude_code
---

## Email: {headers.get('Subject', 'No Subject')}

**From:** {headers.get('From', 'Unknown')}
**Date:** {headers.get('Date', 'Unknown')}

### Preview

> {snippet}

### Suggested Actions

- [ ] Read full email in Gmail
- [ ] Draft reply (move to /Pending_Approval when ready)
- [ ] Flag if action required
- [ ] Archive after processing

### Notes

_Add context or action taken here._

---
*Created by: GmailWatcher · Bronze Tier*
"""
        action_file.write_text(content)
        self.processed_ids.add(message["id"])
        self._save_processed_ids()

        self.log_event("email_detected", {
            "message_id": message["id"],
            "from": headers.get("From", "Unknown"),
            "subject": headers.get("Subject", "No Subject"),
            "priority": priority,
        })

        return action_file


def main():
    parser = argparse.ArgumentParser(
        description="AI Employee — Gmail Watcher",
        epilog="Run with --setup to authorize Gmail access.",
    )
    parser.add_argument("--vault", default=str(Path(__file__).parent.parent / "AI_Employee_Vault"))
    parser.add_argument("--credentials", default=str(Path(__file__).parent / "credentials.json"))
    parser.add_argument("--token", default=str(Path(__file__).parent / "token.json"))
    parser.add_argument("--dry-run", action="store_true", default=DRY_RUN)
    args = parser.parse_args()

    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    vault_path = Path(args.vault).resolve()
    if not vault_path.exists():
        print(f"Error: Vault path does not exist: {vault_path}")
        sys.exit(1)

    watcher = GmailWatcher(str(vault_path), args.credentials, args.token)
    watcher.run()


if __name__ == "__main__":
    main()
