-- Every staged row, with the first data-quality rule it breaks (null = clean).
-- Marts read only clean rows; broken rows stay visible in dq_quarantine with their reason.
with ranked as (
    select *, row_number() over (partition by po_line_id order by po_line_id) as copy_no
    from {{ ref('stg_erp__purchase_orders') }}
)
select
    r.* exclude (copy_no),
    case
        when r.copy_no > 1                                         then 'duplicate_line'
        when r.supplier_id is null                                 then 'missing_supplier'
        when s.supplier_id is null                                 then 'unknown_supplier'
        when m.material_id is null                                 then 'unknown_material'
        when p.plant_id is null                                    then 'unknown_plant'
        when r.order_date is null or r.promised_date is null
             or r.delivered_date is null                           then 'invalid_date'
        when r.delivered_date > date '{{ var("data_as_of") }}'     then 'delivered_in_future'
        when r.ordered_kg <= 0 or r.delivered_kg < 0
             or r.rejected_kg < 0                                  then 'negative_quantity'
        when r.currency <> 'EUR'                                   then 'unsupported_currency'
    end as dq_issue
from ranked r
left join {{ ref('stg_erp__suppliers') }} s using (supplier_id)
left join {{ ref('stg_erp__materials') }} m using (material_id)
left join {{ ref('stg_erp__plants') }} p using (plant_id)
