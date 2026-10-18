with ranked as (
    select *, row_number() over (partition by order_line_id order by order_line_id) as copy_no
    from {{ ref('stg_oms__sales_order_lines') }}
)
select
    r.* exclude (copy_no),
    case
        when r.copy_no > 1                          then 'duplicate_line'
        when c.customer_id is null                  then 'unknown_customer'
        when p.sku is null                          then 'unknown_sku'
        when r.order_date is null                   then 'invalid_date'
        when r.cases <= 0 or r.returned_cases < 0   then 'negative_quantity'
    end as dq_issue
from ranked r
left join {{ ref('stg_oms__customers') }} c using (customer_id)
left join {{ ref('stg_oms__products') }} p using (sku)
