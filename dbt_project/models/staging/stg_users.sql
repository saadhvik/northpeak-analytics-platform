-- Customers. Rename id -> user_id, lowercase email, standardize created_at to UTC.
with source as (
    select * from {{ source('raw_thelook', 'users') }}
)

select
    cast(id as integer)          as user_id,
    trim(first_name)             as first_name,
    trim(last_name)              as last_name,
    lower(trim(email))           as email,
    cast(age as integer)         as age,
    trim(gender)                 as gender,
    trim(city)                   as city,
    trim(state)                  as state,
    trim(postal_code)            as postal_code,
    trim(country)                as country,
    cast(latitude as double)     as latitude,
    cast(longitude as double)    as longitude,
    trim(traffic_source)         as traffic_source,
    {{ to_utc('created_at') }}   as created_at   -- UTC
from source
