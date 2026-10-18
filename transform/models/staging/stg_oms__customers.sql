select
    trim(customer_id)   as customer_id,
    trim(customer_name) as customer_name,
    trim(channel)       as channel,
    upper(trim(country)) as customer_country
from {{ landing('oms/customers.csv') }}
