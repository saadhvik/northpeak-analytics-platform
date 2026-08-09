# NorthPeak Analytics — Data SLA

**Audience:** marketing, ops, finance (data consumers) and the analytics team (owners).
**Status:** active. **Owner:** Analytics. **Last updated:** 2026-07-20.

This is the promise the business can rely on: when the data is ready, how fresh it
is, and what happens when something breaks.

## The promise

| # | Commitment | Target |
|---|---|---|
| 1 | **Daily freshness** | KPI marts reflect data through the prior day by **07:00 UTC** every day. |
| 2 | **Pipeline start** | Daily refresh kicks off at **06:00 UTC**, leaving 1h of retry headroom before the deadline. |
| 3 | **Staleness alert** | If any source hasn't loaded in **> 26h**, a freshness warning fires; **> 48h** is an error/page. |
| 4 | **Quality gate** | Data is published only if it passes **all dbt tests (73)** and **Great Expectations checks (25)**. A failed gate blocks publication. |
| 5 | **Failure notification** | Any failed pipeline step alerts the analytics on-call within minutes (Slack/console). |
| 6 | **Recovery target** | A failed daily refresh is resolved and re-run by **12:00 UTC** (same day). |

## What "fresh" means

Freshness is measured on the source `_loaded_at` audit column, not on business
timestamps. If the pipeline runs, data is fresh; if it stops, `_loaded_at` ages and
thresholds (26h warn / 48h error) fire automatically via `dbt source freshness`.

## Scope

- **Covered:** the 7 governed marts (`dim_customers`, `dim_products`, `fct_orders`,
  `fct_daily_kpis`, `fct_revenue_recognition`) and the staging layer they depend on.
- **Not covered:** ad-hoc queries against `raw`, or dashboards built on tables
  outside the governed marts. Those carry no freshness or correctness guarantee.

## Severity & response

| Severity | Trigger | Response time | Action |
|---|---|---|---|
| **SEV-2 (page)** | Refresh failed, or data > 48h stale | 30 min | Follow `runbook.md`; comms to stakeholders if unresolved by 07:00. |
| **SEV-3 (warn)** | Data 26–48h stale, or a single non-blocking test warns | Same business day | Investigate, fix before next run. |
| **Info** | Successful run, anomaly flagged but within tolerance | — | No action; logged. |

## Measurement & reporting

- Freshness: `dbt source freshness` (part of the daily job).
- Quality: `quality/run_quality_checks.py` exit status.
- Pipeline health: Dagster run history (success rate, run duration).
- These feed the Phase 8 pipeline-health view (row counts, run status over time).

## Change control

Metric definitions are governed by `docs/metric_definitions.md` and require analytics
+ finance sign-off to change. This SLA is reviewed quarterly or after any SEV-2.
