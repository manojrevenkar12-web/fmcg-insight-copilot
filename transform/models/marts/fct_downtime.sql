select
    event_id,
    plant_id,
    plant_id || '-' || line_id        as line_key,
    line_id,
    started_at::date                  as downtime_date,
    duration_minutes,
    reason                            as downtime_reason,
    reason in ('Planned maintenance', 'Changeover', 'Cleaning') as is_planned
from {{ ref('qc_downtime_events') }}
where dq_issue is null
