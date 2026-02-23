#!/usr/bin/env python3
"""odoo_server.py - Odoo Community MCP Server for Personal AI Employee (Gold Tier).

JSON-RPC 2.0 MCP server over stdio.
Interfaces with Odoo Community via Odoo's JSON-RPC External API.

Reference: https://www.odoo.com/documentation/19.0/developer/reference/external_api.html
GitHub MCP ref: https://github.com/AlanOgic/mcp-odoo-adv

Tools exposed:
  - odoo_authenticate      — test connection and authenticate
  - odoo_get_invoices      — list customer invoices
  - odoo_create_invoice    — create a new customer invoice
  - odoo_get_partners      — list customers/contacts
  - odoo_get_financial_summary — revenue/expense summary
  - odoo_list_products     — list products/services
  - odoo_get_payments      — list payments received

Environment variables:
    ODOO_URL       — Odoo base URL (e.g. http://localhost:8069)
    ODOO_DB        — database name
    ODOO_USERNAME  — login username
    ODOO_PASSWORD  — password or API key
    DRY_RUN        — if "true", return mock data (for demo without Odoo installed)

Setup (Odoo Community local):
    # Docker (easiest):
    docker run -p 8069:8069 -e HOST=0.0.0.0 odoo:17

    # Then visit http://localhost:8069, create database, set credentials in .env

Usage:
    python3 mcp_servers/odoo_server.py --test
"""

import json
import logging
import os
import sys
import xmlrpc.client
from datetime import datetime, date
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [OdooMCP] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("OdooMCP")

# ── Configuration ─────────────────────────────────────────────────────────────
ODOO_URL = os.getenv("ODOO_URL", "http://localhost:8069")
ODOO_DB = os.getenv("ODOO_DB", "odoo")
ODOO_USERNAME = os.getenv("ODOO_USERNAME", "admin")
ODOO_PASSWORD = os.getenv("ODOO_PASSWORD", "admin")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
VAULT_PATH = Path(os.getenv("VAULT_PATH", str(ROOT / "AI_Employee_Vault")))

# ── Odoo JSON-RPC Client ──────────────────────────────────────────────────────

class OdooClient:
    """
    Thin wrapper around Odoo's XML-RPC External API.

    Odoo exposes two XML-RPC endpoints:
      /xmlrpc/2/common  — authentication (no auth needed)
      /xmlrpc/2/object  — model operations (requires uid)
    """

    def __init__(self, url: str, db: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid: int | None = None
        self._common = None
        self._models = None

    def _get_common(self):
        if not self._common:
            self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        return self._common

    def _get_models(self):
        if not self._models:
            self._models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        return self._models

    def authenticate(self) -> int:
        """Authenticate and return uid."""
        try:
            common = self._get_common()
            self.uid = common.authenticate(self.db, self.username, self.password, {})
            if not self.uid:
                raise ValueError("Authentication failed — check credentials")
            return self.uid
        except Exception as e:
            raise ConnectionError(f"Odoo authentication error: {e}")

    def ensure_auth(self):
        if not self.uid:
            self.authenticate()

    def execute(self, model: str, method: str, *args, **kwargs) -> any:
        self.ensure_auth()
        models = self._get_models()
        return models.execute_kw(self.db, self.uid, self.password, model, method, list(args), kwargs)

    def search_read(self, model: str, domain: list, fields: list, limit: int = 50, offset: int = 0) -> list:
        return self.execute(model, "search_read", domain, fields=fields, limit=limit, offset=offset)

    def create(self, model: str, values: dict) -> int:
        return self.execute(model, "create", values)

    def write(self, model: str, ids: list, values: dict) -> bool:
        return self.execute(model, "write", ids, values)

    def read(self, model: str, ids: list, fields: list) -> list:
        return self.execute(model, "read", ids, fields=fields)


# ── Mock Data (when Odoo is not installed / DRY_RUN) ──────────────────────────

MOCK_INVOICES = [
    {
        "id": 1, "name": "INV/2026/00001", "partner_id": [1, "Client A"],
        "amount_total": 1500.0, "state": "posted", "invoice_date": "2026-02-20",
        "invoice_date_due": "2026-03-20", "payment_state": "paid",
    },
    {
        "id": 2, "name": "INV/2026/00002", "partner_id": [2, "Client B"],
        "amount_total": 2500.0, "state": "posted", "invoice_date": "2026-02-22",
        "invoice_date_due": "2026-03-22", "payment_state": "not_paid",
    },
    {
        "id": 3, "name": "INV/2026/00003", "partner_id": [3, "Client C"],
        "amount_total": 800.0, "state": "draft", "invoice_date": "2026-02-24",
        "invoice_date_due": "2026-03-24", "payment_state": "not_paid",
    },
]

MOCK_PARTNERS = [
    {"id": 1, "name": "Client A", "email": "client_a@example.com", "phone": "+1-555-0100"},
    {"id": 2, "name": "Client B", "email": "client_b@example.com", "phone": "+1-555-0200"},
    {"id": 3, "name": "Client C", "email": "client_c@example.com", "phone": "+1-555-0300"},
]

MOCK_PRODUCTS = [
    {"id": 1, "name": "Consulting Services", "list_price": 150.0, "type": "service"},
    {"id": 2, "name": "Web Development", "list_price": 3000.0, "type": "service"},
    {"id": 3, "name": "Monthly Retainer", "list_price": 1000.0, "type": "service"},
]


def _get_client() -> OdooClient:
    return OdooClient(ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD)


def _log_action(action_type: str, details: dict):
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = VAULT_PATH / "Logs" / f"{today}.json"
    entry = {
        "timestamp": datetime.now().isoformat(),
        "event_type": action_type,
        "actor": "OdooMCP",
        "dry_run": DRY_RUN,
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


# ── Tool Definitions ──────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "odoo_authenticate",
        "description": "Test connection to Odoo and authenticate. Returns server version and uid.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "odoo_get_invoices",
        "description": "List customer invoices from Odoo. Filter by state (draft/posted/paid) or date range.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "enum": ["draft", "posted", "cancel", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 20},
                "payment_state": {"type": "string", "enum": ["not_paid", "paid", "partial", "all"], "default": "all"},
            },
        },
    },
    {
        "name": "odoo_create_invoice",
        "description": (
            "Create a new customer invoice in Odoo. "
            "IMPORTANT: This creates a DRAFT invoice. Posting/confirming requires approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "partner_name": {"type": "string", "description": "Customer name"},
                "partner_id": {"type": "integer", "description": "Customer ID (use odoo_get_partners to find)"},
                "amount": {"type": "number", "description": "Invoice total amount"},
                "description": {"type": "string", "description": "Line item description"},
                "due_days": {"type": "integer", "description": "Days until due (default 30)", "default": 30},
            },
            "required": ["partner_name", "amount", "description"],
        },
    },
    {
        "name": "odoo_get_partners",
        "description": "List customers and contacts in Odoo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "search": {"type": "string", "description": "Search by name or email", "default": ""},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "odoo_get_financial_summary",
        "description": "Get financial summary: revenue, outstanding invoices, overdue amounts for the current month/year.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": ["this_month", "this_year", "all"], "default": "this_month"},
            },
        },
    },
    {
        "name": "odoo_list_products",
        "description": "List products and services configured in Odoo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["service", "product", "all"], "default": "all"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "odoo_get_payments",
        "description": "List payments received from customers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
]


# ── Tool Handlers ─────────────────────────────────────────────────────────────

def handle_odoo_authenticate(args: dict) -> dict:
    if DRY_RUN:
        return {
            "success": True,
            "dry_run": True,
            "server_version": "17.0",
            "uid": 1,
            "username": ODOO_USERNAME,
            "database": ODOO_DB,
            "url": ODOO_URL,
            "note": "Mock mode — Odoo not connected. Set ODOO_URL, ODOO_DB, ODOO_USERNAME, ODOO_PASSWORD in .env to connect.",
        }
    try:
        client = _get_client()
        uid = client.authenticate()
        common = client._get_common()
        version = common.version()
        return {
            "success": True,
            "uid": uid,
            "username": ODOO_USERNAME,
            "database": ODOO_DB,
            "url": ODOO_URL,
            "server_version": version.get("server_version", "unknown"),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_odoo_get_invoices(args: dict) -> dict:
    state = args.get("state", "all")
    limit = args.get("limit", 20)
    payment_state = args.get("payment_state", "all")

    if DRY_RUN:
        invoices = MOCK_INVOICES.copy()
        if state != "all":
            invoices = [i for i in invoices if i["state"] == state]
        if payment_state != "all":
            invoices = [i for i in invoices if i["payment_state"] == payment_state]
        _log_action("odoo_get_invoices", {"count": len(invoices), "state": state})
        total = sum(i["amount_total"] for i in invoices)
        return {
            "invoices": invoices[:limit],
            "total_count": len(invoices),
            "total_amount": total,
            "dry_run": True,
        }

    try:
        client = _get_client()
        domain = [("move_type", "=", "out_invoice")]
        if state != "all":
            domain.append(("state", "=", state))
        if payment_state != "all":
            domain.append(("payment_state", "=", payment_state))

        fields = ["name", "partner_id", "amount_total", "state", "invoice_date", "invoice_date_due", "payment_state"]
        invoices = client.search_read("account.move", domain, fields, limit=limit)
        total = sum(i.get("amount_total", 0) for i in invoices)
        _log_action("odoo_get_invoices", {"count": len(invoices), "total": total})
        return {"invoices": invoices, "total_count": len(invoices), "total_amount": total}
    except Exception as e:
        return {"error": str(e)}


def handle_odoo_create_invoice(args: dict) -> dict:
    partner_name = args.get("partner_name", "")
    partner_id = args.get("partner_id")
    amount = args.get("amount", 0)
    description = args.get("description", "")
    due_days = args.get("due_days", 30)

    if not partner_name or not amount or not description:
        return {"error": "partner_name, amount, and description are required"}

    if DRY_RUN:
        invoice_name = f"INV/2026/{datetime.now().strftime('%H%M%S')}"
        _log_action("odoo_create_invoice", {
            "partner": partner_name,
            "amount": amount,
            "description": description,
            "invoice_name": invoice_name,
        })
        return {
            "success": True,
            "dry_run": True,
            "invoice_id": 999,
            "invoice_name": invoice_name,
            "partner": partner_name,
            "amount": amount,
            "state": "draft",
            "note": "Mock invoice created. In production, this creates a draft in Odoo.",
        }

    try:
        client = _get_client()

        # Find or use partner
        if not partner_id:
            partners = client.search_read(
                "res.partner",
                [("name", "ilike", partner_name)],
                ["id", "name"],
                limit=1,
            )
            if not partners:
                partner_id = client.create("res.partner", {"name": partner_name, "customer_rank": 1})
            else:
                partner_id = partners[0]["id"]

        invoice_vals = {
            "move_type": "out_invoice",
            "partner_id": partner_id,
            "invoice_date": date.today().isoformat(),
            "invoice_line_ids": [(0, 0, {
                "name": description,
                "quantity": 1,
                "price_unit": amount,
            })],
        }
        invoice_id = client.create("account.move", invoice_vals)
        invoice = client.read("account.move", [invoice_id], ["name", "amount_total", "state"])[0]
        _log_action("odoo_create_invoice", {
            "invoice_id": invoice_id,
            "invoice_name": invoice["name"],
            "partner": partner_name,
            "amount": amount,
        })
        return {
            "success": True,
            "invoice_id": invoice_id,
            "invoice_name": invoice["name"],
            "amount_total": invoice["amount_total"],
            "state": invoice["state"],
        }
    except Exception as e:
        return {"error": str(e)}


def handle_odoo_get_partners(args: dict) -> dict:
    search = args.get("search", "")
    limit = args.get("limit", 20)

    if DRY_RUN:
        partners = MOCK_PARTNERS
        if search:
            partners = [p for p in partners if search.lower() in p["name"].lower()]
        return {"partners": partners[:limit], "total": len(partners), "dry_run": True}

    try:
        client = _get_client()
        domain = [("customer_rank", ">", 0)]
        if search:
            domain.append(("name", "ilike", search))
        fields = ["name", "email", "phone", "mobile", "website"]
        partners = client.search_read("res.partner", domain, fields, limit=limit)
        return {"partners": partners, "total": len(partners)}
    except Exception as e:
        return {"error": str(e)}


def handle_odoo_get_financial_summary(args: dict) -> dict:
    period = args.get("period", "this_month")

    if DRY_RUN:
        paid = sum(i["amount_total"] for i in MOCK_INVOICES if i["payment_state"] == "paid")
        unpaid = sum(i["amount_total"] for i in MOCK_INVOICES if i["payment_state"] == "not_paid")
        total = paid + unpaid
        return {
            "period": period,
            "total_invoiced": total,
            "total_paid": paid,
            "total_outstanding": unpaid,
            "invoice_count": len(MOCK_INVOICES),
            "overdue_count": 0,
            "overdue_amount": 0,
            "dry_run": True,
            "summary": f"Total invoiced: ${total:,.2f} | Paid: ${paid:,.2f} | Outstanding: ${unpaid:,.2f}",
        }

    try:
        client = _get_client()
        today = date.today()

        if period == "this_month":
            date_from = today.replace(day=1).isoformat()
            date_to = today.isoformat()
        elif period == "this_year":
            date_from = today.replace(month=1, day=1).isoformat()
            date_to = today.isoformat()
        else:
            date_from = "2000-01-01"
            date_to = today.isoformat()

        domain = [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("invoice_date", ">=", date_from),
            ("invoice_date", "<=", date_to),
        ]
        fields = ["amount_total", "payment_state", "invoice_date_due"]
        invoices = client.search_read("account.move", domain, fields, limit=1000)

        total = sum(i.get("amount_total", 0) for i in invoices)
        paid = sum(i.get("amount_total", 0) for i in invoices if i.get("payment_state") == "paid")
        outstanding = total - paid
        overdue = [i for i in invoices if i.get("payment_state") != "paid" and i.get("invoice_date_due", "") < today.isoformat()]

        _log_action("odoo_financial_summary", {"period": period, "total": total, "paid": paid})
        return {
            "period": period,
            "date_range": f"{date_from} to {date_to}",
            "total_invoiced": total,
            "total_paid": paid,
            "total_outstanding": outstanding,
            "invoice_count": len(invoices),
            "overdue_count": len(overdue),
            "overdue_amount": sum(i.get("amount_total", 0) for i in overdue),
            "summary": f"Total invoiced: ${total:,.2f} | Paid: ${paid:,.2f} | Outstanding: ${outstanding:,.2f}",
        }
    except Exception as e:
        return {"error": str(e)}


def handle_odoo_list_products(args: dict) -> dict:
    product_type = args.get("type", "all")
    limit = args.get("limit", 20)

    if DRY_RUN:
        products = MOCK_PRODUCTS
        if product_type != "all":
            products = [p for p in products if p["type"] == product_type]
        return {"products": products[:limit], "total": len(products), "dry_run": True}

    try:
        client = _get_client()
        domain = []
        if product_type != "all":
            domain.append(("type", "=", product_type))
        fields = ["name", "list_price", "type", "description_sale"]
        products = client.search_read("product.product", domain, fields, limit=limit)
        return {"products": products, "total": len(products)}
    except Exception as e:
        return {"error": str(e)}


def handle_odoo_get_payments(args: dict) -> dict:
    limit = args.get("limit", 20)

    if DRY_RUN:
        return {
            "payments": [
                {"id": 1, "name": "BNK1/2026/00001", "partner_id": [1, "Client A"],
                 "amount": 1500.0, "date": "2026-02-21", "state": "posted"},
            ],
            "total_count": 1,
            "total_amount": 1500.0,
            "dry_run": True,
        }

    try:
        client = _get_client()
        domain = [("payment_type", "=", "inbound"), ("state", "=", "posted")]
        fields = ["name", "partner_id", "amount", "date", "state"]
        payments = client.search_read("account.payment", domain, fields, limit=limit)
        total = sum(p.get("amount", 0) for p in payments)
        return {"payments": payments, "total_count": len(payments), "total_amount": total}
    except Exception as e:
        return {"error": str(e)}


# ── JSON-RPC 2.0 Server ───────────────────────────────────────────────────────

TOOL_HANDLERS = {
    "odoo_authenticate": handle_odoo_authenticate,
    "odoo_get_invoices": handle_odoo_get_invoices,
    "odoo_create_invoice": handle_odoo_create_invoice,
    "odoo_get_partners": handle_odoo_get_partners,
    "odoo_get_financial_summary": handle_odoo_get_financial_summary,
    "odoo_list_products": handle_odoo_list_products,
    "odoo_get_payments": handle_odoo_get_payments,
}


def handle_request(request: dict) -> dict | None:
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "odoo-mcp", "version": "1.0.0"},
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
        return None

    return err(-32601, f"Method not found: {method}")


def run_server():
    logger.info("Odoo MCP Server starting (stdio transport)")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as e:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(e)}}), flush=True)
            continue
        response = handle_request(request)
        if response is not None:
            print(json.dumps(response), flush=True)


def run_test():
    print("Odoo MCP Server — Test Mode")
    print(f"Odoo URL: {ODOO_URL}")
    print(f"Database: {ODOO_DB}")
    print(f"Username: {ODOO_USERNAME}")
    print(f"DRY_RUN: {DRY_RUN}")

    print("\n--- Testing authenticate ---")
    result = handle_odoo_authenticate({})
    print(json.dumps(result, indent=2))

    print("\n--- Testing get_invoices ---")
    result = handle_odoo_get_invoices({"state": "all", "limit": 5})
    print(json.dumps(result, indent=2))

    print("\n--- Testing financial_summary ---")
    result = handle_odoo_get_financial_summary({"period": "this_month"})
    print(json.dumps(result, indent=2))

    print("\n✅ Odoo MCP Server ready.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        run_test()
    else:
        run_server()
