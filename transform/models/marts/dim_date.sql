select
    d::date                                   as date_day,
    year(d)                                   as year,
    year(d) || '-Q' || quarter(d)             as quarter,
    strftime(d, '%Y-%m')                      as month,
    strftime(d, '%B')                         as month_name,
    strftime(d, '%G-W%V')                     as iso_week
from range(date '2025-01-01', date '2027-01-01', interval 1 day) t(d)
