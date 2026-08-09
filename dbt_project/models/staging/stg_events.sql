-- Web clickstream (~2.4M rows). Basis for conversion/traffic KPIs in later marts.
-- user_id is a nullable DOUBLE in raw (anonymous sessions) -> cast to nullable int.
with source as (
    select * from {{ source('raw_thelook', 'events') }}
)

select
    cast(id as integer)             as event_id,
    cast(user_id as integer)        as user_id,       -- null = anonymous session
    trim(session_id)                as session_id,
    cast(sequence_number as integer) as sequence_number,
    trim(event_type)                as event_type,
    trim(traffic_source)            as traffic_source,
    trim(browser)                   as browser,
    trim(uri)                       as uri,
    trim(city)                      as city,
    trim(state)                     as state,
    trim(postal_code)               as postal_code,
    ip_address,
    {{ to_utc('created_at') }}      as created_at      -- UTC
from source
