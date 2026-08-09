"""
NorthPeak Analytics — Phase 1: Extract & Load
=============================================

Loads the raw TheLook eCommerce CSVs into a local DuckDB warehouse under the
`raw` schema. This is deliberately a *thin* EL step: we land the source data
as-is (only adding audit columns), and leave all cleaning/typing to dbt in the
`staging` layer (Phase 2). That separation is what lets us always re-derive the
warehouse from immutable raw data.

Source dataset:
    Kaggle: mustafakeser4/looker-ecommerce-bigquery-dataset
    (a CSV mirror of BigQuery's `bigquery-public-data.thelook_ecommerce`)

Expected CSV files (7 tables):
    distribution_centers.csv
    products.csv
    users.csv
    orders.csv
    order_items.csv
    inventory_items.csv
    events.csv

Usage:
    python ingestion/load_sources.py \
        --source-dir ./raw_data \
        --db ./warehouse/northpeak.duckdb

Idempotent: re-running fully replaces the `raw` tables from the CSVs on disk.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import duckdb

# The 7 TheLook tables we expect to land. Order doesn't matter for raw load,
# but we list them explicitly so a missing file is a loud failure, not a
# silent gap that surfaces three phases later.
EXPECTED_TABLES = [
    "distribution_centers",
    "products",
    "users",
    "orders",
    "order_items",
    "inventory_items",
    "events",
]

RAW_SCHEMA = "raw"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load TheLook CSVs into DuckDB raw layer.")
    p.add_argument(
        "--source-dir",
        default="./raw_data",
        help="Directory containing the TheLook *.csv files.",
    )
    p.add_argument(
        "--db",
        default="./warehouse/northpeak.duckdb",
        help="Path to the DuckDB database file (created if missing).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any expected table CSV is missing (default: warn and skip).",
    )
    return p.parse_args(argv)


def load_table(
    con: duckdb.DuckDBPyConnection,
    csv_path: Path,
    table: str,
    loaded_at: str,
) -> int:
    """Land one CSV into raw.<table>, replacing any prior copy.

    We rely on DuckDB's read_csv_auto for type/sniffing at the *raw* boundary —
    intentionally permissive. Two audit columns are appended:
        _loaded_at    — when this batch was landed (pipeline provenance)
        _source_file  — which file the row came from (lineage/debugging)
    """
    fq = f'{RAW_SCHEMA}."{table}"'
    con.execute(f"DROP TABLE IF EXISTS {fq};")
    con.execute(
        f"""
        CREATE TABLE {fq} AS
        SELECT
            *,
            TIMESTAMP '{loaded_at}'      AS _loaded_at,
            '{csv_path.name}'            AS _source_file
        FROM read_csv_auto(
            '{csv_path.as_posix()}',
            header = true,
            sample_size = -1            -- scan whole file so types are stable
        );
        """
    )
    (n,) = con.execute(f"SELECT COUNT(*) FROM {fq};").fetchone()
    return n


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source_dir = Path(args.source_dir).resolve()
    db_path = Path(args.db).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        print(f"[load] ERROR: source dir not found: {source_dir}", file=sys.stderr)
        return 2

    loaded_at = dt.datetime.utcnow().replace(microsecond=0).isoformat(sep=" ")

    con = duckdb.connect(str(db_path))
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA};")

    print(f"[load] source : {source_dir}")
    print(f"[load] target : {db_path} (schema '{RAW_SCHEMA}')")
    print(f"[load] batch   : _loaded_at = {loaded_at} UTC")
    print("-" * 60)

    total_rows = 0
    loaded, skipped = [], []
    for table in EXPECTED_TABLES:
        csv_path = source_dir / f"{table}.csv"
        if not csv_path.exists():
            msg = f"[load] MISSING: {csv_path.name}"
            if args.strict:
                print(msg + "  (strict mode → abort)", file=sys.stderr)
                return 3
            print(msg + "  (skipping)")
            skipped.append(table)
            continue
        n = load_table(con, csv_path, table, loaded_at)
        total_rows += n
        loaded.append((table, n))
        print(f"[load] OK  raw.{table:<20} {n:>10,} rows")

    print("-" * 60)
    print(f"[load] loaded {len(loaded)} tables, {total_rows:,} rows total")
    if skipped:
        print(f"[load] skipped (no CSV): {', '.join(skipped)}")

    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
