# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    LLM_MODE=offline HOST=0.0.0.0 PORT=8000
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY data/generate.py ./data/generate.py
COPY transform ./transform
COPY semantic ./semantic
COPY knowledge ./knowledge
COPY config ./config
COPY web ./web

# Build the demo warehouse into the image (landing extracts → dbt layers → tests).
# In production the warehouse lives in Fabric / Synapse / Databricks and DUCKDB_PATH is replaced by that adapter.
RUN insight build && rm -rf transform/logs \
 && useradd --uid 10001 --create-home app && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["insight", "serve"]
