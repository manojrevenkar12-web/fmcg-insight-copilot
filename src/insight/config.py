from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Project root: INSIGHT_HOME if set (containers, installed package), else the source checkout.
_checkout = Path(__file__).resolve().parents[2]
ROOT = Path(os.getenv("INSIGHT_HOME") or (_checkout if (_checkout / "semantic").exists() else Path.cwd()))


@dataclass(frozen=True)
class Settings:
    """Configuration from environment variables, validated once at startup."""

    warehouse_path: Path = field(default_factory=lambda: Path(os.getenv("DUCKDB_PATH", ROOT / "warehouse" / "insight.duckdb")))
    app_db_path: Path = field(default_factory=lambda: Path(os.getenv("APP_DB_PATH", ROOT / "warehouse" / "app.sqlite")))
    semantic_path: Path = field(default_factory=lambda: Path(os.getenv("SEMANTIC_PATH", ROOT / "semantic" / "metrics.yml")))
    manifest_path: Path = field(default_factory=lambda: Path(os.getenv("DBT_MANIFEST", ROOT / "transform" / "target" / "manifest.json")))
    knowledge_dir: Path = field(default_factory=lambda: Path(os.getenv("KNOWLEDGE_DIR", ROOT / "knowledge")))
    users_path: Path = field(default_factory=lambda: Path(os.getenv("USERS_PATH", ROOT / "config" / "users.yml")))
    vector_dir: Path = field(default_factory=lambda: Path(os.getenv("VECTOR_DIR", ROOT / "warehouse" / "chroma")))

    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "offline"))
    openai_api_key: str | None = field(default_factory=lambda: os.getenv("OPENAI_API_KEY") or None)
    openai_base_url: str | None = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL") or None)
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4.1-mini"))
    llm_timeout_s: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_S", "25")))
    max_rows: int = field(default_factory=lambda: int(os.getenv("MAX_ROWS", "50")))

    def __post_init__(self) -> None:
        if self.llm_mode not in {"offline", "live"}:
            raise ValueError("LLM_MODE must be 'offline' or 'live'")
        if self.llm_mode == "live" and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_MODE=live")
