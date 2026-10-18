"""Command line: build the data platform, serve the API, ask a question, run the evaluation.

insight build           # generate landing data (if missing) and run dbt build
insight serve           # API + web UI on :8000
insight ask "Which supplier had the worst OTIF last quarter?"
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

from .config import ROOT, Settings


def build(settings: Settings) -> None:
    landing = ROOT / "data" / "landing"
    if not (landing / "_load_manifest.json").exists():
        subprocess.run([sys.executable, str(ROOT / "data" / "generate.py")], check=True)
    settings.warehouse_path.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "LANDING_PATH": str(landing), "DUCKDB_PATH": str(settings.warehouse_path)}
    subprocess.run(["dbt", "build", "--profiles-dir", "."], cwd=ROOT / "transform", env=env, check=True)


def make_engine(settings: Settings):
    from .agent.engine import InsightEngine
    from .agent.rag import KnowledgeIndex
    from .semantic.catalog import Catalog, load_lineage
    from .warehouse import Warehouse

    llm = None
    if settings.llm_mode == "live":
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0,
            timeout=settings.llm_timeout_s,
            max_retries=2,
        )
    return InsightEngine(
        Catalog.load(settings.semantic_path),
        Warehouse(settings.warehouse_path, settings.max_rows),
        KnowledgeIndex(settings.knowledge_dir, settings.vector_dir),
        load_lineage(settings.manifest_path),
        llm=llm,
    )


def main() -> None:
    p = argparse.ArgumentParser(prog="insight")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    s = sub.add_parser("serve")
    s.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    s.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    a = sub.add_parser("ask")
    a.add_argument("question")
    a.add_argument("--countries", help="comma-separated, e.g. NL (default: all)")
    args = p.parse_args()
    settings = Settings()

    if args.cmd == "build":
        build(settings)
    elif args.cmd == "serve":
        import uvicorn

        from .api.app import create_app
        from .observability import Observability

        app = create_app(settings, make_engine(settings), Observability(settings.app_db_path))
        uvicorn.run(app, host=args.host, port=args.port, proxy_headers=True)
    elif args.cmd == "ask":
        from .agent.engine import User

        countries = args.countries.split(",") if args.countries else None
        r = make_engine(settings).ask(args.question, User("cli", "CLI", ["analyst"], countries))
        print(r["answer"])
        print(json.dumps({k: r[k] for k in ("status", "query", "verification", "sql")}, indent=2, default=str))


if __name__ == "__main__":
    main()
