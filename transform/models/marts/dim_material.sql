select material_id, material_name, material_category, contract_price_eur_per_kg from {{ ref('stg_erp__materials') }}
