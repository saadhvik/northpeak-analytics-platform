-- Reconciliation guard: finance's (recognized + processing_deferred) must always
-- equal management net revenue, to the penny. If these two marts ever drift, this
-- test fails loudly in CI. Allow a sub-cent tolerance for float noise.
select
    order_date,
    net_revenue_mgmt,
    recon_check,
    abs(net_revenue_mgmt - recon_check) as diff
from {{ ref('fct_revenue_recognition') }}
where abs(net_revenue_mgmt - recon_check) > 0.01
