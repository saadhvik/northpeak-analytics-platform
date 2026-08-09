"""
NorthPeak — synthetic TheLook-shaped data generator (for CI & local demos).

The real pipeline runs on the ~3.4M-row TheLook eCommerce dataset from Kaggle,
which is far too large (and unlicensed for redistribution) to commit. CI, though,
needs *some* data to run `dbt build` + tests + the quality suite on every PR.

This generator emits a small, internally-consistent dataset in the exact 7-table
raw schema `ingestion/load_sources.py` expects, so the identical pipeline runs
end-to-end in seconds with no external download. It is deterministic (fixed seed)
so CI is reproducible.

Consistency guarantees (these are what let every downstream test pass):
  * Referential integrity: products→distribution_centers, orders→users,
    order_items→orders/users/products — every FK resolves.
  * Order and order-item status always agree (as in the real source).
  * sale_price >= product cost >= 0, so per-item margin is non-negative
    (keeps fct_daily_kpis.net_margin_rate in [0, 1]).
  * Unique primary keys; valid status value set; non-negative prices.
  * A mix of all five order statuses and some never-purchased users, so the
    revenue ladder, recognition split, and customer segments are all exercised.

Usage:
    python ingestion/generate_synthetic.py --out-dir ./raw_data
    # then: python ingestion/load_sources.py --source-dir ./raw_data --db ...
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

from faker import Faker

# NorthPeak is an outdoor-gear retailer — theme the catalog to match.
CATEGORIES = [
    "Tents", "Backpacks", "Sleeping Bags", "Jackets", "Footwear", "Climbing",
    "Cookware", "Headlamps", "Water Filtration", "Trekking Poles",
    "Base Layers", "Navigation",
]
DEPARTMENTS = ["Men", "Women"]
BRANDS = ["Summit", "TrailForge", "NorthPeak", "Cascade", "Ridgeline", "Basecamp"]
TRAFFIC_SOURCES = ["Search", "Organic", "Facebook", "Email", "Display"]
BROWSERS = ["Chrome", "Safari", "Firefox", "Edge"]
EVENT_TYPES = ["home", "department", "product", "cart", "purchase"]

# Order status mix. Weighted toward fulfilled orders, with enough of every status
# that the revenue ladder / recognition / refunds are all non-trivial.
STATUS_WEIGHTS = [
    ("Complete", 40),
    ("Shipped", 22),
    ("Processing", 18),
    ("Cancelled", 12),
    ("Returned", 8),
]


def _weighted_statuses(fake: Faker, n: int) -> list[str]:
    pool = []
    for status, w in STATUS_WEIGHTS:
        pool += [status] * w
    return [pool[fake.random_int(0, len(pool) - 1)] for _ in range(n)]


def _ts(d: dt.datetime, tz: bool) -> str:
    s = d.strftime("%Y-%m-%d %H:%M:%S")
    return s + "+00:00" if tz else s


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"[synth]   wrote {path.name:<24} {len(rows):>6,} rows")


def generate(out_dir: Path, *, n_users: int, n_products: int, n_dc: int,
             n_orders: int, n_events: int, seed: int) -> None:
    fake = Faker()
    Faker.seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[synth] generating synthetic TheLook data -> {out_dir} (seed={seed})")

    start = dt.datetime(2022, 1, 1)
    span_days = 720  # ~2 years so multiple months/years exist for trend charts

    # --- distribution_centers -------------------------------------------------
    dc_rows = []
    for i in range(1, n_dc + 1):
        dc_rows.append([i, f"{fake.city()} DC",
                        round(fake.latitude(), 6), round(fake.longitude(), 6)])
    _write(out_dir / "distribution_centers.csv",
           ["id", "name", "latitude", "longitude"], dc_rows)

    # --- products (cost < retail so margin is non-negative) -------------------
    prod_rows = []
    products = {}  # id -> (cost, retail, category, name, brand, department, sku, dc)
    for i in range(1, n_products + 1):
        retail = round(fake.random_int(20, 400) + fake.random.random(), 2)
        cost = round(retail * fake.random.uniform(0.4, 0.7), 2)  # always < retail
        category = CATEGORIES[i % len(CATEGORIES)]
        brand = BRANDS[fake.random_int(0, len(BRANDS) - 1)]
        dept = DEPARTMENTS[fake.random_int(0, 1)]
        name = f"{brand} {category[:-1] if category.endswith('s') else category} {fake.word().title()}"
        sku = fake.bothify("SKU-####-????").upper()
        dc = fake.random_int(1, n_dc)
        products[i] = (cost, retail, category, name, brand, dept, sku, dc)
        prod_rows.append([i, cost, category, name, brand, retail, dept, sku, dc])
    _write(out_dir / "products.csv",
           ["id", "cost", "category", "name", "brand", "retail_price",
            "department", "sku", "distribution_center_id"], prod_rows)

    # --- users ----------------------------------------------------------------
    user_rows = []
    user_gender = {}
    for i in range(1, n_users + 1):
        gender = fake.random_element(["M", "F"])
        user_gender[i] = gender
        created = start - dt.timedelta(days=fake.random_int(0, 400))
        user_rows.append([
            i, fake.first_name(), fake.last_name(), fake.unique.email(),
            fake.random_int(18, 75), gender, fake.state_abbr(), fake.street_address(),
            fake.postcode(), fake.city(), "United States",
            round(fake.latitude(), 6), round(fake.longitude(), 6),
            TRAFFIC_SOURCES[fake.random_int(0, len(TRAFFIC_SOURCES) - 1)],
            _ts(created, tz=True),
        ])
    _write(out_dir / "users.csv",
           ["id", "first_name", "last_name", "email", "age", "gender", "state",
            "street_address", "postal_code", "city", "country", "latitude",
            "longitude", "traffic_source", "created_at"], user_rows)

    # --- orders + order_items (statuses agree; FKs resolve) -------------------
    statuses = _weighted_statuses(fake, n_orders)
    order_rows, item_rows, inv_rows = [], [], []
    item_id = 0
    inv_id = 0
    for oid in range(1, n_orders + 1):
        uid = fake.random_int(1, n_users)
        status = statuses[oid - 1]
        placed = start + dt.timedelta(
            days=fake.random_int(0, span_days),
            hours=fake.random_int(0, 23), minutes=fake.random_int(0, 59),
        )
        # lifecycle timestamps consistent with status
        shipped = delivered = returned = None
        if status in ("Shipped", "Complete", "Returned"):
            shipped = placed + dt.timedelta(days=fake.random_int(1, 3))
        if status in ("Complete", "Returned"):
            delivered = shipped + dt.timedelta(days=fake.random_int(1, 5))
        if status == "Returned":
            returned = delivered + dt.timedelta(days=fake.random_int(1, 14))

        n_items = fake.random_int(1, 3)
        for _ in range(n_items):
            item_id += 1
            inv_id += 1
            pid = fake.random_int(1, n_products)
            cost, retail, cat, pname, brand, dept, sku, dc = products[pid]
            # sale_price between cost and retail (never below cost -> margin >= 0)
            sale_price = round(fake.random.uniform(cost, retail), 2)
            item_rows.append([
                item_id, oid, uid, pid, inv_id, status,
                _ts(placed, tz=True),
                _ts(shipped, tz=True) if shipped else "",
                _ts(delivered, tz=True) if delivered else "",
                _ts(returned, tz=True) if returned else "",
                sale_price,
            ])
            # matching inventory unit
            sold_at = placed if status not in ("Cancelled",) else None
            inv_rows.append([
                inv_id, pid, _ts(placed - dt.timedelta(days=fake.random_int(5, 60)), tz=True),
                _ts(sold_at, tz=True) if sold_at else "", cost, cat, pname, brand,
                retail, dept, sku, dc,
            ])

        order_rows.append([
            oid, uid, status, user_gender[uid], _ts(placed, tz=True),
            _ts(returned, tz=False) if returned else "",
            _ts(shipped, tz=False) if shipped else "",
            _ts(delivered, tz=False) if delivered else "",
            n_items,
        ])

    _write(out_dir / "orders.csv",
           ["order_id", "user_id", "status", "gender", "created_at",
            "returned_at", "shipped_at", "delivered_at", "num_of_item"], order_rows)
    _write(out_dir / "order_items.csv",
           ["id", "order_id", "user_id", "product_id", "inventory_item_id", "status",
            "created_at", "shipped_at", "delivered_at", "returned_at", "sale_price"], item_rows)
    _write(out_dir / "inventory_items.csv",
           ["id", "product_id", "created_at", "sold_at", "cost", "product_category",
            "product_name", "product_brand", "product_retail_price",
            "product_department", "product_sku", "product_distribution_center_id"], inv_rows)

    # --- events ---------------------------------------------------------------
    event_rows = []
    for eid in range(1, n_events + 1):
        uid = fake.random_int(1, n_users) if fake.random.random() > 0.2 else ""  # some anonymous
        created = start + dt.timedelta(days=fake.random_int(0, span_days),
                                       seconds=fake.random_int(0, 86399))
        event_rows.append([
            eid, uid, fake.random_int(1, 10), fake.uuid4(), _ts(created, tz=True),
            fake.ipv4(), fake.city(), fake.state_abbr(), fake.postcode(),
            BROWSERS[fake.random_int(0, len(BROWSERS) - 1)],
            TRAFFIC_SOURCES[fake.random_int(0, len(TRAFFIC_SOURCES) - 1)],
            "/" + fake.uri_path(), EVENT_TYPES[fake.random_int(0, len(EVENT_TYPES) - 1)],
        ])
    _write(out_dir / "events.csv",
           ["id", "user_id", "sequence_number", "session_id", "created_at",
            "ip_address", "city", "state", "postal_code", "browser",
            "traffic_source", "uri", "event_type"], event_rows)

    print("[synth] done.")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Generate synthetic TheLook-shaped CSVs.")
    p.add_argument("--out-dir", default="./raw_data")
    p.add_argument("--n-users", type=int, default=250)
    p.add_argument("--n-products", type=int, default=80)
    p.add_argument("--n-dc", type=int, default=6)
    p.add_argument("--n-orders", type=int, default=600)
    p.add_argument("--n-events", type=int, default=1500)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    generate(
        Path(args.out_dir), n_users=args.n_users, n_products=args.n_products,
        n_dc=args.n_dc, n_orders=args.n_orders, n_events=args.n_events, seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
