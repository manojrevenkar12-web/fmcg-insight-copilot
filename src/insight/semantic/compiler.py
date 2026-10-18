"""Compile a validated metric query into parameterised SQL over the consumption layer.

Security model:
  * identifiers (tables, columns, expressions) come only from the governed catalog;
  * every user-supplied value (filter values, dates, allowed countries) is a bound parameter;
  * row-level access is injected here, so no planner — rule-based or LLM — can bypass it;
  * the warehouse connection is read-only with external file access disabled.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .catalog import Catalog, Metric
from .periods import Period


class Filter(BaseModel):
    dimension: str
    values: list[str] = Field(min_length=1, max_length=20)


class MetricQuery(BaseModel):
    """What the planner may ask for. Nothing here is SQL."""

    metrics: list[str] = Field(min_length=1, max_length=4)
    dimensions: list[str] = Field(default_factory=list, max_length=2)
    filters: list[Filter] = Field(default_factory=list, max_length=5)
    period: Period
    compare_previous: bool = False
    order: Literal["desc", "asc"] = "desc"
    limit: int = Field(default=20, ge=1, le=50)

    @field_validator("metrics", "dimensions")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))


class QueryError(ValueError):
    """A query the catalog cannot answer, with a message fit for the end user."""


class CompiledQuery(BaseModel):
    sql: str
    params: list
    columns: list[str]
    fact: str


def validate(q: MetricQuery, catalog: Catalog, known_values: dict[str, set[str]] | None = None) -> list[Metric]:
    metrics = []
    for name in q.metrics:
        m = catalog.metrics.get(name)
        if m is None:
            raise QueryError(f"Unknown metric '{name}'. Available: {', '.join(sorted(catalog.metrics))}.")
        metrics.append(m)
    facts = {m.fact for m in metrics}
    if len(facts) > 1:
        raise QueryError("These metrics come from different processes (e.g. procurement and sales); ask for them separately.")
    allowed = set(metrics[0].dimensions)
    for d in [*q.dimensions, *(f.dimension for f in q.filters)]:
        if d not in catalog.dimensions:
            raise QueryError(f"Unknown dimension '{d}'.")
        if d not in allowed:
            raise QueryError(f"{metrics[0].label} cannot be broken down by {catalog.dimensions[d].label.lower()}. Try: {', '.join(sorted(allowed))}.")
    if known_values:
        for f in q.filters:
            valid = known_values.get(f.dimension)
            if valid is not None:
                unknown = [v for v in f.values if v not in valid]
                if unknown:
                    raise QueryError(f"No {catalog.dimensions[f.dimension].label.lower()} called {', '.join(unknown)}.")
    return metrics


def compile_query(
    q: MetricQuery,
    catalog: Catalog,
    allowed_countries: list[str] | None,
    period: Period | None = None,
    known_values: dict[str, set[str]] | None = None,
) -> CompiledQuery:
    """`allowed_countries=None` means unrestricted; an empty list means no access at all."""
    metrics = validate(q, catalog, known_values)
    fact = catalog.facts[metrics[0].fact]
    p = period or q.period
    params: list = []

    needed = {catalog.dimensions[d].table for d in [*q.dimensions, *(f.dimension for f in q.filters)]}
    country_table = fact.country_column.split(".", 1)[0]
    if allowed_countries is not None:
        needed.add(country_table)

    joins = []
    for table, key in fact.joins.items():
        if table in needed:
            joins.append(f"join marts.{table} on {table}.{key} = fct.{key}")
    if "dim_date" in needed:
        joins.append(f"join marts.dim_date on dim_date.date_day = fct.{fact.time_column}")

    select_dims = [f'{catalog.dimensions[d].column} as "{d}"' for d in q.dimensions]
    select_metrics = [f'{m.expression} as "{m.name}"' for m in metrics]

    where = [f"fct.{fact.time_column} between ? and ?"]
    params += [p.start, p.end]
    for f in q.filters:
        where.append(f"{catalog.dimensions[f.dimension].column} in ({', '.join('?' for _ in f.values)})")
        params += list(f.values)
    if allowed_countries is not None:
        if not allowed_countries:
            where.append("false")
        else:
            where.append(f"{fact.country_column} in ({', '.join('?' for _ in allowed_countries)})")
            params += list(allowed_countries)

    sql = f"select {', '.join(select_dims + select_metrics)}\nfrom marts.{fact.name} as fct"
    if joins:
        sql += "\n" + "\n".join(joins)
    sql += "\nwhere " + "\n  and ".join(where)
    if q.dimensions:
        time_dims = [d for d in q.dimensions if d in ("year", "quarter", "month", "week")]
        sql += "\ngroup by all"
        if time_dims:
            sql += f'\norder by "{time_dims[0]}"'
        else:
            sql += f'\norder by "{metrics[0].name}" {q.order} nulls last'
        sql += f"\nlimit {int(q.limit)}"
    return CompiledQuery(sql=sql, params=params, columns=[*q.dimensions, *q.metrics], fact=fact.name)
