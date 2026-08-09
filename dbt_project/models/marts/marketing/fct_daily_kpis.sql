-- Daily KPI mart (marketing / exec). One row per UTC order_date.
-- Every metric here resolves to docs/metric_definitions.md. Materialized as a table
-- so BI dashboards hit a small, fast, pre-aggregated fact.
with orders as (
    select * from {{ ref('fct_orders') }}
),
daily as (
    select
        order_date,
        count(*)                                    as total_orders,
        count(*) filter (where is_net_order)        as net_orders,
        count(distinct user_id) filter (where is_net_order) as active_customers,

        sum(gmv_amount)                             as gmv,
        sum(gross_amount)                           as gross_revenue,
        sum(net_amount)                             as net_revenue,
        sum(recognized_amount)                      as recognized_revenue,
        sum(refund_amount)                          as refunds,
        sum(net_margin_amount)                      as net_margin
    from orders
    group by order_date
)

select
    order_date,
    total_orders,
    net_orders,
    active_customers,
    gmv,
    gross_revenue,
    net_revenue,
    recognized_revenue,
    refunds,
    net_margin,
    -- ratios (guard divide-by-zero)
    case when net_orders > 0 then net_revenue / net_orders end        as aov,
    case when gross_revenue > 0 then refunds / gross_revenue end       as refund_rate,
    case when net_revenue > 0 then net_margin / net_revenue end        as net_margin_rate
from daily
order by order_date
