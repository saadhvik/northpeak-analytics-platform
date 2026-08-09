-- Revenue grain (one row per order line), enriched with product + order context
-- and the canonical revenue flags/amounts from docs/metric_definitions.md.
-- This is the single place the revenue ladder is encoded; everything downstream
-- sums these columns instead of re-deriving CASE logic.
with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select order_id, created_at as order_created_at, user_id as order_user_id
    from {{ ref('stg_orders') }}
),
products as (
    select product_id, product_name, brand, category, department, cost, retail_price
    from {{ ref('stg_products') }}
)

select
    i.order_item_id,
    i.order_id,
    i.user_id,
    i.product_id,
    i.status,
    i.sale_price,

    -- product context
    p.product_name,
    p.brand,
    p.category,
    p.department,
    p.cost                                    as product_cost,

    -- order context (use ORDER created_at as the canonical demand date)
    o.order_created_at,
    cast(o.order_created_at as date)          as order_date,

    -- revenue ladder flags (see metric_definitions.md)
    (i.status <> 'Cancelled')                             as is_gross,
    (i.status not in ('Cancelled','Returned'))            as is_net,
    (i.status = 'Returned')                               as is_refund,
    (i.status in ('Shipped','Complete'))                  as is_recognized,

    -- pre-computed amounts so marts can just SUM()
    case when i.status <> 'Cancelled' then i.sale_price else 0 end                    as gross_amount,
    case when i.status not in ('Cancelled','Returned') then i.sale_price else 0 end   as net_amount,
    case when i.status = 'Returned' then i.sale_price else 0 end                      as refund_amount,
    case when i.status in ('Shipped','Complete') then i.sale_price else 0 end         as recognized_amount,
    -- gross margin on net sales (revenue - cost), only when the sale counts as net
    case when i.status not in ('Cancelled','Returned')
         then i.sale_price - p.cost else 0 end                                        as net_margin_amount
from items i
left join orders o   on i.order_id = o.order_id
left join products p on i.product_id = p.product_id
