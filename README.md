# NorthPeak Analytics

**🔗 [Live demo — open the dashboard](https://saadhvik.github.io/northpeak-analytics-platform/)** · [Source on GitHub](https://github.com/saadhvik/northpeak-analytics-platform)

**A complete, governed self-serve analytics platform** for NorthPeak, a ~$40M/yr online
outdoor-gear retailer. One source of truth that marketing, ops, and finance query
themselves — with the definition of every metric baked in, so the number you pull is the
number Finance reports.

Built end-to-end as a modern data stack: **Python EL → DuckDB → dbt → Great Expectations
→ Dagster → Slack/SLA → Metabase → governance + CI.** Eight phases, all shipped and
documented.

> Data: the **TheLook eCommerce** dataset (Kaggle: `mustafakeser4/looker-ecommerce-bigquery-dataset`),
> ~3.4M rows spanning Jan 2019 → Jan 2024, standing in for NorthPeak's production commerce system.

## Architecture

```
Source CSVs ──EL (Python)──► DuckDB (raw) ──dbt──► staging → intermediate → marts
                                                        │
                                     dbt tests + Great Expectations  (quality gate)
                                                        │
                                     Dagster (daily 06:00 UTC) ──► Slack alerts + SLA
                                                        │
                          ┌─────────────────────────────┴───────────────────────────┐
                    HTML dashboard                                          Metabase (self-serve BI)
                 (zero-install, from marts)                          (governed collections + RBAC)

           every change gated by CI:  generate → build → 73 dbt tests → 25 quality checks
```

## Status by phase — all complete

| Phase | Deliverable | State |
|---|---|---|
| **1. Ingest + warehouse** | 7 raw tables in DuckDB (3.36M rows) | ✅ **done** |
| **2. dbt staging** | 7 typed/UTC staging views + sources.yml + tests | ✅ **done** |
| **3. dbt marts** | dims/facts + KPI + finance marts, 73 tests, metric defs | ✅ **done** |
| **4. Testing** | Great Expectations suite (25) + defect-injection demo | ✅ **done** |
| **5. Orchestration** | Dagster asset graph + daily 06:00 schedule | ✅ **done** |
| **6. Alerting + SLA** | failure hook + `alerts.py`, `SLA.md`, `runbook.md` | ✅ **done** |
| **7. BI self-serve** | HTML dashboard + Metabase (governed, RBAC) | ✅ **done** |
| **8. Governance + CI** | data dictionary, access control, GitHub Actions | ✅ **done** |

## What makes this more than a dbt project

- **One governed definition of revenue.** A four-rung revenue ladder (GMV → gross → net →
  recognized) defined once in [`docs/metric_definitions.md`](docs/metric_definitions.md)
  and computed once in dbt. Net revenue **$8.13M**, recognized **$5.97M** — and the
  finance mart *reconciles to the marketing mart to the penny*, asserted on every run.
- **Fails loudly, never silently.** 73 dbt tests + 25 Great Expectations checks + relational
  invariants; a Dagster failure hook pages Slack the instant anything breaks; a written
  [SLA](docs/SLA.md) and [runbook](docs/runbook.md) back it.
- **Real governance, verified.** BI reads marts only; the warehouse is mounted read-only;
  Finance-sensitive marts (revenue recognition, customer LTV) are restricted to Finance —
  enforced through Metabase groups *and* the implicit "All Users" group, proven with a
  test user getting `403` on the Finance cards. See [`docs/access_control.md`](docs/access_control.md).
- **Self-contained CI.** Every PR rebuilds the whole pipeline from scratch on deterministic
  synthetic data (no 3.4M-row download, no secrets) and runs the identical tests + quality
  suite. Nothing merges that breaks the contract.

## Quick start

### Run it on the real dataset

```bash
python -m venv .venv && source .venv/Scripts/activate   # (Windows Git Bash; use bin/activate on *nix)
pip install -r requirements-dev.txt

# 1. Land raw CSVs → DuckDB (idempotent):
python ingestion/load_sources.py --source-dir /path/to/thelook_csvs --db ./warehouse/northpeak.duckdb

# 2. Build + test the warehouse (staging → marts, 73 tests):
cd dbt_project && dbt build --profiles-dir . && cd ..

# 3. Quality gate (Great Expectations + relational invariants):
python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb

# 4. BI: zero-install dashboard, or Metabase
python dashboards/build_dashboard.py            # -> dashboards/northpeak_dashboard.html
#   Metabase: see dashboards/metabase_export/README.md
```

### Run it with no data at all (what CI does)

```bash
pip install -r requirements-dev.txt
python ingestion/generate_synthetic.py --out-dir ./raw_data          # deterministic synthetic source
python ingestion/load_sources.py --source-dir ./raw_data --db ./warehouse/northpeak.duckdb --strict
cd dbt_project && dbt build --profiles-dir . && cd ..
python quality/run_quality_checks.py --db ./warehouse/northpeak.duckdb
```

> The DuckDB file (`warehouse/*.duckdb`) is a **build artifact** — git-ignored, always
> rebuilt from source, never committed. The warehouse file must be named `northpeak.duckdb`
> (its catalog name must match `database: northpeak` in the dbt sources).

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push/PR to `main`:
**generate synthetic data → load → `dbt build` (73 tests) → quality suite (25 checks) →
source freshness.** Because the pipeline is re-derivable from raw data by design, CI
exercises the real thing — just on a small, consistent synthetic fixture. Verified green
end-to-end (73/73 + 25/25).

## Repo layout

```
northpeak-analytics/
├── ingestion/
│   ├── load_sources.py         # Phase 1: Extract & Load → DuckDB raw
│   └── generate_synthetic.py   # Phase 8: deterministic synthetic source (for CI/demos)
├── dbt_project/                # Phases 2-3: staging → intermediate → marts (+ tests)
├── quality/                    # Phase 4: Great Expectations suites + defect-injection demo
├── orchestration/              # Phases 5-6: Dagster assets, schedule, alerting
├── dashboards/
│   ├── build_dashboard.py      # Phase 7: zero-install HTML dashboard from the marts
│   ├── northpeak_dashboard.html
│   └── metabase_export/        # Phase 7: governed Metabase (compose, driver, provisioning)
├── warehouse/                  # DuckDB build artifact (git-ignored)
├── .github/workflows/ci.yml    # Phase 8: build · test · quality on every PR
└── docs/                       # the governance paperwork (see below)
```

## Documentation

| Doc | What it covers |
|---|---|
| [`metric_definitions.md`](docs/metric_definitions.md) | The metric contract — the revenue ladder, every KPI, the edge cases |
| [`data_dictionary.md`](docs/data_dictionary.md) | Every table/column, grain, and owner |
| [`access_control.md`](docs/access_control.md) | Role-based access, PII handling, the "All Users" gotcha |
| [`SLA.md`](docs/SLA.md) · [`runbook.md`](docs/runbook.md) | The freshness/quality promise and the on-call playbook |
| [`launch_memo.md`](docs/launch_memo.md) | The "we're live" memo to the business |
| `phase1`–`phase8` docs | Per-phase design decisions and verified results |
