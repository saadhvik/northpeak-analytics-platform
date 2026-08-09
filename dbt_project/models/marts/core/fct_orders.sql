-- Order fact: one row per order, the grain for order-level analysis and the
-- source of truth for order counts. Revenue amounts are rolled up from line items.
select
    order_id,
    user_id,
    order_date,
    created_at,
    status,
    is_net_order,
    is_returned,
    is_cancelled,
    item_count,

    gmv_amount,
    gross_amount,
    net_amount,
    refund_amount,
    recognized_amount,
    net_margin_amount,

    shipped_at,
    delivered_at,
    returned_at
from {{ ref('int_orders_enriched') }}
