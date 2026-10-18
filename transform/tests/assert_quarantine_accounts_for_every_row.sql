-- Nothing is silently dropped: received = passed + quarantined for every source.
select source from {{ ref('dq_summary') }} where rows_received <> rows_passed + rows_quarantined
