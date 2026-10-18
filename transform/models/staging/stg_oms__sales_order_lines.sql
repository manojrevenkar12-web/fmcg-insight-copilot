select
    trim(order_line_id)                         as order_line_id,
    try_cast(order_date as date)                as order_date,
    trim(customer_id)                           as customer_id,
    trim(sku)                                   as sku,
    try_cast(cases as double)                   as cases,
    try_cast(volume_kg as double)               as volume_kg,
    try_cast(gross_revenue_eur as decimal(14, 2)) as gross_revenue_eur,
    try_cast(promo_discount_eur as decimal(14, 2)) as promo_discount_eur,
    try_cast(returned_cases as double)          as returned_cases
from {{ landing('oms/sales_order_lines.csv') }}
