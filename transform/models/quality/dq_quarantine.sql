-- Rows held back from the consumption layer, with the reason. Reviewed by data owners.
select 'erp.purchase_orders' as source, po_line_id as record_id, dq_issue from {{ ref('qc_purchase_orders') }} where dq_issue is not null
union all
select 'mes.production_runs', run_id, dq_issue from {{ ref('qc_production_runs') }} where dq_issue is not null
union all
select 'mes.downtime_events', event_id, dq_issue from {{ ref('qc_downtime_events') }} where dq_issue is not null
union all
select 'oms.sales_order_lines', order_line_id, dq_issue from {{ ref('qc_sales_order_lines') }} where dq_issue is not null
