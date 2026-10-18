"""Read-only access to the consumption layer."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from .semantic.catalog import Catalog
from .semantic.compiler import CompiledQuery


def _plain(v):
    """Decimals become floats so results serialise to JSON and compare as numbers."""
    return float(v) if isinstance(v, Decimal) else v


class Warehouse:
    """One read-only DuckDB connection; each query runs on its own cursor (thread-safe).

    External access is disabled, so even a compromised query could not read files or URLs,
    and the connection is read-only, so nothing can be written or dropped.
    """

    def __init__(self, path: Path, max_rows: int = 50):
        if not path.exists():
            raise FileNotFoundError(f"warehouse not found at {path}; run `insight build` first")
        self._con = duckdb.connect(str(path), read_only=True, config={"enable_external_access": False, "threads": 2})
        self._lock = threading.Lock()
        self.max_rows = max_rows

    def run(self, q: CompiledQuery) -> list[dict]:
        cur = self._con.cursor()
        try:
            rows = cur.execute(q.sql, q.params).fetchmany(self.max_rows + 1)
            cols = [d[0] for d in cur.description]
        finally:
            cur.close()
        return [dict(zip(cols, (_plain(v) for v in r), strict=True)) for r in rows[: self.max_rows]]

    def scalar(self, sql: str, params: list | None = None):
        cur = self._con.cursor()
        try:
            return cur.execute(sql, params or []).fetchone()[0]
        finally:
            cur.close()

    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        cur = self._con.cursor()
        try:
            res = cur.execute(sql, params or [])
            cols = [d[0] for d in res.description]
            return [dict(zip(cols, r, strict=True)) for r in res.fetchall()]
        finally:
            cur.close()

    def as_of(self) -> date:
        return self.scalar("select max(data_as_of) from quality.dq_summary")

    def data_quality(self) -> list[dict]:
        return self.rows("select source, rows_received, rows_passed, rows_quarantined, pass_rate, issues from quality.dq_summary order by source")

    def dimension_values(self, catalog: Catalog) -> dict[str, set[str]]:
        """Distinct values per (non-time) dimension, used to validate filters and to match names in questions."""
        out: dict[str, set[str]] = {}
        for name, d in catalog.dimensions.items():
            if d.table == "dim_date":
                continue
            if d.table == "fct":
                facts = [f for f, fact in catalog.facts.items() if any(name in m.dimensions for m in catalog.metrics.values() if m.fact == f)]
                values: set[str] = set()
                for f in facts:
                    values |= {str(r["v"]) for r in self.rows(f"select distinct {d.field} as v from marts.{f} where {d.field} is not null")}
                out[name] = values
            else:
                out[name] = {str(r["v"]) for r in self.rows(f"select distinct {d.field} as v from marts.{d.table} where {d.field} is not null")}
        return out

    def columns(self, schema: str = "marts") -> set[str]:
        return {
            f"{r['t']}.{r['c']}"
            for r in self.rows("select table_name as t, column_name as c from information_schema.columns where table_schema = ?", [schema])
        }
