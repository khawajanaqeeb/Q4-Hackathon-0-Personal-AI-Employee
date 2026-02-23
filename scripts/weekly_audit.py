#!/usr/bin/env python3
"""weekly_audit.py - Weekly Business & Accounting Audit for Personal AI Employee (Gold Tier).

Generates the "Monday Morning CEO Briefing":
  1. Reads Business_Goals.md for targets and KPIs
  2. Audits Accounting/ for revenue and transactions
  3. Reviews Done/ for completed tasks this week
  4. Scans Logs/ for AI activity
  5. Optionally queries Odoo for financial data (if ODOO_URL is configured)
  6. Detects subscription patterns for cost optimization
  7. Writes briefing to Briefings/YYYY-MM-DD_Weekly_Briefing.md

Usage:
    python3 scripts/weekly_audit.py --vault AI_Employee_Vault
    python3 scripts/weekly_audit.py --vault AI_Employee_Vault --period 7
    python3 scripts/weekly_audit.py --vault AI_Employee_Vault --dry-run
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT_DEFAULT = ROOT / "AI_Employee_Vault"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [WeeklyAudit] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("WeeklyAudit")

# ── Subscription pattern matching (Gold tier) ──────────────────────────────────
SUBSCRIPTION_PATTERNS = {
    "netflix.com": "Netflix",
    "spotify.com": "Spotify",
    "adobe.com": "Adobe Creative Cloud",
    "notion.so": "Notion",
    "slack.com": "Slack",
    "github.com": "GitHub",
    "aws.amazon.com": "AWS",
    "digitalocean.com": "DigitalOcean",
    "heroku.com": "Heroku",
    "zoom.us": "Zoom",
    "dropbox.com": "Dropbox",
    "gsuite": "Google Workspace",
    "microsoft 365": "Microsoft 365",
    "anthropic": "Anthropic (Claude API)",
    "openai": "OpenAI API",
    "figma.com": "Figma",
    "linear.app": "Linear",
    "atlassian": "Atlassian (Jira/Confluence)",
    "mailchimp": "Mailchimp",
    "hubspot": "HubSpot",
    "sendgrid": "SendGrid",
    "twilio": "Twilio",
    "vercel": "Vercel",
    "railway": "Railway",
}


def _parse_transactions_md(vault_path: Path, days: int = 7) -> dict:
    """Parse Accounting/ folder for transaction data."""
    accounting_dir = vault_path / "Accounting"
    if not accounting_dir.exists():
        return {"revenue": 0, "expenses": 0, "transactions": [], "subscriptions": []}

    cutoff = datetime.now() - timedelta(days=days)
    transactions = []
    subscriptions_detected = []

    for txn_file in accounting_dir.glob("*.md"):
        try:
            content = txn_file.read_text()
            # Parse markdown table rows: | date | description | amount | type |
            for line in content.splitlines():
                if not line.startswith("|") or "---" in line or "date" in line.lower():
                    continue
                parts = [p.strip() for p in line.strip("|").split("|")]
                if len(parts) < 3:
                    continue
                try:
                    date_str = parts[0].strip()
                    description = parts[1].strip() if len(parts) > 1 else ""
                    amount_str = parts[2].strip() if len(parts) > 2 else "0"
                    txn_type = parts[3].strip() if len(parts) > 3 else "unknown"

                    # Parse date
                    txn_date = None
                    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y"):
                        try:
                            txn_date = datetime.strptime(date_str, fmt)
                            break
                        except ValueError:
                            continue

                    if txn_date and txn_date < cutoff:
                        continue

                    # Parse amount
                    amount_clean = re.sub(r"[^\d.-]", "", amount_str)
                    amount = float(amount_clean) if amount_clean else 0.0

                    transactions.append({
                        "date": date_str,
                        "description": description,
                        "amount": amount,
                        "type": txn_type,
                    })

                    # Detect subscriptions
                    desc_lower = description.lower()
                    for pattern, name in SUBSCRIPTION_PATTERNS.items():
                        if pattern in desc_lower:
                            subscriptions_detected.append({
                                "name": name,
                                "amount": amount,
                                "date": date_str,
                                "description": description,
                            })
                            break
                except (ValueError, IndexError):
                    continue
        except Exception as e:
            logger.warning(f"Could not parse {txn_file.name}: {e}")

    revenue = sum(t["amount"] for t in transactions if t["type"].lower() in ("income", "revenue", "payment"))
    expenses = sum(t["amount"] for t in transactions if t["type"].lower() in ("expense", "cost", "subscription"))

    return {
        "revenue": revenue,
        "expenses": expenses,
        "net": revenue - expenses,
        "transactions": transactions,
        "subscriptions": subscriptions_detected,
    }


def _parse_done_tasks(vault_path: Path, days: int = 7) -> list:
    """List tasks completed in the last N days."""
    done_dir = vault_path / "Done"
    if not done_dir.exists():
        return []

    cutoff = datetime.now() - timedelta(days=days)
    tasks = []

    for task_file in sorted(done_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True):
        mtime = datetime.fromtimestamp(task_file.stat().st_mtime)
        if mtime < cutoff:
            continue
        tasks.append({
            "file": task_file.name,
            "completed": mtime.strftime("%Y-%m-%d %H:%M"),
            "type": task_file.name.split("_")[0],
        })

    return tasks


def _parse_business_goals(vault_path: Path) -> dict:
    """Extract key metrics from Business_Goals.md."""
    goals_file = vault_path / "Business_Goals.md"
    if not goals_file.exists():
        return {"monthly_target": 10000, "current_mtd": 0, "goals": []}

    content = goals_file.read_text()
    goals = {"monthly_target": 0, "current_mtd": 0, "goals": [], "active_projects": [], "raw": content}

    # Extract monthly goal
    match = re.search(r"[Mm]onthly goal[:\s]+\$?([\d,]+)", content)
    if match:
        goals["monthly_target"] = float(match.group(1).replace(",", ""))

    # Extract current MTD
    match = re.search(r"[Cc]urrent\s+MTD[:\s]+\$?([\d,]+)", content)
    if match:
        goals["current_mtd"] = float(match.group(1).replace(",", ""))

    # Extract active projects
    projects = re.findall(r"^\d+\.\s+(.+?)\s*[-–]\s*Due", content, re.MULTILINE)
    goals["active_projects"] = projects[:5]

    return goals


def _parse_logs(vault_path: Path, days: int = 7) -> dict:
    """Aggregate activity from Logs/ JSON files."""
    logs_dir = vault_path / "Logs"
    if not logs_dir.exists():
        return {"total_events": 0, "by_type": {}, "errors": []}

    cutoff = datetime.now() - timedelta(days=days)
    all_events = []

    for log_file in sorted(logs_dir.glob("*.json"), reverse=True)[:days + 1]:
        try:
            entries = json.loads(log_file.read_text())
            for entry in entries:
                ts_str = entry.get("timestamp", "")
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts < cutoff:
                        continue
                except ValueError:
                    pass
                all_events.append(entry)
        except Exception:
            continue

    by_type = {}
    errors = []
    for event in all_events:
        et = event.get("event_type", "unknown")
        by_type[et] = by_type.get(et, 0) + 1
        if "error" in et.lower() or event.get("result") == "error":
            errors.append(event)

    return {"total_events": len(all_events), "by_type": by_type, "errors": errors[-5:]}


def _try_odoo_summary() -> dict | None:
    """Optionally pull financial data from Odoo MCP."""
    odoo_url = os.getenv("ODOO_URL", "")
    if not odoo_url:
        return None
    try:
        sys.path.insert(0, str(ROOT / "mcp_servers"))
        from odoo_server import handle_odoo_get_financial_summary
        result = handle_odoo_get_financial_summary({"period": "this_month"})
        if "error" not in result:
            return result
    except Exception as e:
        logger.warning(f"Could not fetch Odoo data: {e}")
    return None


def generate_briefing(vault_path: Path, days: int = 7) -> Path:
    """Generate the weekly CEO briefing and save to Briefings/."""
    logger.info(f"Generating weekly audit (last {days} days)...")

    # ── Gather data ────────────────────────────────────────────────────────────
    txn_data = _parse_transactions_md(vault_path, days)
    done_tasks = _parse_done_tasks(vault_path, days)
    goals = _parse_business_goals(vault_path)
    logs_data = _parse_logs(vault_path, days)
    odoo_data = _try_odoo_summary()

    now = datetime.now()
    period_start = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    period_end = now.strftime("%Y-%m-%d")
    today_str = now.strftime("%Y-%m-%d")
    day_name = now.strftime("%A")

    # Revenue calculation
    revenue = txn_data["revenue"]
    if odoo_data and odoo_data.get("total_paid"):
        revenue = odoo_data["total_paid"]  # prefer Odoo data if available

    monthly_target = goals.get("monthly_target", 10000)
    current_mtd = goals.get("current_mtd", 0) or revenue
    pct_target = (current_mtd / monthly_target * 100) if monthly_target else 0
    trend = "On track" if pct_target >= (now.day / 28 * 100) else "Behind target"

    # ── Build briefing markdown ─────────────────────────────────────────────────
    lines = [
        f"---",
        f"generated: {now.isoformat()}",
        f"period: {period_start} to {period_end}",
        f"type: weekly_ceo_briefing",
        f"---",
        f"",
        f"# {day_name} Morning CEO Briefing",
        f"",
        f"*AI Employee · Gold Tier · Generated {now.strftime('%Y-%m-%d %H:%M')}*",
        f"",
        f"---",
        f"",
        f"## Executive Summary",
    ]

    # Status assessment
    if pct_target >= 80:
        exec_summary = f"Strong week. Revenue at {pct_target:.0f}% of monthly target."
    elif pct_target >= 50:
        exec_summary = f"Moderate week. Revenue at {pct_target:.0f}% of monthly target. Acceleration needed."
    else:
        exec_summary = f"Below target week. Revenue at {pct_target:.0f}% of monthly target. Action required."

    lines.append(exec_summary)
    lines += ["", "---", "", "## Revenue"]
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| This Period | ${revenue:,.2f} |")
    lines.append(f"| MTD | ${current_mtd:,.2f} ({pct_target:.0f}% of ${monthly_target:,.0f} target) |")
    lines.append(f"| Trend | {trend} |")

    if odoo_data:
        lines.append(f"| Odoo Outstanding | ${odoo_data.get('total_outstanding', 0):,.2f} |")
        if odoo_data.get("overdue_amount", 0) > 0:
            lines.append(f"| ⚠️ Overdue | ${odoo_data.get('overdue_amount', 0):,.2f} ({odoo_data.get('overdue_count', 0)} invoices) |")

    lines += ["", "---", "", "## Completed Tasks This Period"]
    if done_tasks:
        # Group by type
        task_types = {}
        for task in done_tasks:
            t = task["type"]
            task_types[t] = task_types.get(t, 0) + 1

        lines.append(f"Total: **{len(done_tasks)} tasks** completed")
        lines.append("")
        for ttype, count in sorted(task_types.items(), key=lambda x: -x[1]):
            lines.append(f"- {ttype}: {count}")
        lines.append("")
        lines.append("### Recent Completions")
        for task in done_tasks[:10]:
            lines.append(f"- [{task['completed']}] `{task['file']}`")
    else:
        lines.append("No tasks completed in this period.")

    # ── Bottlenecks ────────────────────────────────────────────────────────────
    lines += ["", "---", "", "## Bottlenecks & Issues"]
    if logs_data["errors"]:
        lines.append(f"**{len(logs_data['errors'])} errors detected in AI logs:**")
        lines.append("")
        for err in logs_data["errors"]:
            lines.append(f"- {err.get('timestamp', '')[:19]} — {err.get('event_type', 'unknown')}: {str(err)[:100]}")
    else:
        lines.append("✅ No errors detected in AI activity logs.")

    pending_approval = list((vault_path / "Pending_Approval").glob("*.md")) if (vault_path / "Pending_Approval").exists() else []
    if pending_approval:
        lines.append("")
        lines.append(f"**{len(pending_approval)} items awaiting approval:**")
        for f in pending_approval[:5]:
            lines.append(f"  - `{f.name}`")

    # ── Proactive Suggestions ──────────────────────────────────────────────────
    lines += ["", "---", "", "## Proactive Suggestions"]

    suggestions = []

    # Subscription cost review
    if txn_data["subscriptions"]:
        lines.append("### 💰 Cost Optimization")
        for sub in txn_data["subscriptions"][:5]:
            lines.append(
                f"- **{sub['name']}**: ${sub['amount']:.2f}/period detected. "
                f"Review if actively used."
            )
        lines.append("")

    # Revenue gap
    if pct_target < 50 and monthly_target > 0:
        remaining = monthly_target - current_mtd
        suggestions.append(f"Revenue gap: ${remaining:,.2f} needed to hit monthly target. Consider outreach or new proposals.")

    # Pending too long
    old_pending = []
    for f in pending_approval:
        age_days = (now - datetime.fromtimestamp(f.stat().st_mtime)).days
        if age_days > 3:
            old_pending.append((f.name, age_days))
    if old_pending:
        suggestions.append(f"{len(old_pending)} approval items pending >3 days. Review: " + ", ".join(f"`{n}`" for n, _ in old_pending[:3]))

    if suggestions:
        lines.append("### 📋 Action Items")
        for s in suggestions:
            lines.append(f"- {s}")
        lines.append("")
    else:
        lines.append("No critical action items. System running smoothly.")

    # ── Active Projects ─────────────────────────────────────────────────────────
    if goals.get("active_projects"):
        lines += ["", "---", "", "## Active Projects"]
        for proj in goals["active_projects"]:
            lines.append(f"- {proj}")

    # ── Upcoming Deadlines ──────────────────────────────────────────────────────
    lines += ["", "---", "", "## System Activity (Last 7 Days)"]
    lines.append(f"Total AI events: **{logs_data['total_events']}**")
    if logs_data["by_type"]:
        lines.append("")
        lines.append("| Event Type | Count |")
        lines.append("|-----------|-------|")
        for et, count in sorted(logs_data["by_type"].items(), key=lambda x: -x[1])[:10]:
            lines.append(f"| {et} | {count} |")

    # ── Footer ──────────────────────────────────────────────────────────────────
    lines += [
        "",
        "---",
        "",
        f"*Generated by AI Employee (Gold Tier) · {now.strftime('%Y-%m-%d %H:%M')}*",
        "",
        "_Review this briefing and take action on any flagged items._",
    ]

    # ── Write to Briefings/ ────────────────────────────────────────────────────
    briefings_dir = vault_path / "Briefings"
    briefings_dir.mkdir(exist_ok=True)
    briefing_file = briefings_dir / f"{today_str}_Weekly_Briefing.md"
    briefing_file.write_text("\n".join(lines))

    # ── Log the audit ──────────────────────────────────────────────────────────
    log_file = vault_path / "Logs" / f"{today_str}.json"
    entries = []
    if log_file.exists():
        try:
            entries = json.loads(log_file.read_text())
        except Exception:
            pass
    entries.append({
        "timestamp": now.isoformat(),
        "event_type": "weekly_audit_generated",
        "actor": "WeeklyAudit",
        "briefing_file": briefing_file.name,
        "tasks_completed": len(done_tasks),
        "revenue": revenue,
        "errors_found": len(logs_data["errors"]),
        "result": "success",
    })
    log_file.write_text(json.dumps(entries, indent=2))

    logger.info(f"Briefing written to: {briefing_file}")
    return briefing_file


def main():
    parser = argparse.ArgumentParser(description="Weekly Business Audit & CEO Briefing (Gold Tier)")
    parser.add_argument("--vault", default=str(VAULT_DEFAULT), help="Path to AI_Employee_Vault")
    parser.add_argument("--period", type=int, default=7, help="Audit period in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Generate briefing without modifying logs")
    args = parser.parse_args()

    vault = Path(args.vault).resolve()
    if not vault.exists():
        logger.error(f"Vault not found: {vault}")
        sys.exit(1)

    briefing_path = generate_briefing(vault, days=args.period)
    print(f"\n✅ Weekly briefing generated: {briefing_path}")
    print("\nPreview:")
    print("=" * 60)
    content = briefing_path.read_text()
    # Print first 40 lines
    for i, line in enumerate(content.splitlines()[:40]):
        print(line)
    if len(content.splitlines()) > 40:
        print(f"... ({len(content.splitlines()) - 40} more lines)")


if __name__ == "__main__":
    main()
