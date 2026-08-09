"""
NorthPeak — defect-injection demo (proves the quality suite actually catches things).

Production data is NEVER touched. This loads the real marts into memory, corrupts
COPIES with realistic defects, and re-runs the same expectation suites to show them
fail. This is how you earn trust in a test suite: demonstrate it going red on
known-bad data, not just green on good data.

Defects injected:
  1. negative sale_price            (bad price feed)          -> range expectation
  2. null order_date in daily KPIs  (broken date parse)       -> not-null expectation
  3. refund_rate = 1.5              (divide-by-zero / logic)  -> [0,1] range expectation
  4. duplicate user_id in customers (fan-out join bug)        -> uniqueness expectation

Usage:
    python quality/demo_inject_defects.py --db ./warehouse/northpeak.duckdb
"""

from __future__ import annotations

import argparse
import os
import sys
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("TQDM_DISABLE", "1")

import duckdb  # noqa: E402
import great_expectations as gx  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from expectations import build_suites  # noqa: E402


def validate_df(df, table, suite_key) -> list[dict]:
    # Rebuild expectations fresh each call: a GX Expectation object may only belong
    # to one suite, so we can't reuse the same instances across baseline/defect runs.
    expectations = build_suites()[suite_key]
    ctx = gx.get_context(mode="ephemeral")
    ds = ctx.data_sources.add_pandas("demo")
    asset = ds.add_dataframe_asset(name=table)
    bd = asset.add_batch_definition_whole_dataframe("whole")
    suite = ctx.suites.add(gx.ExpectationSuite(name="demo"))
    for exp in expectations:
        suite.add_expectation(exp)
    vd = ctx.validation_definitions.add(
        gx.ValidationDefinition(data=bd, suite=suite, name="demo_vd")
    )
    res = vd.run(batch_parameters={"dataframe": df})
    return [
        {"check": f'{r["expectation_config"]["type"]}'
                  f'({r["expectation_config"]["kwargs"].get("column","")})',
         "success": bool(r["success"])}
        for r in res.results
    ]


def report(title, before, after_defect):
    print(f"\n### {title}")
    newly_failing = [b["check"] for b, a in zip(before, after_defect)
                     if b["success"] and not a["success"]]
    for a in after_defect:
        mark = "PASS" if a["success"] else "FAIL"
        print(f"   [{mark}] {a['check']}")
    print(f"   -> defect CAUGHT by: {', '.join(newly_failing) if newly_failing else 'NOTHING (!)'}")
    return bool(newly_failing)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="./warehouse/northpeak.duckdb")
    args = ap.parse_args(argv)
    con = duckdb.connect(args.db, read_only=True)

    print("=" * 60)
    print("DEFECT-INJECTION DEMO — production data untouched (in-memory copies)")
    print("=" * 60)

    caught = []

    # 1. negative sale_price
    k = "main_staging.stg_order_items"
    df = con.execute("select * from main_staging.stg_order_items limit 5000").df()
    df2 = df.copy(); df2.loc[df2.index[0], "sale_price"] = -42.0
    caught.append(report("Defect 1: negative sale_price",
                         validate_df(df, "stg_order_items", k),
                         validate_df(df2, "stg_order_items", k)))

    # 2. null order_date + 3. refund_rate out of range (fct_daily_kpis)
    k = "main_marts.fct_daily_kpis"
    df = con.execute("select * from main_marts.fct_daily_kpis").df()
    d2 = df.copy(); d2.loc[d2.index[0], "order_date"] = None
    caught.append(report("Defect 2: null order_date", validate_df(df, "fct_daily_kpis", k),
                         validate_df(d2, "fct_daily_kpis", k)))
    d3 = df.copy(); d3.loc[d3.index[0], "refund_rate"] = 1.5
    caught.append(report("Defect 3: refund_rate = 1.5", validate_df(df, "fct_daily_kpis", k),
                         validate_df(d3, "fct_daily_kpis", k)))

    # 4. duplicate user_id
    k = "main_marts.dim_customers"
    df = con.execute("select * from main_marts.dim_customers limit 5000").df()
    d4 = df.copy(); d4.loc[d4.index[1], "user_id"] = d4.loc[d4.index[0], "user_id"]
    caught.append(report("Defect 4: duplicate user_id", validate_df(df, "dim_customers", k),
                         validate_df(d4, "dim_customers", k)))

    con.close()
    print("\n" + "=" * 60)
    ok = all(caught)
    print(f"RESULT: {sum(caught)}/{len(caught)} injected defects were caught by the suite",
          "✅" if ok else "❌")
    # exit 0 = the demo succeeded (all defects were caught, as intended)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
