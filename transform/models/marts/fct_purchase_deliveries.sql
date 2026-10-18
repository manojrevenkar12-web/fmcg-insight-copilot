-- One row per delivered purchase-order line (clean rows only).
select
    po.po_line_id,
    po.supplier_id,
    po.material_id,
    po.plant_id,
    po.order_date,
    po.promised_date,
    po.delivered_date,
    po.ordered_kg,
    po.delivered_kg,
    po.rejected_kg,
    po.delivered_kg - po.rejected_kg                                      as accepted_kg,
    po.unit_price_eur_per_kg,
    m.contract_price_eur_per_kg,
    po.unit_price_eur_per_kg * po.delivered_kg                            as spend_eur,
    (po.unit_price_eur_per_kg - m.contract_price_eur_per_kg) * po.delivered_kg as price_variance_eur,
    po.delivered_date <= po.promised_date                                 as is_on_time,
    po.delivered_kg >= {{ var('in_full_tolerance') }} * po.ordered_kg     as is_in_full,
    (po.delivered_date <= po.promised_date)
        and (po.delivered_kg >= {{ var('in_full_tolerance') }} * po.ordered_kg) as is_otif,
    greatest(datediff('day', po.promised_date, po.delivered_date), 0)     as days_late
from {{ ref('qc_purchase_orders') }} po
join {{ ref('dim_material') }} m using (material_id)
where po.dq_issue is null
