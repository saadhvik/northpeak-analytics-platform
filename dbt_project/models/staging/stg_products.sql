-- Product catalog. Rename id -> product_id, keep cost/price for margin logic later.
with source as (
    select * from {{ source('raw_thelook', 'products') }}
)

select
    cast(id as integer)                     as product_id,
    trim(name)                              as product_name,
    trim(brand)                             as brand,
    trim(category)                          as category,
    trim(department)                        as department,
    trim(sku)                               as sku,
    cast(cost as double)                    as cost,
    cast(retail_price as double)            as retail_price,
    -- convenience: gross unit margin, computed once here
    cast(retail_price as double) - cast(cost as double) as unit_margin,
    cast(distribution_center_id as integer) as distribution_center_id
from source
