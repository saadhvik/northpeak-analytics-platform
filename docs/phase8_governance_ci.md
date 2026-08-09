# Phase 8 — Governance & CI

*Writing down the contract, and making a machine enforce it on every change.*

## What we set out to do

The platform works; this final phase makes it **safe to change**. Three things: a data
dictionary so nobody has to read SQL to know what a column means, role-based access notes
so "Finance sees revenue-recognition, Marketing doesn't" is documented policy, and a CI
gate so nothing merges that breaks a model, a test, or a quality invariant. Plus the
paperwork that makes the repo legible to a newcomer: a launch memo and a front-page README.

## Decisions & rationale

**CI runs the *real* pipeline, on synthetic data.** The pipeline is re-derivable from raw
data by design (Phase 1), so CI exercises that: it rebuilds the warehouse from scratch and
runs the identical `dbt build` + tests + quality suite as production. The only difference is
the *data* — the 3.4M-row TheLook dataset is too large and isn't ours to redistribute, so
CI can't download it on every PR. Instead `ingestion/generate_synthetic.py` emits a small,
deterministic, internally-consistent dataset in the exact 7-table raw schema. This finally
gives the long-declared `Faker` dependency a job, and makes CI fully self-contained — no
secrets, no external fetch, seconds to run.

**The synthetic data has to be *consistent*, not just present.** A random dataset would
fail the tests it's meant to exercise. The generator guarantees referential integrity
(every FK resolves), agreeing order/item statuses, unique keys, valid status values, and
`sale_price ≥ cost ≥ 0` (so per-item margin stays non-negative and `net_margin_rate`
lands in [0, 1]). Everything else — the revenue ladder ordering, recognition ≤ net, the
finance-to-management reconciliation — holds *automatically* because those are structural
properties of the dbt models, not of the data. Verified: **73/73 dbt tests + 25/25 quality
checks pass** on the synthetic warehouse.

**One catalog-name gotcha, pinned down.** `_sources.yml` declares `database: northpeak`,
and DuckDB derives the catalog name from the *filename*. So the CI warehouse file must be
named `northpeak.duckdb` or every source test fails with `Catalog "northpeak" does not
exist`. CI sets `NORTHPEAK_DUCKDB` accordingly; documented so it isn't rediscovered the
hard way.

**Access control is code, and the tricky bit is the implicit group.** Metabase unions
permissions across all of a user's groups, and everyone is implicitly in "All Users". So
the governance requirement is only real if All Users is locked out of the Finance
collection — see [access_control.md](access_control.md). Enforced by the idempotent
`provision_metabase.py`, verified with a Marketing-only user getting `403` on the Finance
cards.

**Versions pinned to what actually passed.** `requirements-dev.txt` pins the exact
dbt-core / dbt-duckdb / duckdb / great-expectations / Faker versions the full loop was
verified green on, so CI isn't surprised by a floating upgrade.

## Results (verified 2026-08-08)

- `generate_synthetic.py` → 4,862 rows across 7 tables (seed=42, deterministic).
- Full CI sequence run locally end-to-end: generate → load → `dbt build` (**73/73**) →
  quality suite (**25/25**, exit 0) → `dbt source freshness` (informational).
- `.github/workflows/ci.yml` runs that sequence on every push/PR to `main`; YAML validated.
- Robustness fix: the quality runner's final summary line is ASCII, so it can't die on a
  non-UTF-8 console after checks have already passed.

## Deliverables

```
ingestion/generate_synthetic.py   # deterministic, consistent synthetic source data
requirements-dev.txt              # pinned full/CI dependency set
.github/workflows/ci.yml          # build · test · quality on every PR
docs/data_dictionary.md           # every mart/staging table: grain, owner, columns
docs/access_control.md            # role-based access + PII notes
docs/launch_memo.md               # the "we're live" memo
README.md                         # recruiter-ready front page
```

## The pipeline is complete

Eight phases: ingest → staging → marts → quality → orchestration → alerting/SLA →
self-serve BI → governance/CI. The result is one governed source of truth that
marketing, ops, and finance can query themselves, that fails loudly when it breaks, and
that can't be changed without a green CI run. See `docs/launch_memo.md` for the business
framing and `README.md` for the tour.
