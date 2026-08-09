"""
Provision the NorthPeak governed BI layer in Metabase via its REST API.

This is the code-as-configuration counterpart to the click-through steps in
README.md sections 3-5. Running it against a fresh (already set-up) Metabase
instance creates, idempotently:

  * the DuckDB warehouse connection (if not already present)
  * two collections:
      - "NorthPeak KPIs" — company-wide governed questions
      - "Finance"        — revenue-recognition + customer-LTV (restricted)
  * the seven governed questions from governed_questions.sql, each as a native
    SQL card reading ONLY the dbt marts, with a sensible visualization
  * a "NorthPeak KPIs" dashboard with the company-wide cards laid out on it
  * two permission groups (Marketing, Finance) wired so Marketing can see the
    KPIs collection but NOT the Finance collection — the "finance sees
    revenue-recognition, marketing doesn't" governance requirement.

Idempotent: re-running matches existing objects by name and updates them in
place rather than creating duplicates.

Usage:
    python dashboards/metabase_export/provision_metabase.py \
        --url http://localhost:3000 \
        --user you@example.com --password 'secret'

Credentials may also come from MB_USER / MB_PASSWORD env vars.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DB_NAME = "NorthPeak Warehouse"
DB_FILE = "/data/northpeak.duckdb"
KPIS_COLLECTION = "NorthPeak KPIs"
FINANCE_COLLECTION = "Finance"


# --- thin Metabase API client -------------------------------------------------

class MB:
    def __init__(self, base_url: str, session: str):
        self.base = base_url.rstrip("/")
        self.session = session

    @classmethod
    def login(cls, base_url: str, user: str, password: str) -> "MB":
        body = json.dumps({"username": user, "password": password}).encode()
        req = urllib.request.Request(
            base_url.rstrip("/") + "/api/session",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as r:
            sid = json.load(r)["id"]
        return cls(base_url, sid)

    def _req(self, method: str, path: str, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.base + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "X-Metabase-Session": self.session,
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(req) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode()
            raise RuntimeError(f"{method} {path} -> {e.code}: {detail}") from None

    def get(self, path):
        return self._req("GET", path)

    def post(self, path, payload):
        return self._req("POST", path, payload)

    def put(self, path, payload):
        return self._req("PUT", path, payload)


# --- governed question definitions -------------------------------------------
# SQL is copied verbatim from governed_questions.sql; each reads only the marts,
# so results match docs/metric_definitions.md by construction.

QUESTIONS = [
    {
        "name": "Headline KPIs (full history)",
        "collection": KPIS_COLLECTION,
        "display": "table",
        "sql": """select
    round(sum(net_revenue), 0)                        as net_revenue,
    round(sum(recognized_revenue), 0)                 as recognized_revenue,
    round(sum(gmv), 0)                                as gmv,
    sum(net_orders)                                   as net_orders,
    round(sum(net_revenue) / nullif(sum(net_orders), 0), 2) as aov,
    round(sum(refunds) / nullif(sum(gross_revenue), 0), 4)  as refund_rate
from main_marts.fct_daily_kpis""",
    },
    {
        "name": "Monthly net revenue trend",
        "collection": KPIS_COLLECTION,
        "display": "line",
        "sql": """select date_trunc('month', order_date) as month,
       round(sum(net_revenue), 0)      as net_revenue,
       round(sum(recognized_revenue),0) as recognized_revenue
from main_marts.fct_daily_kpis
group by 1 order by 1""",
        "viz": {
            "graph.dimensions": ["month"],
            "graph.metrics": ["net_revenue", "recognized_revenue"],
        },
    },
    {
        "name": "Net revenue by category",
        "collection": KPIS_COLLECTION,
        "display": "bar",
        "sql": """select category, round(sum(net_revenue), 0) as net_revenue
from main_marts.dim_products
group by 1 order by 2 desc""",
        "viz": {
            "graph.dimensions": ["category"],
            "graph.metrics": ["net_revenue"],
        },
    },
    {
        "name": "Repeat-purchase rate",
        "collection": KPIS_COLLECTION,
        "display": "table",
        "sql": """select
    count(*) filter (where lifetime_net_orders >= 1)                              as purchasers,
    count(*) filter (where is_repeat_customer)                                    as repeat_customers,
    round(count(*) filter (where is_repeat_customer)
          / nullif(count(*) filter (where lifetime_net_orders >= 1), 0)::double, 3) as repeat_rate
from main_marts.dim_customers""",
    },
    {
        "name": "Orders by status",
        "collection": KPIS_COLLECTION,
        "display": "bar",
        "sql": """select status, count(*) as orders
from main_marts.fct_orders group by 1 order by 2 desc""",
        "viz": {
            "graph.dimensions": ["status"],
            "graph.metrics": ["orders"],
        },
    },
    {
        "name": "Revenue recognition (recognized vs deferred)",
        "collection": FINANCE_COLLECTION,
        "display": "line",
        "sql": """select date_trunc('month', order_date) as month,
       round(sum(recognized_revenue), 0)  as recognized,
       round(sum(processing_deferred), 0) as deferred_processing,
       round(sum(refunds), 0)             as refunds
from main_marts.fct_revenue_recognition
group by 1 order by 1""",
        "viz": {
            "graph.dimensions": ["month"],
            "graph.metrics": ["recognized", "deferred_processing", "refunds"],
        },
    },
    {
        "name": "Top customers by lifetime net revenue",
        "collection": FINANCE_COLLECTION,
        "display": "table",
        "sql": """select user_id, city, state, lifetime_net_orders, round(lifetime_net_revenue, 2) as ltv
from main_marts.dim_customers
order by lifetime_net_revenue desc limit 50""",
    },
]


# --- provisioning steps -------------------------------------------------------

def ensure_database(mb: MB) -> int:
    dbs = mb.get("/api/database")
    data = dbs["data"] if isinstance(dbs, dict) and "data" in dbs else dbs
    for db in data:
        if db["name"] == DB_NAME and db["engine"] == "duckdb":
            print(f"[provision] database '{DB_NAME}' already present (id={db['id']})")
            return db["id"]
    created = mb.post("/api/database", {
        "engine": "duckdb",
        "name": DB_NAME,
        "details": {"database_file": DB_FILE, "read_only": True, "old_implicit_casting": False},
        "is_full_sync": True,
    })
    print(f"[provision] created database '{DB_NAME}' (id={created['id']})")
    return created["id"]


def ensure_collection(mb: MB, name: str, description: str) -> int:
    for c in mb.get("/api/collection"):
        if c.get("name") == name and not c.get("archived"):
            print(f"[provision] collection '{name}' already present (id={c['id']})")
            return c["id"]
    created = mb.post("/api/collection", {"name": name, "description": description})
    print(f"[provision] created collection '{name}' (id={created['id']})")
    return created["id"]


def ensure_question(mb: MB, db_id: int, coll_ids: dict, spec: dict) -> int:
    coll_id = coll_ids[spec["collection"]]
    payload = {
        "name": spec["name"],
        "collection_id": coll_id,
        "dataset_query": {
            "type": "native",
            "native": {"query": spec["sql"]},
            "database": db_id,
        },
        "display": spec["display"],
        "visualization_settings": spec.get("viz", {}),
    }
    # find existing card by name in this collection
    existing = None
    for card in mb.get("/api/card"):
        if card.get("name") == spec["name"] and card.get("collection_id") == coll_id:
            existing = card
            break
    if existing:
        mb.put(f"/api/card/{existing['id']}", payload)
        print(f"[provision]   updated question '{spec['name']}' (id={existing['id']})")
        return existing["id"]
    created = mb.post("/api/card", payload)
    print(f"[provision]   created question '{spec['name']}' (id={created['id']})")
    return created["id"]


def ensure_dashboard(mb: MB, coll_id: int, card_ids: list[int]) -> int:
    name = "NorthPeak KPIs"
    existing = None
    for d in mb.get("/api/dashboard"):
        if d.get("name") == name and not d.get("archived"):
            existing = d
            break
    if existing:
        dash_id = existing["id"]
        print(f"[provision] dashboard '{name}' already present (id={dash_id}) — relaying out cards")
    else:
        created = mb.post("/api/dashboard", {
            "name": name,
            "collection_id": coll_id,
            "description": "Governed self-serve KPIs — every card reads the dbt marts, "
                           "so numbers match docs/metric_definitions.md by construction.",
        })
        dash_id = created["id"]
        print(f"[provision] created dashboard '{name}' (id={dash_id})")

    # Lay cards out two-per-row, 12 grid cols wide, 6 rows tall each.
    dashcards = []
    for i, cid in enumerate(card_ids):
        row = (i // 2) * 6
        col = (i % 2) * 12
        dashcards.append({
            "id": -(i + 1),          # negative = new dashcard
            "card_id": cid,
            "row": row,
            "col": col,
            "size_x": 12,
            "size_y": 6,
        })
    mb.put(f"/api/dashboard/{dash_id}", {"dashcards": dashcards})
    print(f"[provision]   placed {len(dashcards)} cards on the dashboard")
    return dash_id


def ensure_group(mb: MB, name: str) -> int:
    for g in mb.get("/api/permissions/group"):
        if g.get("name") == name:
            print(f"[provision] permission group '{name}' already present (id={g['id']})")
            return g["id"]
    created = mb.post("/api/permissions/group", {"name": name})
    print(f"[provision] created permission group '{name}' (id={created['id']})")
    return created["id"]


def _all_users_gid(mb: MB) -> int:
    for g in mb.get("/api/permissions/group"):
        if g.get("name") == "All Users":
            return g["id"]
    raise RuntimeError("built-in 'All Users' group not found")


def set_collection_permissions(mb: MB, coll_ids: dict, marketing_gid: int, finance_gid: int):
    """Wire collection access so Marketing genuinely cannot see Finance.

    CRITICAL: Metabase grants a user the *most permissive* access across ALL
    their groups, and every user is implicitly in the built-in "All Users"
    group. So restricting the Marketing group alone is cosmetic — if All Users
    still has access to Finance, a Marketing user inherits it. We therefore lock
    All Users OUT of the Finance collection (the one holding revenue-recognition
    and customer-LTV) and grant Finance access only via the named Finance group.

    Resulting effective access:
      * Marketing person (All Users + Marketing): KPIs read, Finance NONE
      * Finance person   (All Users + Finance):   KPIs read, Finance read
    """
    graph = mb.get("/api/collection/graph")
    revision = graph["revision"]
    groups = graph["groups"]

    kpis_id = str(coll_ids[KPIS_COLLECTION])
    fin_id = str(coll_ids[FINANCE_COLLECTION])
    all_users_gid = _all_users_gid(mb)

    for gid in (marketing_gid, finance_gid, all_users_gid):
        groups.setdefault(str(gid), {})

    # All Users: company-wide read on KPIs, but NO access to Finance.
    groups[str(all_users_gid)][kpis_id] = "read"
    groups[str(all_users_gid)][fin_id] = "none"
    # Marketing: read KPIs, explicitly no access to Finance.
    groups[str(marketing_gid)][kpis_id] = "read"
    groups[str(marketing_gid)][fin_id] = "none"
    # Finance: read both.
    groups[str(finance_gid)][kpis_id] = "read"
    groups[str(finance_gid)][fin_id] = "read"

    mb.put("/api/collection/graph", {"revision": revision, "groups": groups})
    print("[provision] set collection permissions "
          "(All Users -> KPIs:read, Finance:none | Marketing -> KPIs:read, Finance:none "
          "| Finance -> both:read)")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:3000")
    p.add_argument("--user", default=os.environ.get("MB_USER"))
    p.add_argument("--password", default=os.environ.get("MB_PASSWORD"))
    args = p.parse_args()
    if not args.user or not args.password:
        print("ERROR: provide --user/--password or MB_USER/MB_PASSWORD", file=sys.stderr)
        return 2

    mb = MB.login(args.url, args.user, args.password)
    print(f"[provision] logged in to {args.url}")

    db_id = ensure_database(mb)

    coll_ids = {
        KPIS_COLLECTION: ensure_collection(
            mb, KPIS_COLLECTION,
            "Company-wide governed KPIs over the dbt marts."),
        FINANCE_COLLECTION: ensure_collection(
            mb, FINANCE_COLLECTION,
            "Finance-only: revenue recognition and customer LTV. Restricted from Marketing."),
    }

    kpi_card_ids = []
    print("[provision] questions:")
    for spec in QUESTIONS:
        cid = ensure_question(mb, db_id, coll_ids, spec)
        if spec["collection"] == KPIS_COLLECTION:
            kpi_card_ids.append(cid)

    ensure_dashboard(mb, coll_ids[KPIS_COLLECTION], kpi_card_ids)

    marketing_gid = ensure_group(mb, "Marketing")
    finance_gid = ensure_group(mb, "Finance")
    set_collection_permissions(mb, coll_ids, marketing_gid, finance_gid)

    print("[provision] done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
