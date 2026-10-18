select customer_id, customer_name, channel, customer_country from {{ ref('stg_oms__customers') }}
