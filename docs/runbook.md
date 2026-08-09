# NorthPeak Pipeline — Runbook

**When to use:** you got a `NorthPeak pipeline — ERROR` alert, or the 07:00 UTC data
looks stale/wrong. This is the on-call playbook.

## 0. Triage (first 5 minutes)

1. Open Dagster run history (`dagster dev -f orchestration/dagster_defs.py` → UI) and
   find the failed run. Note **which asset** failed — the alert names it:
   `raw_sources`, `dbt_models`, or `data_quality`.
2. Check severity against `SLA.md`. If data is >48h stale or it's before 07:00 with no
   good data, this is **SEV-2** — keep going fast.
3. Read the step logs in Dagster; the failing command and its stderr are captured there.

## 1. If `raw_sources` failed (ingest)

**Symptom:** load step exited non-zero.

- **Missing CSV / bad source dir** (`--strict` abort, "MISSING: …"): confirm the
  source files exist at `NORTHPEAK_SOURCE_DIR`. Restore/refetch the file, then re-run.
- **Malformed CSV / parse error:** inspect the offending file header vs
  `EXPECTED_TABLES` in `ingestion/load_sources.py`. Do **not** hand-edit raw data —
  fix the source feed and re-load.
- **Recovery:** re-materialize just this asset:
  `dagster asset materialize -f orchestration/dagster_defs.py --select raw_sources`
  then let downstream run.

## 2. If `dbt_models` failed (transform/tests)

**Symptom:** `dbt build` exited non-zero. Two sub-cases:

- **A model errored (compilation/SQL):** the log shows the model + SQL error. Fix the
  model in `dbt_project/models/…`, run `dbt build --select <model>+` locally.
- **A test failed (data contract broke):** e.g. `unique`, `not_null`,
  `accepted_values`, or `assert_revenue_reconciles`. This means **upstream data
  changed shape** — a new order status, a duplicate key, a broken join.
  1. Identify the failing test in the log.
  2. Query the offending rows (dbt prints the compiled test SQL).
  3. Decide: is the *data* wrong (fix source / add a cleaning rule in staging) or is
     the *expectation* now outdated (update the test + `metric_definitions.md` with
     sign-off)? Never silence a test to make the run green.
- **Recovery:** after fix, `--select dbt_models` and downstream.

## 3. If `data_quality` failed (GX gate)

**Symptom:** `run_quality_checks.py` exited 1; the alert/log lists the failing check.

- Map the check to the table/column. Common causes:
  - range/`refund_rate` out of [0,1] → a divide or logic bug in a mart.
  - anomaly guard (`net_revenue` band) tripped → either a real data spike (verify with
    the business) or a duplication bug inflating revenue.
  - cross-column rule (e.g. `recognized_revenue <= net_revenue`) → a marts logic
    regression.
- Reproduce locally: `python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb`.
- **Do not publish** by bypassing the gate. Fix the cause; the gate is fail-closed on
  purpose (`SLA.md` #4).

## 4. Communicate

- **SEV-2 unresolved by 07:00 UTC:** post to the stakeholder channel — "NorthPeak KPIs
  delayed, ETA <time>, dashboards show yesterday's data (safe, not wrong)."
- On resolution, post the all-clear and a one-line cause.

## 5. After recovery — always

1. Confirm a clean full run: `dagster asset materialize --select '*'` → all green.
2. Verify freshness recovered: `dbt source freshness`.
3. If this was SEV-2, write a short blameless postmortem (what broke, why, the fix,
   the guard we're adding so it can't recur silently).

## Quick commands

```bash
export NORTHPEAK_HOME=$(pwd) NORTHPEAK_DB=./warehouse/northpeak.duckdb
export NORTHPEAK_SOURCE_DIR=/path/to/thelook_csvs

dagster dev -f orchestration/dagster_defs.py                              # UI + logs
dagster asset materialize -f orchestration/dagster_defs.py --select '*'  # full re-run
python quality/run_quality_checks.py --db $NORTHPEAK_DB                   # quality only
cd dbt_project && dbt build --profiles-dir . && dbt source freshness --profiles-dir .
```

## Escalation

Analytics on-call → analytics lead → data platform owner. Source-system (order feed)
issues escalate to the eng team that owns the commerce backend.
