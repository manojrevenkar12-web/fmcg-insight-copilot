"""Semantic layer: definitions are valid, SQL is parameterised, row-level access cannot be bypassed."""

import pytest
import yaml

from insight.semantic import periods
from insight.semantic.catalog import Catalog
from insight.semantic.compiler import Filter, MetricQuery, QueryError, compile_query

Q3 = periods.quarter(2026, 3)


def test_every_metric_runs_for_every_allowed_dimension(catalog, warehouse):
    for m in catalog.metrics.values():
        for d in [None, *m.dimensions]:
            q = MetricQuery(metrics=[m.name], dimensions=[d] if d else [], period=Q3)
            rows = warehouse.run(compile_query(q, catalog, None))
            assert rows, f"{m.name} by {d} returned nothing"


def test_ratio_kpis_are_aggregated_from_totals_not_averaged(catalog, warehouse):
    by_line = warehouse.run(compile_query(MetricQuery(metrics=["oee"], dimensions=["line"], period=Q3, limit=50), catalog, None))
    overall = warehouse.run(compile_query(MetricQuery(metrics=["oee"], period=Q3), catalog, None))[0]["oee"]
    naive = sum(r["oee"] for r in by_line) / len(by_line)
    truth = warehouse.scalar(
        "select sum(good_kg)/sum(ideal_output_kg) from marts.fct_production where production_date between '2026-07-01' and '2026-09-30'"
    )
    assert overall == pytest.approx(truth)
    assert overall != pytest.approx(naive, abs=1e-6)


def test_filter_values_are_bound_parameters_never_sql(catalog, warehouse):
    evil = "x') or 1=1 --"
    q = MetricQuery(metrics=["net_revenue"], filters=[Filter(dimension="customer", values=[evil])], period=Q3)
    c = compile_query(q, catalog, None)
    assert evil not in c.sql and evil in c.params
    assert warehouse.run(c)[0]["net_revenue"] is None  # treated as a literal customer name: no match


def test_unknown_filter_values_are_rejected_with_a_readable_error(catalog, warehouse):
    values = warehouse.dimension_values(catalog)
    with pytest.raises(QueryError, match="No supplier called Acme"):
        compile_query(
            MetricQuery(metrics=["spend"], filters=[Filter(dimension="supplier", values=["Acme"])], period=Q3), catalog, None, known_values=values
        )


def test_metrics_from_different_processes_cannot_be_mixed(catalog):
    with pytest.raises(QueryError, match="different processes"):
        compile_query(MetricQuery(metrics=["oee", "net_revenue"], period=Q3), catalog, None)


def test_disallowed_dimension_is_rejected(catalog):
    with pytest.raises(QueryError, match="cannot be broken down by"):
        compile_query(MetricQuery(metrics=["oee"], dimensions=["customer"], period=Q3), catalog, None)


@pytest.mark.parametrize("metric,dim", [("net_revenue", "country"), ("oee", "plant"), ("spend", "plant")])
def test_row_level_access_is_enforced_in_sql(catalog, warehouse, metric, dim):
    rows = warehouse.run(compile_query(MetricQuery(metrics=[metric], dimensions=[dim], period=Q3), catalog, ["NL"]))
    assert rows and all(str(r[dim]).startswith("NL") for r in rows)
    none = warehouse.run(compile_query(MetricQuery(metrics=[metric], period=Q3), catalog, []))
    assert none[0][metric] is None


def test_catalog_rejects_dimension_without_join(tmp_path, settings):
    raw = yaml.safe_load(settings.semantic_path.read_text())
    raw["metrics"][0]["dimensions"].append("customer")
    p = tmp_path / "bad.yml"
    p.write_text(yaml.safe_dump(raw))
    with pytest.raises(ValueError, match="needs a join"):
        Catalog.load(p)


def test_catalog_columns_exist_in_the_warehouse(catalog, warehouse):
    cols = warehouse.columns()
    for d in catalog.dimensions.values():
        table = d.table if d.table != "fct" else None
        if table:
            assert f"{table}.{d.field}" in cols, d.name


def test_periods():
    as_of = periods.date(2026, 9, 30)
    assert periods.last_complete_quarter(as_of).label == "Q3 2026"
    assert periods.last_complete_month(periods.date(2026, 9, 15)).label == "August 2026"
    assert periods.previous(periods.quarter(2026, 1)).label == "Q4 2025"
    assert periods.previous(periods.ytd(as_of)).start == periods.date(2025, 1, 1)
    assert periods.month(2024, 2).end == periods.date(2024, 2, 29)
