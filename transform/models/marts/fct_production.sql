-- One row per production line and day (clean rows only).
select
    run_id,
    plant_id,
    plant_id || '-' || line_id                    as line_key,
    line_id,
    production_date,
    planned_minutes,
    run_minutes,
    ideal_rate_kg_per_min,
    good_kg,
    scrap_kg,
    good_kg + scrap_kg                            as total_kg,
    ideal_rate_kg_per_min * planned_minutes       as ideal_output_kg   -- OEE denominator
from {{ ref('qc_production_runs') }}
where dq_issue is null
