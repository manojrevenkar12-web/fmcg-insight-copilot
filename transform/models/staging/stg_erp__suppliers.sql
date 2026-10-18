select
    trim(supplier_id)   as supplier_id,
    trim(supplier_name) as supplier_name,
    upper(trim(country)) as supplier_country
from {{ landing('erp/suppliers.csv') }}
