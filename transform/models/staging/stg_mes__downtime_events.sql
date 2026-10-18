select
    trim(event_id)                        as event_id,
    trim(plant_id)                        as plant_id,
    trim(line_id)                         as line_id,
    try_cast(started_at as timestamp)     as started_at,
    try_cast(duration_minutes as double)  as duration_minutes,
    nullif(trim(reason), '')              as reason
from {{ landing('mes/downtime_events.csv') }}
