-- NorthPeak — governed "questions" for Metabase.
-- Paste each as a Native SQL question, or let non-technical users build on the marts
-- with the query builder. Every query reads ONLY the governed marts, so results match
-- docs/metric_definitions.md by construction. Schema is main_marts / main_staging.

-- 1) Headline KPIs (full history)
select
    round(sum(net_revenue), 0)                        as net_revenue,
    round(sum(recognized_revenue), 0)                 as recognized_revenue,
    round(sum(gmv), 0)                                as gmv,
    sum(net_orders)                                   as net_orders,
    round(sum(net_revenue) / nullif(sum(net_orders), 0), 2) as aov,
    round(sum(refunds) / nullif(sum(gross_revenue), 0), 4)  as refund_rate
from main_marts.fct_daily_kpis;

-- 2) Monthly net revenue trend (line chart)
select date_trunc('month', order_date) as month,
       round(sum(net_revenue), 0)      as net_revenue,
       round(sum(recognized_revenue),0) as recognized_revenue
from main_marts.fct_daily_kpis
group by 1 order by 1;

-- 3) Net revenue by category (bar)
select category, round(sum(net_revenue), 0) as net_revenue
from main_marts.dim_products
group by 1 order by 2 desc;

-- 4) Repeat-purchase rate
select
    count(*) filter (where lifetime_net_orders >= 1)                              as purchasers,
    count(*) filter (where is_repeat_customer)                                    as repeat_customers,
    round(count(*) filter (where is_repeat_customer)
          / nullif(count(*) filter (where lifetime_net_orders >= 1), 0)::double, 3) as repeat_rate
from main_marts.dim_customers;

-- 5) Finance view: recognized revenue vs deferred (reconciles to net)
select date_trunc('month', order_date) as month,
       round(sum(recognized_revenue), 0)  as recognized,
       round(sum(processing_deferred), 0) as deferred_processing,
       round(sum(refunds), 0)             as refunds
from main_marts.fct_revenue_recognition
group by 1 order by 1;

-- 6) Orders by status (funnel/health)
select status, count(*) as orders
from main_marts.fct_orders group by 1 order by 2 desc;

-- 7) Top customers by lifetime net revenue (guarded for finance-only if needed)
select user_id, city, state, lifetime_net_orders, round(lifetime_net_revenue, 2) as ltv
from main_marts.dim_customers
order by lifetime_net_revenue desc limit 50;
