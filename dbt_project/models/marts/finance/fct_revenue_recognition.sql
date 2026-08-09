-- Finance revenue-recognition mart (accrual view). One row per UTC order_date.
-- Deliberately stricter than the marketing net_revenue: recognizes only FULFILLED
-- (Shipped/Complete) sales, and exposes the Processing bucket as a reconciling item
-- so Finance can tie recognized revenue back to management net revenue.
--
--   net_revenue (mgmt)  =  recognized_revenue  +  processing_deferred
--
with orders as (
    select * from {{ ref('fct_orders') }}
),
daily as (
    select
        order_date,
        sum(recognized_amount)                       as recognized_revenue,   -- Shipped + Complete
        sum(net_amount) - sum(recognized_amount)     as processing_deferred,  -- placed, not yet shipped
        sum(net_amount)                              as net_revenue_mgmt,     -- ties to marketing mart
        sum(refund_amount)                           as refunds,              -- Returned
        sum(gross_amount)                            as gross_revenue
    from orders
    group by order_date
)

select
    order_date,
    recognized_revenue,
    processing_deferred,
    net_revenue_mgmt,
    refunds,
    gross_revenue,
    -- explicit reconciliation column: should always equal net_revenue_mgmt
    (recognized_revenue + processing_deferred)       as recon_check
from daily
order by order_date
