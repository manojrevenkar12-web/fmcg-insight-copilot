select supplier_id, supplier_name, supplier_country from {{ ref('stg_erp__suppliers') }}
