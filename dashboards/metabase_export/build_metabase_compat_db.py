"""
Build a Metabase-compatible copy of the DuckDB warehouse.

Why this exists
----------------
The community Metabase DuckDB driver (AlexR2D2/metabase_duckdb_driver) bundles
an old DuckDB engine (v0.10.x) that cannot open database files written by a
newer DuckDB (this project's ingestion/dbt pipeline uses the current release).
DuckDB's storage format has been stable since v0.10, but only in the forward
direction — newer engines can always read older files, not the reverse.

So we can't just point Metabase at warehouse/northpeak.duckdb directly. Instead:
  1. Export the live warehouse to Parquet (version-agnostic interchange format).
  2. Re-import it using a pinned old DuckDB CLI binary (v0.10.3, matching the
     driver), which writes the file back out in the old, driver-compatible
     storage format.

Run this any time warehouse/northpeak.duckdb is rebuilt (new ingestion + dbt
build) and you want Metabase's view of the data to catch up:

    python dashboards/metabase_export/build_metabase_compat_db.py

Output: warehouse/metabase_compat/northpeak.duckdb — mounted by
dashboards/metabase_export/docker-compose.yml.
"""

from __future__ import annotations

import platform
import re
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DB = REPO_ROOT / "warehouse" / "northpeak.duckdb"
COMPAT_DIR = REPO_ROOT / "warehouse" / "metabase_compat"
COMPAT_DB = COMPAT_DIR / "northpeak.duckdb"
EXPORT_DIR = COMPAT_DIR / "_export_tmp"

# Pinned to match the community driver's bundled DuckDB engine (v0.10.0 per its
# release notes) — v0.10.3 is a same-storage-format patch release.
OLD_DUCKDB_VERSION = "v0.10.3"
CLI_CACHE_DIR = REPO_ROOT / "dashboards" / "metabase_export" / ".duckdb_cli_cache"

_ASSET_BY_PLATFORM = {
    "Windows": "duckdb_cli-windows-amd64.zip",
    "Linux": "duckdb_cli-linux-amd64.zip",
    "Darwin": "duckdb_cli-osx-universal.zip",
}


def _old_cli_path() -> Path:
    exe_name = "duckdb.exe" if platform.system() == "Windows" else "duckdb"
    cli_path = CLI_CACHE_DIR / OLD_DUCKDB_VERSION / exe_name
    if cli_path.exists():
        return cli_path

    asset = _ASSET_BY_PLATFORM.get(platform.system())
    if asset is None:
        raise RuntimeError(f"No known DuckDB CLI asset for platform {platform.system()}")

    url = f"https://github.com/duckdb/duckdb/releases/download/{OLD_DUCKDB_VERSION}/{asset}"
    cli_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path = cli_path.parent / asset
    print(f"[compat-db] downloading DuckDB CLI {OLD_DUCKDB_VERSION} ...")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(cli_path.parent)
    zip_path.unlink()
    if platform.system() != "Windows":
        cli_path.chmod(cli_path.stat().st_mode | stat.S_IEXEC)
    return cli_path


def _topo_sort_views(schema_sql: str) -> str:
    """Reorder CREATE VIEW statements so dependencies come before dependents.

    duckdb's EXPORT DATABASE writes statements in an order that isn't always
    dependency-safe for views (unlike tables, views aren't materialized, so a
    view referencing another view/table must be created after it). CREATE
    TABLE / CREATE SCHEMA statements are left in place; only CREATE VIEW
    statements are reordered among themselves.
    """
    statements = [s.strip() for s in schema_sql.split(";;") if s.strip()]
    view_stmts, other_stmts = [], []
    names = set()
    for stmt in statements:
        m = re.match(r"CREATE VIEW (\S+)", stmt)
        if m:
            view_stmts.append((m.group(1), stmt))
            names.add(m.group(1))
        else:
            other_stmts.append(stmt)

    # Build dependency edges: view -> views/tables it references, restricted to
    # names we know are views (tables are always available already).
    view_names = {n for n, _ in view_stmts}
    deps = {}
    for name, stmt in view_stmts:
        referenced = set()
        for other in view_names:
            if other == name:
                continue
            # matches "<catalog>.<schema>.<table>" qualified refs, e.g. northpeak.main_staging.stg_orders
            unqualified = other.split(".")[-1]
            if re.search(rf"\.{re.escape(unqualified)}\b", stmt):
                referenced.add(other)
        deps[name] = referenced

    ordered, seen = [], set()

    def visit(n):
        if n in seen:
            return
        seen.add(n)
        for dep in deps.get(n, ()):
            visit(dep)
        ordered.append(n)

    for name, _ in view_stmts:
        visit(name)

    stmt_by_name = dict(view_stmts)
    sorted_views = [stmt_by_name[n] for n in ordered]
    return ";;\n".join(other_stmts + sorted_views) + ";;\n"


def main() -> int:
    if not SOURCE_DB.exists():
        print(f"[compat-db] ERROR: {SOURCE_DB} not found — run ingestion + dbt build first.", file=sys.stderr)
        return 2

    import duckdb  # local import: only the ingestion/dbt venv needs this installed

    if EXPORT_DIR.exists():
        shutil.rmtree(EXPORT_DIR)
    EXPORT_DIR.mkdir(parents=True)

    print(f"[compat-db] exporting {SOURCE_DB} -> {EXPORT_DIR} (Parquet)")
    con = duckdb.connect(str(SOURCE_DB), read_only=True)
    con.execute(f"EXPORT DATABASE '{EXPORT_DIR.as_posix()}' (FORMAT PARQUET);")
    con.close()

    schema_sql_path = EXPORT_DIR / "schema.sql"
    schema_sql_path.write_text(_topo_sort_views(schema_sql_path.read_text()))

    old_cli = _old_cli_path()
    COMPAT_DIR.mkdir(parents=True, exist_ok=True)
    if COMPAT_DB.exists():
        COMPAT_DB.unlink()

    print(f"[compat-db] importing via DuckDB {OLD_DUCKDB_VERSION} CLI -> {COMPAT_DB}")
    subprocess.run(
        [str(old_cli), str(COMPAT_DB), "-c", f"IMPORT DATABASE '{EXPORT_DIR.as_posix()}';"],
        check=True,
    )

    shutil.rmtree(EXPORT_DIR)
    print(f"[compat-db] done: {COMPAT_DB}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
