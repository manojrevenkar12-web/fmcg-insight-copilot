"""The semantic layer: governed metric and dimension definitions, loaded from semantic/metrics.yml."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

Unit = Literal["eur", "percent", "tonnes", "hours", "eur_per_kg"]
Direction = Literal["up", "down", "neutral"]


class Fact(BaseModel):
    name: str
    label: str
    time_column: str
    country_column: str
    joins: dict[str, str]


class Dimension(BaseModel):
    name: str
    column: str  # "<table alias>.<column>" where alias is a dim table name, "fct" or "dim_date"
    label: str
    synonyms: list[str] = Field(default_factory=list)

    @property
    def table(self) -> str:
        return self.column.split(".", 1)[0]

    @property
    def field(self) -> str:
        return self.column.split(".", 1)[1]


class Metric(BaseModel):
    name: str
    label: str
    fact: str
    expression: str
    unit: Unit
    direction: Direction
    owner: str
    description: str
    synonyms: list[str] = Field(default_factory=list)
    dimensions: list[str]


class Catalog(BaseModel):
    facts: dict[str, Fact]
    dimensions: dict[str, Dimension]
    metrics: dict[str, Metric]

    @model_validator(mode="after")
    def _consistent(self) -> Catalog:
        # The catalog is code: inconsistencies fail at startup, not in front of a user.
        for m in self.metrics.values():
            if m.fact not in self.facts:
                raise ValueError(f"metric {m.name}: unknown fact {m.fact}")
            for d in m.dimensions:
                dim = self.dimensions.get(d)
                if dim is None:
                    raise ValueError(f"metric {m.name}: unknown dimension {d}")
                if dim.table not in ("fct", "dim_date") and dim.table not in self.facts[m.fact].joins:
                    raise ValueError(f"metric {m.name}: dimension {d} needs a join from {m.fact} to {dim.table}")
            if re.search(r";|--|/\*", m.expression):
                raise ValueError(f"metric {m.name}: expression must be a single SQL expression")
        return self

    @classmethod
    def load(cls, path: Path) -> Catalog:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            facts={k: Fact(name=k, **v) for k, v in raw["facts"].items()},
            dimensions={k: Dimension(name=k, **v) for k, v in raw["dimensions"].items()},
            metrics={m["name"]: Metric(**m) for m in raw["metrics"]},
        )

    def describe(self) -> str:
        """Compact catalog description for the LLM planner prompt."""
        lines = ["METRICS (name: label [unit] — description; allowed dimensions)"]
        for m in self.metrics.values():
            lines.append(f"- {m.name}: {m.label} [{m.unit}] — {m.description} Dimensions: {', '.join(m.dimensions)}")
        lines.append("DIMENSIONS")
        for d in self.dimensions.values():
            lines.append(f"- {d.name}: {d.label}")
        return "\n".join(lines)


# ---------------------------------------------------------------- lineage


def load_lineage(manifest_path: Path) -> dict[str, dict]:
    """Model-level lineage from the dbt manifest: for every model, its parents and the landing files it reads."""
    if not manifest_path.exists():
        return {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    nodes = {k: v for k, v in manifest["nodes"].items() if v["resource_type"] == "model"}
    out: dict[str, dict] = {}
    for node in nodes.values():
        files = re.findall(r"landing\('([^']+)'\)", node.get("raw_code", ""))
        out[node["name"]] = {
            "layer": node["fqn"][1] if len(node["fqn"]) > 2 else "",
            "schema": node["schema"],
            "description": node.get("description", ""),
            "parents": sorted(nodes[p]["name"] for p in node["depends_on"]["nodes"] if p in nodes),
            "landing_files": files,
        }
    return out


def trace(model: str, lineage: dict[str, dict]) -> list[dict]:
    """Walk upstream from a model to the landing files: consumption → quality → staging → landing."""
    chain: list[dict] = []
    seen: set[str] = set()
    frontier = [model]
    while frontier:
        nxt: list[str] = []
        for name in frontier:
            if name in seen or name not in lineage:
                continue
            seen.add(name)
            info = lineage[name]
            chain.append({"model": name, "layer": info["layer"], "landing_files": info["landing_files"]})
            nxt.extend(info["parents"])
        frontier = nxt
    return chain
