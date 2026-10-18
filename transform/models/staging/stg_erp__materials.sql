select
    trim(material_id)   as material_id,
    trim(material_name) as material_name,
    trim(category)      as material_category,
    try_cast(contract_price_eur_per_kg as decimal(12, 4)) as contract_price_eur_per_kg
from {{ landing('erp/materials.csv') }}
