select order_line_id from {{ ref('fct_sales') }} where net_revenue_eur < 0
