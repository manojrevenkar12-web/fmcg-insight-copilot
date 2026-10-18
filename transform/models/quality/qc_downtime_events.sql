with ranked as (
    select *, row_number() over (partition by event_id order by event_id) as copy_no
    from {{ ref('stg_mes__downtime_events') }}
)
select
    r.* exclude (copy_no),
    case
        when r.copy_no > 1                     then 'duplicate_event'
        when r.reason is null                  then 'missing_reason'
        when r.started_at is null              then 'invalid_date'
        when r.duration_minutes <= 0           then 'non_positive_duration'
    end as dq_issue
from ranked r
