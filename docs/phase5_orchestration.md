# Phase 5 — Orchestration (Dagster)

*Making the pipeline run itself, in order, every day — and stop the moment a step fails.*

## What we set out to do

Turn the three things we've been running by hand — ingest, dbt build, quality gate —
into a single scheduled, observable pipeline. If ingest fails, dbt must not run on
stale data. If quality fails, we must know. That's orchestration's job.

## The asset graph

```
raw_sources ──► dbt_models ──► data_quality
 (EL: CSV→raw)   (dbt build)    (Great Expectations gate)
```

Three Dagster **software-defined assets**, each a stage of the pipeline, wired in a
strict linear dependency. A downstream asset only runs if its upstream succeeded.

## Decisions & rationale

**Assets, not raw ops.** Each stage is modeled as an *asset* — a thing that exists
in the warehouse — rather than an anonymous task. Dagster then tracks
materialization history, lineage, and lets you re-run a single stage. `dbt_models`
declaring `deps=[raw_sources]` is the guarantee that transforms never run on a failed
load.

**Shell out to the same scripts a human runs.** The assets call
`ingestion/load_sources.py`, `dbt build`, and `quality/run_quality_checks.py` — the
exact commands from Phases 1–4. No logic is duplicated into Dagster; it's pure
coordination. Each call checks the return code and **raises on non-zero**, so a
failure marks the step failed, halts downstream steps, and gives Phase 6 something
to alert on.

**Fail-closed quality gate.** `data_quality` runs last and raises if any expectation
fails. A bad refresh stops *before* anyone trusts the dashboards — the pipeline
would rather serve yesterday's good data than today's broken data.

**Daily schedule tied to the SLA.** The `daily_refresh` job runs at **06:00 UTC**
(`0 6 * * *`), giving an hour of headroom before the 07:00 SLA deadline (see
`docs/SLA.md`, Phase 6) for retries if a step is slow or flaky.

**Config by env var.** Warehouse path, source dir, and repo root come from
`NORTHPEAK_DB` / `NORTHPEAK_SOURCE_DIR` / `NORTHPEAK_HOME`, so the same definitions
run locally, in the sandbox, and in CI without edits.

## Results (verified 2026-07-20)

Definitions validate, and every asset executed through the Dagster engine to
`RUN_SUCCESS`:

| Asset | Result |
|---|---|
| `raw_sources` | RUN_SUCCESS — 3,358,783 rows loaded across 7 raw tables |
| `dbt_models` | RUN_SUCCESS — dbt build PASS=73, ERROR=0 |
| `data_quality` | RUN_SUCCESS — 25/25 quality checks passed |

Graph wiring confirmed: `raw_sources → dbt_models → data_quality`, one job
(`daily_refresh`), one schedule (`daily_refresh_6am`, `0 6 * * *` UTC).

## How to run

```bash
pip install dagster dagster-webserver
export NORTHPEAK_HOME=$(pwd)
export NORTHPEAK_DB=./warehouse/northpeak.duckdb
export NORTHPEAK_SOURCE_DIR=/path/to/thelook_csvs

# Interactive UI (lineage, run history, manual triggers) at localhost:3000
dagster dev -f orchestration/dagster_defs.py

# Headless full run
dagster asset materialize -f orchestration/dagster_defs.py --select '*'
```

## Next: Phase 6 — Alerting & SLA

Attach failure hooks to the job so a failed step posts to Slack/email, and write the
formal `SLA.md` (refresh by 07:00, freshness alert if >26h stale) plus a runbook for
what to do when the pipeline goes red.
