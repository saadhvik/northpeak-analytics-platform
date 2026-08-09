-- Customer dimension: one row per user, enriched with lifetime order behavior.
-- Repeat-purchase and active-customer logic anchors on NON-CANCELLED orders
-- (see docs/metric_definitions.md).
with users as (
    select * from {{ ref('stg_users') }}
),
order_facts as (
    select
        user_id,
        count(*) filter (where is_net_order)              as lifetime_net_orders,
        sum(net_amount)                                   as lifetime_net_revenue,
        min(order_date) filter (where is_net_order)       as first_order_date,
        max(order_date) filter (where is_net_order)       as most_recent_order_date
    from {{ ref('int_orders_enriched') }}
    group by user_id
)

select
    u.user_id,
    u.first_name,
    u.last_name,
    u.email,
    u.age,
    u.gender,
    u.city,
    u.state,
    u.country,
    u.traffic_source,
    u.created_at                              as signed_up_at,

    coalesce(f.lifetime_net_orders, 0)        as lifetime_net_orders,
    coalesce(f.lifetime_net_revenue, 0)       as lifetime_net_revenue,
    f.first_order_date,
    f.most_recent_order_date,

    -- classification
    (coalesce(f.lifetime_net_orders, 0) >= 2) as is_repeat_customer,
    case
        when coalesce(f.lifetime_net_orders, 0) = 0 then 'never_purchased'
        when f.lifetime_net_orders = 1           then 'one_time'
        else 'repeat'
    end                                        as customer_segment
from users u
left join order_facts f on u.user_id = f.user_id
