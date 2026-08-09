# NorthPeak Access Control

**Status:** governed. **Owner:** Analytics + Data Platform. **Last updated:** 2026-08-08.

Who can see what, and how it's enforced. The guiding rule: **one governed source of
truth, least-privilege on top of it.** Everyone reads the same marts, so nobody can
redefine "revenue" — but not everyone sees every mart.

## Principles

1. **BI reads marts, never raw.** Self-serve users query the governed marts only. Raw
   and staging are Analytics-internal. This keeps definitions consistent and keeps PII
   exposure to the curated dimension columns.
2. **The warehouse is read-only to BI.** Metabase mounts the DuckDB file `:ro`, so a
   dashboard or a stray SQL question can never mutate governed data.
3. **Least privilege by domain.** Finance-sensitive marts (revenue recognition,
   customer LTV) are visible only to Finance; Marketing sees the shared KPIs.
4. **Definitions are code.** Access changes and metric changes both go through a PR that
   CI gates — there is no "quietly grant access in the UI and forget."

## Roles → what they see

| Group | KPIs collection (`fct_daily_kpis`, `dim_products`, order status, repeat rate) | Finance collection (`fct_revenue_recognition`, customer LTV) |
|---|---|---|
| **Administrators** | full | full |
| **Finance** | read | **read** |
| **Marketing** | read | **none** |
| **All Users** (implicit) | read | **none** |

### The subtle part: the implicit "All Users" group

Metabase grants a user the **most-permissive** access across *all* their groups, and
every account is implicitly in the built-in **All Users** group. So restricting the
Marketing group alone would be cosmetic — if All Users still had Finance access, a
Marketing user would inherit it. The provisioning script therefore **locks All Users out
of the Finance collection** and grants Finance access only through the named Finance
group.

This is enforced in code, not clicks: `dashboards/metabase_export/provision_metabase.py`
sets the collection-permission graph and is idempotent. Verified end-to-end with a
Marketing-only test user: `200` on KPI cards, **`403` on the revenue-recognition and
LTV cards** — at both the metadata and the query level.

## PII handling

- Customer identity columns (`first_name`, `last_name`, `email`) live in
  `dim_customers`. They are needed for support/ops lookups but are **not** surfaced on
  any shared dashboard — the governed KPI questions aggregate away from the individual.
- Customer-level financials (`lifetime_net_revenue`) are treated as sensitive: the only
  question exposing them (Top customers by LTV) sits in the restricted **Finance**
  collection.
- The clickstream `events` table carries `ip_address`; it stays in the raw/staging
  layer, out of the BI surface entirely.

## Warehouse-level access (beyond BI)

- **dbt / pipeline** connect read-write (they build staging + marts) but only ever
  create the `staging`/`intermediate`/`marts` schemas — raw is treated as immutable and
  is only appended to by the loader.
- **Analysts** who need raw/staging use a direct DuckDB connection, not the BI tool.

## Production hardening (when this leaves the demo)

- Move authentication to **SSO** and map IdP groups → the Marketing/Finance groups, so
  role membership is managed centrally, not per-user in Metabase.
- Swap the Metabase app DB from H2 to **Postgres** and front the instance with HTTPS.
- When the warehouse moves to BigQuery/Snowflake, enforce the same split with warehouse
  roles + row/column policies, so governance holds even for direct SQL access — the BI
  collection split then mirrors, rather than substitutes for, database-level grants.

See also: [data_dictionary.md](data_dictionary.md) (what each mart holds),
`dashboards/metabase_export/README.md` (how the groups/collections are provisioned).
