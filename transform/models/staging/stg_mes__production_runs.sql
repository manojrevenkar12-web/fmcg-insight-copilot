select
    trim(run_id)                             as run_id,
    trim(plant_id)                           as plant_id,
    trim(line_id)                            as line_id,
    try_cast(production_date as date)        as production_date,
    try_cast(planned_minutes as double)      as planned_minutes,
    try_cast(run_minutes as double)          as run_minutes,
    try_cast(ideal_rate_kg_per_min as double) as ideal_rate_kg_per_min,
    try_cast(good_kg as double)              as good_kg,
    try_cast(scrap_kg as double)             as scrap_kg
from {{ landing('mes/production_runs.csv') }}
