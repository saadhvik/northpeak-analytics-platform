-- Order line items (revenue grain). sale_price is the actual transacted price.
-- All four timestamps here are TIMESTAMPTZ -> normalize to UTC.
with source as (
    select * from {{ source('raw_thelook', 'order_items') }}
)

select
    cast(id as integer)                as order_item_id,
    cast(order_id as integer)          as order_id,
    cast(user_id as integer)           as user_id,
    cast(product_id as integer)        as product_id,
    cast(inventory_item_id as integer) as inventory_item_id,
    trim(status)                       as status,
    cast(sale_price as double)         as sale_price,
    {{ to_utc('created_at') }}         as created_at,     -- UTC
    {{ to_utc('shipped_at') }}         as shipped_at,     -- UTC
    {{ to_utc('delivered_at') }}       as delivered_at,   -- UTC
    {{ to_utc('returned_at') }}        as returned_at     -- UTC
from source
