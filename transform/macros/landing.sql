{#-
  Read a raw extract from the landing zone. Everything is read as text: typing and
  validation are the staging and quality layers' job, so a malformed value never breaks
  ingestion — it gets quarantined with a reason instead.
-#}
{% macro landing(file) -%}
    read_csv('{{ env_var("LANDING_PATH", "../data/landing") }}/{{ file }}', header = true, all_varchar = true)
{%- endmacro %}
