# Phase 7 — Self-Serve BI

*Putting the numbers in front of marketing, ops, and finance — without letting them
reinvent "revenue."*

## What we set out to do

Give non-technical users a way to explore metrics themselves, so the two analysts
stop being a human API. The catch: self-serve must not mean self-invented
definitions. Both BI surfaces here read the **governed marts**, so every number
inherits `docs/metric_definitions.md` automatically.

## Two BI artifacts

| Artifact | For | Runs |
|---|---|---|
| **`dashboards/northpeak_dashboard.html`** | recruiters / anyone / a quick look | open the file — no server |
| **Metabase** (`dashboards/metabase_export/`) | the "real" self-serve deployment | `docker compose up` |

### The HTML dashboard
`build_dashboard.py` queries the marts and emits one self-contained HTML file: KPI
cards (net revenue, recognized revenue, GMV, AOV, refund rate, repeat rate), a
year-filterable monthly revenue trend (net vs finance-recognized — the gap is the
Processing bucket), orders-by-status, and category / brand / traffic-source
breakdowns. Regenerate after each daily refresh; it's a pure function of the marts.

### Metabase
`docker-compose.yml` + setup guide + `governed_questions.sql`. Users build charts via
the query builder on the marts, or start from the seven governed SQL questions. The
warehouse is mounted **read-only** so BI can never mutate data.

## Decisions & rationale

**Governance by construction, not by policy.** Neither surface exposes `raw` or lets
a user re-write revenue logic in a chart. "Net revenue" was computed once in dbt; the
dashboard and Metabase both just `SUM()` it. That's the whole point of the marts.

**Show both revenues, visibly.** The trend chart plots net revenue against
finance-recognized revenue so the Processing gap is a feature users can see — the
Phase 3 finance decision made legible, not hidden.

**HTML dashboard is reproducible, not hand-drawn.** It's generated from the marts by a
script, so it can be regenerated in CI or after each refresh — no stale screenshots.

**Access control mapped to the requirement.** The Metabase guide lays out Finance vs
Marketing collections (finance sees `fct_revenue_recognition` and customer LTV;
marketing sees `fct_daily_kpis` / `dim_products`) — the "finance sees revenue-rec,
marketing doesn't" mandate, ready to enforce in Phase 8.

## Results (verified 2026-07-20)

- `build_dashboard.py` → `northpeak_dashboard.html` (15 KB, self-contained).
  Embedded governed numbers verified: **net revenue $8,127,337**, AOV **$76.23**,
  repeat rate **33.7%**, 61 months of trend, 12 categories, 10 brands, 5 order
  statuses. Chart.js via CDN; no template placeholders left.
- Metabase compose + driver instructions + 7 governed SQL questions + access-control
  plan written.

## Deliverables

```
dashboards/
├── build_dashboard.py          # marts -> self-contained HTML (reproducible)
├── northpeak_dashboard.html     # the generated dashboard (open in a browser)
└── metabase_export/
    ├── docker-compose.yml       # Metabase over DuckDB (read-only mount)
    ├── README.md                # driver install + connect + governed dashboard + RBAC
    └── governed_questions.sql   # 7 curated questions on the marts
```

## How to run

```bash
# HTML dashboard
python dashboards/build_dashboard.py --db ./warehouse/northpeak.duckdb
open dashboards/northpeak_dashboard.html

# Metabase
cd dashboards/metabase_export && docker compose up -d   # http://localhost:3000
```

## Next: Phase 8 — Governance & CI

The data dictionary (every mart table/column, grain, owner), enforce role-based access
in Metabase, and a GitHub Actions workflow that runs `dbt build` + tests + the quality
suite on every PR — so nothing merges that would break the contract.
