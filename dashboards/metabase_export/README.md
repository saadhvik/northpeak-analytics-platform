# Metabase Setup — NorthPeak Self-Serve BI

Stands up Metabase over the governed DuckDB marts so marketing, ops, and finance
build their own charts without writing SQL — while every number stays tied to
`docs/metric_definitions.md`.

> **Two BI artifacts ship in this repo.** This Metabase setup is the "production BI"
> story. For a zero-install view, open `dashboards/northpeak_dashboard.html` — a
> self-contained dashboard generated straight from the marts.

## What's here

| File | Purpose |
|---|---|
| `Dockerfile` | Metabase on a **glibc** base with the DuckDB driver working (see gotchas) |
| `docker-compose.yml` | Runs Metabase, mounts the driver + warehouse, persists app DB |
| `build_metabase_compat_db.py` | Rebuilds a driver-compatible copy of the warehouse |
| `provision_metabase.py` | Creates the collections, questions, dashboard & permissions via API |
| `governed_questions.sql` | The seven governed queries (also embedded in the provision script) |

## TL;DR (scripted path)

```bash
# 0. warehouse must exist: python ingestion/load_sources.py … && (cd dbt_project && dbt build)

# 1. driver jar + compat warehouse copy (see gotchas for why the copy is needed)
curl -L -o plugins/duckdb.metabase-driver.jar \
  https://github.com/AlexR2D2/metabase_duckdb_driver/releases/latest/download/duckdb.metabase-driver.jar
python build_metabase_compat_db.py

# 2. start Metabase (first build compiles a glibc image — a few minutes)
docker compose up -d          # http://localhost:3000 — create the admin account

# 3. provision the governed BI layer (collections, questions, dashboard, permissions)
MB_USER=you@example.com MB_PASSWORD='…' python provision_metabase.py
```

---

## Why a driver step is needed

DuckDB isn't a built-in Metabase data source, so we add the community DuckDB driver.
(In a real deployment you'd point Metabase at the warehouse once it lives in
BigQuery/Snowflake, which Metabase supports natively — no driver needed, and none of
the gotchas below apply.)

## Gotchas discovered standing this up (why the Dockerfile & compat script exist)

The community driver is real-but-rough. Three issues had to be solved to get a live
connection; all are now handled by the files in this folder, but they're documented
so the workarounds aren't mistaken for cruft.

1. **The driver's native lib needs glibc; Metabase's image is Alpine (musl).**
   The driver bundles a native DuckDB JDBC library compiled against glibc. On the
   stock `metabase/metabase` (Alpine) image it fails to load (`libstdc++.so.6` /
   `ld-linux-x86-64.so.2` missing). Installing `gcompat`+`libstdc++` gets it to
   *load*, but every call into the engine then dies with an uninformative
   `Invalid Error: No error information` — musl's C++ exception unwinding is
   incompatible with the glibc-built lib across the ABI boundary (reproduced
   directly against the JNI layer, independent of Metabase). **Fix:** `Dockerfile`
   rebuilds Metabase on a genuine glibc base (`eclipse-temurin:11-jre-jammy`),
   copying the app jar out of the official image. (One knock-on: Debian's `su`
   resets `PATH`, so `java` is symlinked into `/usr/local/bin`.)

2. **DuckDB storage-format mismatch.** The driver embeds an old DuckDB engine
   (v0.10.x). Newer DuckDB can read old files but not vice-versa, so it can't open
   `warehouse/northpeak.duckdb` (written by the current DuckDB used in ingestion/dbt).
   **Fix:** `build_metabase_compat_db.py` exports the warehouse to Parquet and
   re-imports it with a pinned v0.10.3 DuckDB CLI, producing
   `warehouse/metabase_compat/northpeak.duckdb` — which is what compose mounts.
   Re-run it whenever the warehouse is rebuilt.

3. **`old_implicit_casting` must be sent explicitly.** The driver errors if the
   connection detail is absent (`Could not convert string '' to BOOL`). The
   provisioning script always sets it to `false`.

---

## Manual steps (if you'd rather click than script)

### 1. Add the DuckDB driver

```bash
mkdir -p plugins
curl -L -o plugins/duckdb.metabase-driver.jar \
  https://github.com/AlexR2D2/metabase_duckdb_driver/releases/latest/download/duckdb.metabase-driver.jar
python build_metabase_compat_db.py   # build the compat warehouse copy
```

### 2. Start Metabase

```bash
docker compose up -d
# wait ~1 min, then open http://localhost:3000 and create the admin account
```

### 3. Connect the warehouse

In **Admin → Databases → Add database**:

- **Type:** DuckDB
- **Database file:** `/data/northpeak.duckdb`  (the compat copy, mounted read-only)
- **Use old_implicit_casting:** leave the box's default (`false`) — but don't leave
  the field empty if editing raw JSON (see gotcha 3).
- Save. Metabase syncs and discovers `main_marts` / `main_staging` / `main_intermediate` / `raw`.

### 4. Build the governed dashboard

Two paths, both governed because they read the marts:

- **Query builder (recommended for non-technical users):** New → Question → pick a
  mart (`fct_daily_kpis`, `dim_products`, `dim_customers`, `fct_orders`) → summarize.
- **Native SQL:** paste the queries from `governed_questions.sql` (KPIs, monthly
  trend, category revenue, repeat rate, finance recognition, order status, top LTV).

Pin the resulting questions to a **NorthPeak KPIs** dashboard.

---

## 5. Governance & access control

`provision_metabase.py` implements this; the model is:

- **Read-only warehouse:** mounted `:ro`, so BI can never mutate governed data.
- **Two collections:** company-wide **NorthPeak KPIs** vs a restricted **Finance**
  (holds `fct_revenue_recognition` and customer-LTV questions).
- **Groups:** `Marketing` and `Finance`. Marketing reads KPIs only; Finance reads both.
- **The subtle part — the built-in "All Users" group.** Metabase grants a user the
  *most permissive* access across all their groups, and everyone is implicitly in
  "All Users". Restricting the Marketing group alone is cosmetic: if All Users still
  has Finance access, a Marketing user inherits it. So the script locks **All Users
  out of the Finance collection** and grants it only via the named Finance group.
  Verified end-to-end: a Marketing-only user gets `200` on KPI cards and `403` on the
  revenue-recognition and LTV cards, at both the metadata and query level.
- **One definition of revenue:** because every question sits on the marts, nobody can
  redefine "net revenue" in a chart — it's computed once in dbt. The provisioned
  headline card reconciles exactly to `docs/metric_definitions.md`
  (net 8,127,337 · recognized 5,972,005 · GMV 10,827,119).

## Production hardening (notes, not required for demo)

- Swap the H2 app DB for **Postgres** (`MB_DB_TYPE=postgres` + a `postgres` service).
  (The compose file already persists the H2 app DB on a named volume so setup
  survives container rebuilds — but H2 is still demo-grade.)
- Front with HTTPS; enable SSO/groups for real access control.
- Schedule Metabase to refresh model caches — and re-run `build_metabase_compat_db.py`
  — after the 06:00 pipeline run.
- Once the warehouse moves to BigQuery/Snowflake, drop the custom image, the compat
  script, and the community driver entirely — those engines are native to Metabase.
