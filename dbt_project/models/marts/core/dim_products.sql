-- Product dimension: catalog attributes + lifetime sales performance.
with products as (
    select * from {{ ref('stg_products') }}
),
sales as (
    select
        product_id,
        count(*) filter (where is_net)      as units_sold_net,
        sum(net_amount)                     as net_revenue,
        sum(net_margin_amount)              as net_margin,
        sum(refund_amount)                  as refunds
    from {{ ref('int_order_items_enriched') }}
    group by product_id
)

select
    p.product_id,
    p.product_name,
    p.brand,
    p.category,
    p.department,
    p.sku,
    p.cost,
    p.retail_price,
    p.unit_margin,
    p.distribution_center_id,

    coalesce(s.units_sold_net, 0)           as units_sold_net,
    coalesce(s.net_revenue, 0)              as net_revenue,
    coalesce(s.net_margin, 0)               as net_margin,
    coalesce(s.refunds, 0)                  as refunds
from products p
left join sales s on p.product_id = s.product_id
