select plant_id, plant_name, plant_country from {{ ref('stg_erp__plants') }}
