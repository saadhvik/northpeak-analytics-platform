-- Order headers. Key normalization here is timestamps:
--   created_at is TIMESTAMPTZ  -> route through to_utc()
--   shipped/delivered/returned are naive TIMESTAMP already in UTC -> cast straight
-- NULL shipped/delivered/returned are legitimate (order hasn't reached that stage),
-- so we DO NOT coalesce them away.
with source as (
    select * from {{ source('raw_thelook', 'orders') }}
)

select
    cast(order_id as integer)         as order_id,
    cast(user_id as integer)          as user_id,
    trim(status)                      as status,
    trim(gender)                      as gender,
    cast(num_of_item as integer)      as num_of_item,
    {{ to_utc('created_at') }}        as created_at,       -- UTC
    cast(shipped_at as timestamp)     as shipped_at,       -- already UTC
    cast(delivered_at as timestamp)   as delivered_at,     -- already UTC
    cast(returned_at as timestamp)    as returned_at,      -- already UTC
    -- derived booleans for convenient filtering downstream
    (status = 'Returned')             as is_returned,
    (status = 'Cancelled')            as is_cancelled
from source
