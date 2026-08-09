# Phase 2 — dbt Staging

*Turning raw landings into a clean, typed, tested contract.*

## What we set out to do

Put dbt in charge of transformation. Declare the 7 raw tables as **sources** (with
freshness thresholds that seed our SLA), then build one `stg_*` model per source that
renames to a consistent convention, casts types, and — the headline fix —
**normalizes every timestamp to naive UTC**. Staging is the layer everything
downstream is allowed to touch; nothing reads `raw` directly again.

## Decisions & rationale

**Sources are the tested boundary; staging is the typed contract.** `_sources.yml`
asserts the guarantees about *incoming* data (uniqueness, referential integrity,
`accepted_values` on status, freshness). `_models.yml` re-asserts on the
*transformed* output — deliberately, because a bad `cast` can silently turn values
into NULLs that the source never had. The two layers catch different failure modes.

**Materialize staging as views.** Staging does no aggregation — it's a typed window
on raw. Views cost nothing to store and are always in sync with raw. Tables would
just be stale copies. (Marts, in Phase 3, become tables for BI query speed.)

**One timestamp type everywhere: naive UTC `TIMESTAMP`.** The raw load typed some
columns as `TIMESTAMPTZ` and others as naive `TIMESTAMP`, even though every value is
UTC (`+00:00`). That inconsistency breaks date math and joins downstream. The
`to_utc()` macro routes tz-aware columns through `AT TIME ZONE 'UTC'`; the
already-UTC naive columns are cast straight. Verified: raw instant `09:31:00+00:00`
→ staging `09:31:00`. This is also the decision finance signs off on later —
*"what calendar day does an order belong to?"* is now answerable and consistent.

**Lifecycle NULLs are preserved, not coalesced.** `shipped_at` / `delivered_at` /
`returned_at` stay NULL when an order hasn't reached that stage. We tested this the
right way: `not_null` on `created_at` (must always exist) but **not** on the
lifecycle columns. A blanket `not_null` there would have been a bug.

**Naming convention.** Every primary key becomes `<entity>_id` (`products.id` →
`product_id`), text is `trim()`-ed, `email` is lowercased. Small touches that stop
downstream joins from silently missing on whitespace/case.

## Freshness = the SLA seed

Sources use `_loaded_at` as the freshness field: warn after 26h, error after 48h.
Because `_loaded_at` is stamped at load time, if the daily pipeline stops running,
these thresholds age and fire — exactly the signal Phase 6's alerting will page on.
All 7 sources currently **PASS** freshness.

## Results (verified 2026-07-20)

- `dbt build`: **7 view models + 41 data tests → PASS=48, WARN=0, ERROR=0**
- `dbt source freshness`: **7/7 PASS**
- Row parity raw↔staging: exact on all tables (orders 125,226 · order_items
  181,759 · users 100,000 · events 2,431,963).
- Staging materializes to schema **`main_staging`** (dbt's default
  `<target>_<custom>` naming; the target schema is `main`).

## How to run

```bash
cd dbt_project
export NORTHPEAK_DUCKDB=/path/to/northpeak.duckdb   # optional; defaults to ../warehouse/
dbt build --profiles-dir .            # models + tests
dbt source freshness --profiles-dir . # SLA check
```

## What's in this layer

```
models/staging/
├── _sources.yml    # 7 sources: freshness + uniqueness/relationships/accepted_values
├── _models.yml     # staging contract tests + column docs
├── stg_distribution_centers.sql
├── stg_products.sql          # + unit_margin (retail_price - cost)
├── stg_users.sql             # email lowercased, created_at UTC
├── stg_orders.sql            # UTC timestamps, is_returned / is_cancelled flags
├── stg_order_items.sql       # revenue grain, sale_price
├── stg_inventory_items.sql
└── stg_events.sql            # ~2.4M rows, anonymous user_id nullable
macros/to_utc.sql             # tz-aware -> naive UTC normalization
tests/assert_sale_price_non_negative.sql   # singular test (no dbt_utils dependency)
```

## Next: Phase 3 — marts (Kimball dimensional model)

Build `int_*` intermediate models (enrich orders with items + product/customer
attributes) then `dim_customers`, `dim_products`, `fct_orders`, and the first KPI
mart `fct_daily_kpis` (revenue, orders, AOV). This is where we confront the metric
definitions finance has to agree on — GMV vs net revenue, what counts as an "active"
customer, how returns/cancellations hit revenue.
