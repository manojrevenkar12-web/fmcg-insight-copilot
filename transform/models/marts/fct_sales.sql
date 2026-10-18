select
    s.order_line_id,
    s.order_date,
    s.customer_id,
    c.customer_country                              as country,
    s.sku,
    s.cases,
    s.volume_kg,
    s.gross_revenue_eur,
    s.promo_discount_eur,
    s.gross_revenue_eur - s.promo_discount_eur      as net_revenue_eur,
    s.returned_cases,
    s.promo_discount_eur > 0                        as is_promoted
from {{ ref('qc_sales_order_lines') }} s
join {{ ref('dim_customer') }} c using (customer_id)
where s.dq_issue is null
