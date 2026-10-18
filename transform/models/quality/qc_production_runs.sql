with ranked as (
    select *, row_number() over (partition by run_id order by run_id) as copy_no
    from {{ ref('stg_mes__production_runs') }}
)
select
    r.* exclude (copy_no),
    case
        when r.copy_no > 1                                    then 'duplicate_run'
        when p.plant_id is null                               then 'unknown_plant'
        when r.production_date is null                        then 'invalid_date'
        when r.run_minutes < 0 or r.run_minutes > r.planned_minutes then 'run_exceeds_plan'
        when r.good_kg < 0 or r.scrap_kg < 0                  then 'negative_quantity'
    end as dq_issue
from ranked r
left join {{ ref('stg_erp__plants') }} p using (plant_id)
