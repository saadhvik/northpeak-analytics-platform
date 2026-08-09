# Launch Memo — NorthPeak Self-Serve Analytics

**To:** Marketing, Ops, Finance, Leadership
**From:** Analytics
**Date:** 2026-08-08
**Re:** The analytics platform is live — how to get your own numbers

## The short version

You no longer have to file a ticket and wait to find out what happened last week. There is
now **one governed source of truth** for NorthPeak's commerce data that you can explore
yourself — with the definitions of "revenue," "orders," and "customers" baked in, so the
number you pull matches the number Finance reports.

## What "governed" buys you

- **One definition of revenue.** "Net revenue" means exactly one thing, computed once, in
  one place. A chart you build and a chart Finance builds on the same metric will agree —
  because they read the same governed table, not a re-implementation.
- **The revenue ladder is explicit.** GMV (demand) → gross (minus cancellations) → net
  (minus returns) → recognized (fulfilled only, the finance/accrual number). Each rung is
  defined and reconciles to the next. Full-history net revenue is **$8.13M**; recognized is
  **$5.97M**; the $2.16M gap is orders placed but not yet shipped, shown as a reconciling
  item — not hidden.
- **Numbers are fresh and trustworthy.** The pipeline refreshes daily by 07:00 UTC, runs
  100+ automated tests and quality checks every time, and pages us the moment anything
  breaks — so you're never quietly looking at stale or wrong data.

## How to use it

- **No-install dashboard:** open `dashboards/northpeak_dashboard.html` — headline KPIs, a
  year-filterable revenue trend (net vs recognized), orders by status, and category /
  brand / traffic breakdowns. It regenerates from the marts after every refresh, so it's
  never a stale screenshot.
- **Build your own:** Metabase (self-serve BI) over the same governed marts. Pick a table,
  summarize, chart — no SQL required. Setup and the governed starter questions are in
  `dashboards/metabase_export/`.

## Who sees what

Everyone shares the **NorthPeak KPIs** — revenue trend, orders, categories, repeat rate.
The **Finance** view (revenue recognition, customer lifetime value) is restricted to
Finance. This is enforced by role, verified, and documented in
[`access_control.md`](access_control.md) — not a convention we hope people follow.

## What's behind it (for the curious)

A standard modern-data-stack build, end to end: Python ingestion → DuckDB warehouse → dbt
(staging → marts) → Great Expectations quality gate → Dagster orchestration with Slack
alerting and a written SLA → HTML + Metabase BI → a data dictionary, role-based access, and
CI that blocks any change breaking the contract. Eight phases, all documented in `docs/`.

## Where to go

- **The numbers:** the HTML dashboard, or Metabase.
- **What a metric means:** [`metric_definitions.md`](metric_definitions.md).
- **What's in the warehouse:** [`data_dictionary.md`](data_dictionary.md).
- **When something looks off:** [`runbook.md`](runbook.md) — or ping Analytics.

Welcome to self-serve. Go find something out.
