-- Singular test: sale_price must never be negative.
-- Returns offending rows; dbt fails the test if any come back.
select
    order_item_id,
    sale_price
from {{ ref('stg_order_items') }}
where sale_price < 0
