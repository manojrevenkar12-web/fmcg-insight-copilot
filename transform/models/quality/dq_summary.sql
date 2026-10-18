-- One row per source: how many rows arrived, how many passed, how many were quarantined.
with totals as (
    select 'erp.purchase_orders' as source, count(*) as rows_received, count(*) filter (where dq_issue is null) as rows_passed from {{ ref('qc_purchase_orders') }}
    union all
    select 'mes.production_runs', count(*), count(*) filter (where dq_issue is null) from {{ ref('qc_production_runs') }}
    union all
    select 'mes.downtime_events', count(*), count(*) filter (where dq_issue is null) from {{ ref('qc_downtime_events') }}
    union all
    select 'oms.sales_order_lines', count(*), count(*) filter (where dq_issue is null) from {{ ref('qc_sales_order_lines') }}
),
issues as (
    select source, string_agg(dq_issue || ': ' || n, ', ' order by n desc) as issues
    from (select source, dq_issue, count(*) as n from {{ ref('dq_quarantine') }} group by all)
    group by source
)
select
    t.source,
    t.rows_received,
    t.rows_passed,
    t.rows_received - t.rows_passed as rows_quarantined,
    round(t.rows_passed / t.rows_received, 4) as pass_rate,
    coalesce(i.issues, '') as issues,
    date '{{ var("data_as_of") }}' as data_as_of
from totals t
left join issues i using (source)
order by t.source
