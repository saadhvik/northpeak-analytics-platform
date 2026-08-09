# NorthPeak Metric Definitions

**Status:** proposed — pending sign-off from Finance.
**Owner:** Analytics. **Last updated:** 2026-07-20.

This is the contract. Every number in the BI layer resolves to a definition here.
The whole point of the platform is that "revenue" means *one* thing across marketing,
ops, and finance. Where a metric has a defensible alternative, it's called out under
**Edge cases** so we can settle it deliberately rather than discover the disagreement
in a board meeting.

All amounts are in USD. All dates are the **UTC calendar date** of the relevant
timestamp (see Phase 2 — timestamps are normalized to UTC).

---

## The revenue ladder (read this first)

Revenue is layered. Each rung strips out a different thing. Figures below are the
current full-history totals from the warehouse, for orientation.

| Rung | Definition | Includes statuses | Full-history $ |
|---|---|---|---:|
| **GMV / demand** | Everything customers tried to buy | all 5 | 10,827,119 |
| **Gross revenue** | Demand minus cancellations | not Cancelled | 9,224,643 |
| **Net revenue** *(headline)* | Gross minus returns | not Cancelled, not Returned | 8,127,337 |
| **Recognized revenue** *(finance/accrual)* | Only fulfilled (shipped) sales, net of returns | Shipped, Complete | 5,972,005 |

The swing between **Net** and **Recognized** is the **Processing** bucket
(2,155,332) — orders placed but **not yet shipped**. That is the one real judgment
call in this doc; see *Net revenue → Edge cases*.

Grain note: `sale_price` lives on the **order-item** line. Order-item status and
order status always agree in the source (verified: 0 mismatches), so revenue can be
summed at line grain safely.

---

## Metrics

### GMV (Gross Merchandise Value) / Demand
- **Definition:** `SUM(sale_price)` across **all** order items, any status.
- **Use:** top-of-funnel demand, marketing performance before fulfilment reality.
- **Edge cases:** includes items later cancelled or returned — it is *not* money
  earned. Never report GMV as "revenue."

### Gross revenue
- **Definition:** `SUM(sale_price) WHERE status <> 'Cancelled'`.
- **Use:** demand that made it past cancellation; numerator for refund rate.

### Net revenue  *(the headline "revenue")*
- **Definition:** `SUM(sale_price) WHERE status NOT IN ('Cancelled','Returned')`.
- **Rationale:** excludes cancellations (never fulfilled) and returns (refunded).
  Includes **Processing** — treats a placed, uncancelled order as revenue.
- **Use:** the default "revenue" in daily KPIs and marketing/exec dashboards.
- **Edge cases — THE decision for Finance:**
  - **Processing (2.16M):** management view counts it (order is committed);
    strict accrual accounting would **not** recognize it until shipment. If Finance
    wants the headline to equal recognized revenue, move Processing out of Net.
    Current default: **Net includes Processing.**
  - Partial returns: source models a return at line grain, so a partially returned
    order nets only the returned lines. No special handling needed.

### Recognized revenue  *(finance / accrual)*
- **Definition:** `SUM(sale_price) WHERE status IN ('Shipped','Complete')`.
- **Rationale:** revenue recognized on **fulfilment** (shipment), returns excluded,
  Processing excluded (not yet shipped), Cancelled excluded.
- **Use:** the finance mart (`fct_revenue_recognition`); the number that ties to the
  P&L. Deliberately stricter than Net revenue.

### Refunds
- **Definition:** `SUM(sale_price) WHERE status = 'Returned'` (1,097,307 full history).

### Refund rate
- **Definition:** `refunds / gross_revenue`.
- **Edge cases:** dollar-based by default. A count-based version
  (`returned_items / shipped_items`) can differ materially if returns skew to
  high-value items — we report the dollar version unless Finance asks otherwise.

### Orders (order count)
- **Definition:** distinct `order_id`.
- **Net orders:** distinct `order_id` with status `NOT IN ('Cancelled')`.
- **Edge cases:** count at the **order** grain, never the item grain (a 3-item order
  is one order).

### AOV (Average Order Value)
- **Definition:** `net_revenue / net_orders` over the period.
- **Edge cases:** ratio of period totals, **not** the average of per-order values
  (avoids small-order skew). Denominator excludes cancelled orders so AOV isn't
  deflated by orders that earned nothing.

### Active customers
- **Definition:** distinct `user_id` with ≥1 non-cancelled order whose `created_at`
  falls in the period.
- **Edge cases:** activity is keyed on **order date**, not signup date. A customer
  with only cancelled orders in the period is **not** active.

### Repeat-purchase rate
- **Definition:** share of customers (in period) with ≥2 non-cancelled orders
  lifetime-to-date.
- **Edge cases:** "repeat" is judged on lifetime order count, not in-period count,
  so a loyal customer buying once this month still counts as repeat.

### Category growth %
- **Definition:** `(net_revenue_this_period / net_revenue_prior_period) - 1`, by
  product category.
- **Edge cases:** period-over-period on **net** revenue. New categories (no prior
  period) report as null growth, not infinite.

---

## Conventions

- **Currency:** USD, unrounded in models; rounding is a presentation concern.
- **Dates:** UTC calendar date of the driving timestamp (`orders.created_at` for
  demand/net; fulfilment timestamps for recognized revenue).
- **Grain discipline:** money sums at line grain; order/customer counts at their
  own grain. Mixing grains is the most common way these numbers go wrong.
