select sku, product_name, brand, product_category, kg_per_case, list_price_eur_per_case from {{ ref('stg_oms__products') }}
