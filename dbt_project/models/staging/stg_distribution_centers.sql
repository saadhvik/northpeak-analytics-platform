-- Fulfilment centers. Tiny dimension; just rename + type.
with source as (
    select * from {{ source('raw_thelook', 'distribution_centers') }}
)

select
    cast(id as integer)         as distribution_center_id,
    trim(name)                  as distribution_center_name,
    cast(latitude as double)    as latitude,
    cast(longitude as double)   as longitude
from source
