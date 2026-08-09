# NorthPeak Data Dictionary

**Status:** governed. **Owner:** Analytics. **Last updated:** 2026-08-08.

The catalog of what's in the warehouse and who owns it. This is the *structural*
companion to [`metric_definitions.md`](metric_definitions.md): the metric doc defines
what each number *means*; this doc lists every table and column, its grain, and its
steward. If a column here computes a governed metric, its definition is authoritative
in the metric doc — this dictionary points there rather than restating it.

**Layers.** `raw` (immutable landed source) → `staging` (typed/cleaned views) →
`intermediate` (reusable enrichment) → `marts` (the governed, BI-facing tables).
Self-serve BI reads **marts only**. Column-level tests noted below are enforced by
`dbt build` and the quality suite on every run and every PR (Phase 8 CI).

---

## Marts (BI-facing — this is what self-serve users touch)

### `main_marts.fct_daily_kpis`
**Grain:** one row per UTC `order_date`. **Domain owner:** Marketing + Analytics.
**Source of truth for:** the headline daily KPIs and the HTML/Metabase dashboards.

| Column | Type | Description |
|---|---|---|
| `order_date` 🔑 | date | UTC calendar date of the orders. Unique, not null. |
| `total_orders` | bigint | All orders placed that day (any status). |
| `net_orders` | bigint | Orders not Cancelled. See *Orders* in metric defs. |
| `active_customers` | bigint | Distinct customers with a net order that day. ≤ `net_orders`. |
| `gmv` | double | Gross Merchandise Value — demand, all statuses. |
| `gross_revenue` | double | Demand minus cancellations. |
| `net_revenue` | double | **Headline revenue** — gross minus returns. Not null, ≥ 0. |
| `recognized_revenue` | double | Finance/accrual — fulfilled sales only. ≤ `net_revenue`. |
| `refunds` | double | Returned-item value. |
| `net_margin` | double | Net revenue minus cost of net items. |
| `aov` | double | `net_revenue / net_orders` (ratio of period totals). |
| `refund_rate` | double | `refunds / gross_revenue`. In [0, 1]. |
| `net_margin_rate` | double | `net_margin / net_revenue`. In [0, 1]. |

### `main_marts.fct_revenue_recognition`
**Grain:** one row per UTC `order_date`. **Domain owner:** Finance + Analytics.
**Access:** restricted (Finance collection in BI — see [access_control.md](access_control.md)).
**Reconciles to** `fct_daily_kpis` by construction: `recognized + processing_deferred = net_revenue_mgmt` (asserted every run).

| Column | Type | Description |
|---|---|---|
| `order_date` 🔑 | date | UTC calendar date. Unique, not null. |
| `recognized_revenue` | double | Shipped + Complete only (accrual). Not null, ≥ 0. |
| `processing_deferred` | double | Placed-but-not-yet-shipped (reconciling item). |
| `net_revenue_mgmt` | double | Management net revenue — ties to the marketing mart. |
| `refunds` | double | Returned-item value. |
| `gross_revenue` | double | Demand minus cancellations. |
| `recon_check` | double | `recognized_revenue + processing_deferred`; must equal `net_revenue_mgmt`. |

### `main_marts.fct_orders`
**Grain:** one row per order. **Domain owner:** Analytics.
**Source of truth for:** order counts; the base fact both daily marts aggregate from.

| Column | Type | Description |
|---|---|---|
| `order_id` 🔑 | integer | Order primary key. Unique, not null. |
| `user_id` | integer | FK → `dim_customers.user_id`. Not null. |
| `order_date` | date | UTC date the order was placed. |
| `created_at` | timestamp | UTC order-placed timestamp. |
| `status` | varchar | One of Shipped/Complete/Processing/Cancelled/Returned. |
| `is_net_order` | boolean | Status ≠ Cancelled. |
| `is_returned` / `is_cancelled` | boolean | Lifecycle flags. |
| `item_count` | bigint | Line items on the order. |
| `gmv_amount` | double | Line-sum, all statuses. |
| `gross_amount` | double | Line-sum, not Cancelled. |
| `net_amount` | double | Line-sum, not Cancelled/Returned. |
| `refund_amount` | double | Line-sum of Returned. |
| `recognized_amount` | double | Line-sum of Shipped/Complete. |
| `net_margin_amount` | double | Net amount minus cost. |
| `shipped_at` / `delivered_at` / `returned_at` | timestamp | Fulfilment lifecycle (UTC; null until reached). |

### `main_marts.dim_customers`
**Grain:** one row per customer. **Domain owner:** Analytics.
**Access note:** `lifetime_net_revenue` is customer-level financial data; the *Top-LTV*
BI question built on it lives in the restricted Finance collection.

| Column | Type | Description |
|---|---|---|
| `user_id` 🔑 | integer | Customer primary key. Unique, not null. |
| `first_name`, `last_name`, `email` | varchar | Identity (PII — see access_control.md). |
| `age` | integer | |
| `gender` | varchar | |
| `city`, `state`, `country` | varchar | Location. |
| `traffic_source` | varchar | Acquisition channel. |
| `signed_up_at` | timestamp | Account creation (UTC). |
| `lifetime_net_orders` | bigint | Count of net orders, lifetime. ≥ 0. |
| `lifetime_net_revenue` | double | Net revenue, lifetime (LTV). |
| `first_order_date`, `most_recent_order_date` | date | Order-history bounds. |
| `is_repeat_customer` | boolean | ≥ 2 net orders lifetime. |
| `customer_segment` | varchar | never_purchased / one_time / repeat. |

### `main_marts.dim_products`
**Grain:** one row per product. **Domain owner:** Merchandising + Analytics.

| Column | Type | Description |
|---|---|---|
| `product_id` 🔑 | integer | Product primary key. Unique, not null. |
| `product_name`, `brand`, `category`, `department`, `sku` | varchar | Catalog attributes. |
| `cost` | double | Unit cost. |
| `retail_price` | double | List price. |
| `unit_margin` | double | `retail_price − cost`. |
| `distribution_center_id` | integer | FK → distribution center. |
| `units_sold_net` | bigint | Net units sold, lifetime. |
| `net_revenue` | double | Net revenue attributed to the product. |
| `net_margin` | double | Net margin attributed to the product. |
| `refunds` | double | Returned value attributed to the product. |

---

## Staging (typed views on raw — building blocks, not for direct BI use)

One typed/trimmed view per raw table, all timestamps normalized to UTC. **Owner:** Analytics.

| Model | Grain | Key column (unique + not null) |
|---|---|---|
| `stg_orders` | one row per order | `order_id` |
| `stg_order_items` | one row per line item (revenue grain) | `order_item_id` |
| `stg_products` | one row per product | `product_id` |
| `stg_users` | one row per customer | `user_id` |
| `stg_distribution_centers` | one row per fulfilment center | `distribution_center_id` |
| `stg_inventory_items` | one row per stock unit | `inventory_item_id` |
| `stg_events` | one row per web event | `event_id` |

**Intermediate:** `int_order_items_enriched` (line items joined to orders/products with
status-driven revenue amounts) and `int_orders_enriched` (order-grain rollup). Ephemeral
building blocks for the marts; not queried directly.

---

## Raw (immutable source boundary — `raw` schema)

Landed as-is by `ingestion/load_sources.py` from the TheLook eCommerce dataset, with two
audit columns added to every table: `_loaded_at` (batch provenance) and `_source_file`
(lineage). No cleaning happens here — all typing/cleaning is deferred to staging so the
warehouse is always re-derivable. Source-level tests (unique/not-null PKs, the three FK
relationships, status value set, freshness) are defined in `models/staging/_sources.yml`.

Tables: `distribution_centers`, `products`, `users`, `orders`, `order_items`,
`inventory_items`, `events`.

---

## Ownership & change control

- **Analytics** owns the models and this dictionary; changes go through a PR that CI must
  pass (`dbt build` + tests + quality suite — see [phase8_governance_ci.md](phase8_governance_ci.md)).
- **Finance** signs off on the revenue ladder and `fct_revenue_recognition`
  (the one real judgment call is documented in `metric_definitions.md`).
- A metric or column definition is never changed in a BI tool — only here and in the dbt
  models, so every downstream chart moves together.
