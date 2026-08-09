# Phase 3 — Marts (Kimball dimensional model)

*Where staging becomes numbers the business argues about — so we pin the definitions.*

## What we set out to do

Build the dimensional layer: reusable `int_*` business logic, then star-schema
`dim_*` / `fct_*` marts, and the first governed KPI marts. Critically, **agree the
metric math** and encode it exactly once, so "revenue" means one thing everywhere.

## The model DAG

```
staging (7 views)
   │
   ├─ int_order_items_enriched   (line grain + revenue ladder flags/amounts)
   └─ int_orders_enriched        (order grain rollup)
        │
   marts/core
   ├─ dim_customers   (1/customer: lifetime orders, segment, repeat flag)
   ├─ dim_products    (1/product: catalog + lifetime sales)
   └─ fct_orders      (1/order: source of truth for order counts)
        │
   marts/marketing
   └─ fct_daily_kpis           (1/day: revenue ladder, orders, AOV, refund rate)
   marts/finance
   └─ fct_revenue_recognition  (1/day: accrual recognized revenue + reconciliation)
```

## Decisions & rationale

**Encode the revenue ladder once, in `int_order_items_enriched`.** Every revenue
number in the platform is a `SUM()` of a pre-computed column (`net_amount`,
`recognized_amount`, `refund_amount`, …) defined in one model. No dashboard or mart
re-writes `CASE WHEN status = ...` logic — that's how two teams end up with two
"revenues." Change the definition once, everything downstream follows.

**Grain discipline.** Money sums at **line grain** (`sale_price` lives there); orders
and customers are counted at **their own grain** (`fct_orders`, `dim_customers`).
Mixing them is the classic way KPIs silently inflate.

**Two revenues, on purpose — and they reconcile.** Marketing's headline **net
revenue** includes *Processing* (placed, uncancelled orders). Finance's
**recognized revenue** counts only *fulfilled* (Shipped/Complete) sales. The
difference is the Processing bucket, exposed as `processing_deferred` in the finance
mart so the two tie out:
`recognized_revenue + processing_deferred = net_revenue`. A dbt test
(`assert_revenue_reconciles`) fails CI if they ever drift. **This is the one call
Finance still needs to make** — see `docs/metric_definitions.md`.

**Marts are tables, staging/intermediate are views.** BI users hit small,
pre-aggregated tables (`fct_daily_kpis` is 1,818 rows for 5 years); the heavy lifting
happens at build time, not query time.

## Results (verified 2026-07-20)

`dbt build` (full DAG): **5 table marts + 9 view models + 59 tests → PASS=73,
WARN=0, ERROR=0.** Marts reconcile to raw to the dollar:

| Metric (full history, Jan 2019–Jan 2024) | Value |
|---|---:|
| GMV (demand) | $10,827,119 |
| Gross revenue | $9,224,643 |
| **Net revenue (headline)** | **$8,127,337** |
| Recognized revenue (finance) | $5,972,005 |
| Refunds | $1,097,307 |
| AOV | $76.23 |
| Refund rate | 11.9% |
| Net margin rate | 51.9% |
| Purchasing customers | 72,123 |
| Repeat-purchase rate | 33.7% |
| Finance↔mgmt recon max daily diff | $0.00 |

## What's in this layer

```
models/intermediate/
├── int_order_items_enriched.sql   # revenue ladder encoded here (once)
└── int_orders_enriched.sql
models/marts/
├── core/       dim_customers.sql  dim_products.sql  fct_orders.sql  _core_models.yml
├── marketing/  fct_daily_kpis.sql  _marketing_models.yml
└── finance/    fct_revenue_recognition.sql  _finance_models.yml
tests/assert_revenue_reconciles.sql   # finance ties to management, or CI fails
docs/metric_definitions.md            # the agreed math + edge cases (finance sign-off)
```

## Open item for sign-off

**Does the headline "revenue" include Processing (unshipped) orders?** Current
default: yes for management/marketing, no for finance recognition. Swing = ~$2.16M
full-history. If Finance wants one number, we move Processing out of Net. Everything
is built to flip that with a one-line change in `int_order_items_enriched`.

## Next: Phase 4 — Testing & data quality

Layer Great Expectations on top of dbt tests for distribution/statistical checks
(value ranges, freshness of KPI outputs, anomaly bounds), and optionally seed a few
controlled defects to prove the suite and (Phase 6) alerts actually fire.
