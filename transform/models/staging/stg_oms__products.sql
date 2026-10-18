select
    trim(sku)          as sku,
    trim(product_name) as product_name,
    trim(brand)        as brand,
    trim(category)     as product_category,
    try_cast(kg_per_case as double)                  as kg_per_case,
    try_cast(list_price_eur_per_case as decimal(12, 2)) as list_price_eur_per_case
from {{ landing('oms/products.csv') }}
