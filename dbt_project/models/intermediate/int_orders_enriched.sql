-- Order grain (one row per order): roll item-level revenue amounts up to the order,
-- and attach order header fields. Counts happen at THIS grain (one order = one row).
with orders as (
    select * from {{ ref('stg_orders') }}
),
item_rollup as (
    select
        order_id,
        count(*)                         as item_count,
        sum(sale_price)                  as gmv_amount,
        sum(gross_amount)                as gross_amount,
        sum(net_amount)                  as net_amount,
        sum(refund_amount)               as refund_amount,
        sum(recognized_amount)           as recognized_amount,
        sum(net_margin_amount)           as net_margin_amount
    from {{ ref('int_order_items_enriched') }}
    group by order_id
)

select
    o.order_id,
    o.user_id,
    o.status,
    o.gender,
    o.num_of_item,
    o.created_at,
    cast(o.created_at as date)           as order_date,
    o.shipped_at,
    o.delivered_at,
    o.returned_at,
    o.is_returned,
    o.is_cancelled,
    -- order counts toward "net orders" if it wasn't cancelled
    (o.status <> 'Cancelled')            as is_net_order,

    coalesce(r.item_count, 0)            as item_count,
    coalesce(r.gmv_amount, 0)            as gmv_amount,
    coalesce(r.gross_amount, 0)          as gross_amount,
    coalesce(r.net_amount, 0)            as net_amount,
    coalesce(r.refund_amount, 0)         as refund_amount,
    coalesce(r.recognized_amount, 0)     as recognized_amount,
    coalesce(r.net_margin_amount, 0)     as net_margin_amount
from orders o
left join item_rollup r on o.order_id = r.order_id
