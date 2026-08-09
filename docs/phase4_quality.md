# Phase 4 — Testing & Data Quality

*Proving the numbers are trustworthy — and proving the checks would notice if they weren't.*

## What we set out to do

Add a second, independent layer of data quality on top of dbt's tests, and — the part
most portfolios skip — **demonstrate the suite going red on known-bad data**. A test
suite you've only ever seen pass is not evidence of anything.

## Two complementary layers

| Layer | Tool | Catches | Runs |
|---|---|---|---|
| Relational contract | **dbt tests** (73) | uniqueness, not-null, referential integrity, accepted values, revenue reconciliation | `dbt build` |
| Distribution & value | **Great Expectations** (25) | ranges, value sets, nulls, anomaly bands, cross-column invariants | `quality/run_quality_checks.py` |

They overlap on purpose at the edges but catch different things: dbt is strongest on
*relationships between tables*; GX is strongest on *the shape of values within a
column* (is refund_rate really a proportion? is any daily revenue absurdly large?).

## Decisions & rationale

**Expectations are defined as code (`quality/expectations.py`).** Reviewable in a PR,
diffable, no clicking through a UI. Each expectation maps back to
`docs/metric_definitions.md`, so a definition change and its check move together.

**Cross-column invariants live as SQL, not GX.** GX single-column expectations can't
cleanly say "gmv ≥ gross ≥ net *per row*." Those relational rules are expressed as SQL
that returns violating rows (dbt-singular style) and run in the same pass. Right tool,
right job.

**Anomaly guard with tolerance.** Daily `net_revenue` is expected within a sane band
for **99%** of days (`mostly=0.99`) — flags a data explosion without failing on a
legitimately huge sales day. This is the seed of Phase 8's ">3σ revenue drop" alert.

**Production data is never mutated to test the suite.** The defect demo corrupts
**in-memory copies** and re-runs the identical suite. This proves detection without
risking the warehouse — the honest way to earn trust in a quality gate.

## Results (verified 2026-07-20)

**Real marts — `run_quality_checks.py`: 25/25 checks PASS**
(21 GX expectations across stg_order_items, fct_daily_kpis, dim_customers,
fct_revenue_recognition + 4 cross-column invariant rules).

**Defect demo — `demo_inject_defects.py`: 4/4 injected defects CAUGHT**, each by the
expected check:

| Injected defect | Caught by |
|---|---|
| negative `sale_price` (−42) | `expect_column_values_to_be_between(sale_price)` |
| null `order_date` in daily KPIs | `expect_column_values_to_not_be_null(order_date)` |
| `refund_rate = 1.5` | `expect_column_values_to_be_between(refund_rate)` |
| duplicate `user_id` | `expect_column_values_to_be_unique(user_id)` |

Both scripts exit non-zero on failure, so Phase 5 orchestration and Phase 8 CI can
gate on them.

## What's in this layer

```
quality/
├── expectations.py          # GX suites (as code) + SQL cross-column rules
├── run_quality_checks.py    # validate real marts; exit 1 on any failure
└── demo_inject_defects.py   # corrupt in-memory copies; prove the suite fires
```

## How to run

```bash
pip install great-expectations
python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb        # gate
python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb --json # for orchestration
python quality/demo_inject_defects.py --db ./warehouse/northpeak.duckdb       # demo
```

## Next: Phase 5 — Orchestration

Wrap the whole flow — `load_sources.py` → `dbt build` → `run_quality_checks.py` — in
a Dagster job with a daily schedule, so the warehouse refreshes and self-validates
every morning, with each step observable and individually retryable.
