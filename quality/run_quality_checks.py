"""
NorthPeak — data quality runner (Great Expectations + relational invariants).

Runs the suites in expectations.py against the DuckDB marts and prints a compact
report. Exits non-zero if anything fails, so orchestration (Phase 5) and CI
(Phase 8) can gate on it.

Usage:
    python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb
    python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb --json
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("TQDM_DISABLE", "1")  # silence GX metric progress bars

import duckdb  # noqa: E402
import great_expectations as gx  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expectations import build_suites, CROSS_COLUMN_RULES  # noqa: E402


def run_suite(con, table: str, expectations: list) -> list[dict]:
    """Validate one table's single-column expectation suite via an ephemeral GX context."""
    df = con.execute(f"select * from {table}").df()
    ctx = gx.get_context(mode="ephemeral")
    ds = ctx.data_sources.add_pandas(f"src_{table.replace('.', '_')}")
    asset = ds.add_dataframe_asset(name=table)
    batch_def = asset.add_batch_definition_whole_dataframe("whole")
    suite = ctx.suites.add(gx.ExpectationSuite(name=f"{table}_suite"))
    for exp in expectations:
        suite.add_expectation(exp)
    vd = ctx.validation_definitions.add(
        gx.ValidationDefinition(data=batch_def, suite=suite, name=f"{table}_vd")
    )
    res = vd.run(batch_parameters={"dataframe": df})
    out = []
    for r in res.results:
        cfg = r["expectation_config"]
        col = cfg["kwargs"].get("column", "")
        out.append({
            "table": table,
            "check": f'{cfg["type"]}({col})',
            "success": bool(r["success"]),
        })
    return out


def run_cross_column(con) -> list[dict]:
    out = []
    for label, table, sql in CROSS_COLUMN_RULES:
        n = con.execute(f"select count(*) from ({sql}) t").fetchone()[0]
        out.append({"table": table, "check": f"[rule] {label}", "success": n == 0,
                    "violations": n})
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./warehouse/northpeak.duckdb")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args(argv)

    con = duckdb.connect(args.db, read_only=True)
    results: list[dict] = []
    for table, exps in build_suites().items():
        results.extend(run_suite(con, table, exps))
    results.extend(run_cross_column(con))
    con.close()

    passed = sum(1 for r in results if r["success"])
    failed = [r for r in results if not r["success"]]

    if args.json:
        import json
        print(json.dumps({"passed": passed, "failed": len(failed), "results": results}, indent=2))
    else:
        print(f"\nNorthPeak data quality — {passed}/{len(results)} checks passed\n" + "-" * 60)
        cur = None
        for r in results:
            if r["table"] != cur:
                cur = r["table"]; print(f"\n{cur}")
            mark = "PASS" if r["success"] else "FAIL"
            extra = f'  ({r.get("violations")} violating rows)' if not r["success"] and "violations" in r else ""
            print(f"  [{mark}] {r['check']}{extra}")
        print("-" * 60)
        # Plain ASCII so the runner never dies on a non-UTF-8 console (e.g. Windows
        # cp1252) at the final print after all checks have already been evaluated.
        print("RESULT:", "ALL PASSED" if not failed else f"{len(failed)} FAILED")

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
