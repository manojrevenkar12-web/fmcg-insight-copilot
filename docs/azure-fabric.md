# Running this on Azure / Microsoft Fabric

This repository runs locally on DuckDB so anyone can build and test it in a minute. The design
maps one-to-one onto an enterprise Azure / Fabric estate. **This is a design mapping, not a
deployment that has been tested** — the table says what would change and what stays the same.

| Layer here | Azure / Fabric equivalent | What changes |
|---|---|---|
| `data/landing/` raw CSV extracts + load manifest | OneLake / ADLS Gen2 landing zone, filled by Data Factory or Fabric pipelines | `landing()` macro reads from the lake path instead of local files |
| dbt staging → quality → marts (dbt-duckdb) | Same dbt project on `dbt-fabric`, `dbt-synapse` or `dbt-databricks` | Adapter and profile; the SQL models are standard SQL except a few DuckDB functions (`try_cast`, `strftime`) |
| `quality.dq_quarantine`, `dq_summary`, dbt tests | Same models, surfaced in Purview data quality / a Power BI DQ page | None — quarantine stays a table |
| Consumption layer (`marts`) | Fabric Warehouse or Lakehouse SQL endpoint | `Warehouse` class gets an ODBC/SQL connection; the compiler emits ANSI SQL with `?` parameters |
| `semantic/metrics.yml` | Stays the source of truth for KPI definitions; Power BI semantic-model measures are generated from it or checked against it in CI | A small exporter to DAX measures (not built yet) |
| BI reports (Qlik / Power BI) | Keep running on the same marts | Power BI can also call `POST /v1/query?format=csv` to get governed KPIs with the same access rules |
| LLM (`LLM_MODE=live`) | Azure OpenAI / Microsoft Foundry deployment in an EU region | Set `OPENAI_BASE_URL` and key from Key Vault |
| ChromaDB knowledge index | Azure AI Search vector index | Swap `KnowledgeIndex` storage; retrieval logic unchanged |
| API (`insight serve`) | Azure Container Apps behind API Management | Container image from this repo's Dockerfile |
| `config/users.yml` API keys | Microsoft Entra ID (OIDC); groups mapped to roles and countries | Replace `current_user` dependency with token validation |
| `/ops/prometheus`, interaction log | Azure Monitor / Application Insights; interaction log in the Lakehouse | Exporters only |

## Governance notes

- **Data sovereignty:** data stays in the EU tenant; only the question, catalog names and
  aggregated results are sent to the model. Raw rows and personal data are never sent.
- **EU AI Act:** a decision-support assistant over internal KPIs is not a high-risk use; the
  transparency duties (users know they are using AI, outputs are explained) are met by the
  answer's "How this was calculated" panel. Decisions stay with named KPI owners.
- **GDPR:** the KPI catalog contains no personal data; the interaction log stores user id,
  question and outcome — retention should follow the company's logging policy.
