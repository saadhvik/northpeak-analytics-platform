# Phase 1 — Ingest & Warehouse

*The "why" behind the first layer, written the way a senior teammate would hand it off.*

## What we set out to do

Stand up the **single source of truth**: a warehouse that holds NorthPeak's source
data, loaded by a repeatable job we can re-run every day. Nothing modelled yet —
just get trustworthy raw data landed in one place we control.

## Decisions & rationale

**Warehouse = DuckDB (local file).** Zero cost, no infra to babysit, and it speaks
real analytical SQL. For a company at NorthPeak's scale (3.4M rows total) an
in-process columnar engine is genuinely enough; we can lift-and-shift the *same dbt
models* to BigQuery/Snowflake later without rewriting business logic. Choosing DuckDB
now is a cost decision, not a toy decision.

**EL, not ETL — land raw first, transform later.** `load_sources.py` copies each CSV
into the `raw` schema essentially untouched. We do **not** clean, rename, or retype
here. Why: the moment you transform-on-load, your warehouse can no longer be
reproduced from source, and every bug becomes archaeology. Keeping a pristine `raw`
layer means we can always blow away everything downstream and rebuild deterministically.
All cleaning lives in dbt `staging` (Phase 2), in version control, tested.

**Two audit columns on every raw table.** We append `_loaded_at` (batch timestamp)
and `_source_file` (lineage). Trivial now, invaluable the first time someone asks
"why did revenue jump on the 14th?" — you can trace a row back to the exact load.

**The warehouse file is a build artifact, not source.** `warehouse/*.duckdb` is
git-ignored. It's rebuilt from the CSVs in ~10 seconds by re-running the loader.
Committing a 160MB binary that changes every run is how repos rot. Source = the CSVs
+ the loader; everything else regenerates.

**Idempotent by design.** The loader `DROP ... CREATE`s each table, so re-running is
safe and always converges to the same state — the property Phase 5's daily Dagster
schedule will depend on.

## What actually loaded (verified 2026-07-18)

| raw table | rows | note |
|---|--:|---|
| distribution_centers | 10 | the 10 fulfilment hubs |
| products | 29,120 | catalog |
| users | 100,000 | customers, 5 traffic sources |
| orders | 125,226 | order header grain |
| order_items | 181,759 | line-item grain (has `sale_price`) |
| inventory_items | 490,705 | stock units |
| events | 2,431,963 | web clickstream (for conversion later) |
| **total** | **3,358,783** | Jan 2019 → Jan 2024 |

## Data-quality reconnaissance (what Phase 2–4 must handle)

I profiled the raw data so we design staging and tests against reality, not hope.
Findings that shape the next phases:

1. **Timestamps are timezone-aware (`TIMESTAMP WITH TIME ZONE`, America/New_York).**
   This is the classic "timezone issue" real source systems carry. Staging must
   **standardize everything to UTC** so daily KPIs don't drift across DST boundaries.
   This is a real decision to record in the metric-definitions doc: *what calendar
   day does an order belong to?*

2. **Lifecycle timestamps are legitimately NULL, and that's not dirt.**
   `orders`: 43,765 NULL `shipped_at`, 81,342 NULL `delivered_at`, 112,696 NULL
   `returned_at`. These are orders that haven't shipped / delivered / been returned —
   expected. Lesson for Phase 4: a blanket `not_null` test here would be *wrong*;
   nullness must be tested **conditionally on status**.

3. **`status` is a 5-value enum** — `Shipped, Complete, Processing, Cancelled,
   Returned`. Perfect candidate for a dbt `accepted_values` test so a new/misspelled
   status fails CI loudly.

4. **Referential integrity is currently clean:** 0 duplicate `order_id`, 0 orphan
   `order_items` (every line ties to an order). We'll still add `unique` +
   `relationships` tests — not because it's broken today, but because tests exist to
   catch the day a source *change* breaks it.

5. **This canonical TheLook copy is fairly clean** (no negative margins, no null
   prices). Real NorthPeak source data won't be. Before Phase 4 we can optionally
   seed a few controlled defects (dupes, a bad price, a timezone-mangled row) so the
   test suite has something real to catch and we can prove the alerts fire.

## How to reproduce

```bash
python ingestion/load_sources.py \
    --source-dir /path/to/thelook_csvs \
    --db ./warehouse/northpeak.duckdb
# --strict  → fail (don't skip) if any of the 7 expected CSVs is missing
```

## Next: Phase 2 — dbt staging

Initialize `dbt-duckdb`, declare the 7 raw tables in `sources.yml` (with freshness
thresholds — the seed of our SLA), and build `stg_*` models that rename to a
consistent convention, cast types, and **convert all timestamps to UTC**. That's
where the reconnaissance above turns into code.
