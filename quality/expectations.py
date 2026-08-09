"""
NorthPeak — Great Expectations suites (defined as code).

Two kinds of check live here:

  SUITES              single-column GX expectations (nulls, ranges, value sets,
                      distribution). This is what GX is best at and complements
                      dbt's relational tests.

  CROSS_COLUMN_RULES  relational invariants across columns of the same table,
                      expressed as SQL that returns *violating rows* (dbt-singular
                      style). GX single-column suites can't express "gmv >= net"
                      per row cleanly, so we keep these as SQL.

Both are executed by run_quality_checks.py. Every rule ties back to
docs/metric_definitions.md so quality checks and definitions never drift.
"""

import great_expectations as gx

ORDER_STATUSES = ["Shipped", "Complete", "Processing", "Cancelled", "Returned"]
CUSTOMER_SEGMENTS = ["never_purchased", "one_time", "repeat"]


# --- single-column expectation suites, keyed by warehouse table ------------------
def build_suites() -> dict[str, list]:
    e = gx.expectations
    return {
        "main_staging.stg_order_items": [
            e.ExpectColumnValuesToNotBeNull(column="order_item_id"),
            e.ExpectColumnValuesToBeUnique(column="order_item_id"),
            e.ExpectColumnValuesToNotBeNull(column="sale_price"),
            # max observed sale_price is 999; band gives headroom but flags absurd values
            e.ExpectColumnValuesToBeBetween(column="sale_price", min_value=0, max_value=2000),
            e.ExpectColumnValuesToBeInSet(column="status", value_set=ORDER_STATUSES),
        ],
        "main_marts.fct_daily_kpis": [
            e.ExpectColumnValuesToNotBeNull(column="order_date"),
            e.ExpectColumnValuesToBeUnique(column="order_date"),
            e.ExpectColumnValuesToNotBeNull(column="net_revenue"),
            e.ExpectColumnValuesToBeBetween(column="net_revenue", min_value=0, max_value=None),
            e.ExpectColumnValuesToBeBetween(column="net_orders", min_value=0, max_value=None),
            e.ExpectColumnValuesToBeBetween(column="active_customers", min_value=0, max_value=None),
            # rates are proportions
            e.ExpectColumnValuesToBeBetween(column="refund_rate", min_value=0, max_value=1),
            e.ExpectColumnValuesToBeBetween(column="net_margin_rate", min_value=0, max_value=1),
            # distribution / anomaly guard: daily net revenue should sit in a sane band
            # for ~all days (mostly=0.99 tolerates legitimate outlier days).
            e.ExpectColumnValuesToBeBetween(
                column="net_revenue", min_value=0, max_value=250000, mostly=0.99
            ),
        ],
        "main_marts.dim_customers": [
            e.ExpectColumnValuesToNotBeNull(column="user_id"),
            e.ExpectColumnValuesToBeUnique(column="user_id"),
            e.ExpectColumnValuesToBeBetween(column="lifetime_net_orders", min_value=0, max_value=None),
            e.ExpectColumnValuesToBeInSet(column="customer_segment", value_set=CUSTOMER_SEGMENTS),
        ],
        "main_marts.fct_revenue_recognition": [
            e.ExpectColumnValuesToNotBeNull(column="order_date"),
            e.ExpectColumnValuesToBeUnique(column="order_date"),
            e.ExpectColumnValuesToBeBetween(column="recognized_revenue", min_value=0, max_value=None),
        ],
    }


# --- relational invariants (SQL returning violating rows) -----------------------
# Each entry: (label, table, sql). sql must return 0 rows when healthy.
CROSS_COLUMN_RULES = [
    (
        "revenue ladder ordering (gmv >= gross >= net) per day",
        "main_marts.fct_daily_kpis",
        "select order_date from main_marts.fct_daily_kpis "
        "where not (gmv >= gross_revenue and gross_revenue >= net_revenue)",
    ),
    (
        "recognized_revenue <= net_revenue per day",
        "main_marts.fct_daily_kpis",
        "select order_date from main_marts.fct_daily_kpis "
        "where recognized_revenue > net_revenue + 0.01",
    ),
    (
        "active_customers <= net_orders per day",
        "main_marts.fct_daily_kpis",
        "select order_date from main_marts.fct_daily_kpis "
        "where active_customers > net_orders",
    ),
    (
        "finance reconciles to management net revenue",
        "main_marts.fct_revenue_recognition",
        "select order_date from main_marts.fct_revenue_recognition "
        "where abs(net_revenue_mgmt - recon_check) > 0.01",
    ),
]
