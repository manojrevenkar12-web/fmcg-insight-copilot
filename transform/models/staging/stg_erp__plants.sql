select
    trim(plant_id)   as plant_id,
    trim(plant_name) as plant_name,
    upper(trim(country)) as plant_country
from {{ landing('erp/plants.csv') }}
