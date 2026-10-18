-- OEE inputs must be physically possible: output never exceeds the ideal for the planned time.
select run_id
from {{ ref('fct_production') }}
where run_minutes > planned_minutes
   or total_kg > ideal_output_kg
   or good_kg < 0
