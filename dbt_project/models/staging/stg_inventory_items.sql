-- Individual stock units. created_at/sold_at are TIMESTAMPTZ -> UTC.
-- sold_at NULL means the unit is still in stock (legitimate null).
with source as (
    select * from {{ source('raw_thelook', 'inventory_items') }}
)

select
    cast(id as integer)                            as inventory_item_id,
    cast(product_id as integer)                    as product_id,
    cast(product_distribution_center_id as integer) as distribution_center_id,
    trim(product_category)                         as product_category,
    trim(product_name)                             as product_name,
    trim(product_brand)                            as product_brand,
    trim(product_department)                       as product_department,
    trim(product_sku)                              as product_sku,
    cast(cost as double)                           as cost,
    cast(product_retail_price as double)           as retail_price,
    {{ to_utc('created_at') }}                     as created_at,   -- UTC
    {{ to_utc('sold_at') }}                        as sold_at       -- UTC (null = unsold)
from source
