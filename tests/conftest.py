"""Shared fixtures: one dbt build into a temporary warehouse per test session."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from insight.agent.engine import InsightEngine, User
from insight.agent.rag import KnowledgeIndex
from insight.cli import build
from insight.config import ROOT, Settings
from insight.semantic.catalog import Catalog, load_lineage
from insight.warehouse import Warehouse


@pytest.fixture(scope="session")
def settings(tmp_path_factory) -> Settings:
    tmp = tmp_path_factory.mktemp("wh")
    os.environ["DUCKDB_PATH"] = str(tmp / "insight.duckdb")
    os.environ["APP_DB_PATH"] = str(tmp / "app.sqlite")
    os.environ["VECTOR_DIR"] = str(tmp / "chroma")
    os.environ["LLM_MODE"] = "offline"
    s = Settings()
    build(s)
    return s


@pytest.fixture(scope="session")
def catalog(settings) -> Catalog:
    return Catalog.load(settings.semantic_path)


@pytest.fixture(scope="session")
def warehouse(settings) -> Warehouse:
    return Warehouse(settings.warehouse_path)


@pytest.fixture(scope="session")
def engine(settings, catalog, warehouse) -> InsightEngine:
    return InsightEngine(catalog, warehouse, KnowledgeIndex(settings.knowledge_dir), load_lineage(settings.manifest_path))


@pytest.fixture
def analyst() -> User:
    return User("analyst", "Analyst", ["analyst"], None)


@pytest.fixture
def nl_user() -> User:
    return User("sales-nl", "Sales NL", ["analyst"], ["NL"])


LANDING = ROOT / "data" / "landing"
__all__ = ["LANDING", "Path"]
