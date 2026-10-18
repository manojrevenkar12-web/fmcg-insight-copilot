select
    trim(po_line_id)                     as po_line_id,
    nullif(trim(supplier_id), '')        as supplier_id,
    nullif(trim(material_id), '')        as material_id,
    nullif(trim(plant_id), '')           as plant_id,
    try_cast(order_date as date)         as order_date,
    try_cast(promised_date as date)      as promised_date,
    try_cast(delivered_date as date)     as delivered_date,
    try_cast(ordered_qty_kg as double)   as ordered_kg,
    try_cast(delivered_qty_kg as double) as delivered_kg,
    try_cast(rejected_qty_kg as double)  as rejected_kg,
    try_cast(unit_price as decimal(12, 4)) as unit_price_eur_per_kg,
    upper(trim(currency))                as currency   -- 'eur' and 'EUR' are the same currency
from {{ landing('erp/purchase_orders.csv') }}
