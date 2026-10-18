"""Landing → staging → quality → consumption: nothing is lost, defects are quarantined with a reason."""

import hashlib
import subprocess
import sys

from conftest import LANDING

from insight.config import ROOT


def _digest() -> str:
    h = hashlib.sha256()
    for f in sorted(LANDING.rglob("*.csv")):
        h.update(f.read_bytes())
    return h.hexdigest()


def test_generator_is_deterministic():
    before = _digest()
    subprocess.run([sys.executable, str(ROOT / "data" / "generate.py")], check=True, capture_output=True)
    assert _digest() == before


def test_every_row_is_accounted_for(warehouse):
    for row in warehouse.data_quality():
        assert row["rows_received"] == row["rows_passed"] + row["rows_quarantined"]


def test_planted_defects_are_quarantined_with_reasons(warehouse):
    issues = {
        (r["source"], r["dq_issue"]): r["n"] for r in warehouse.rows("select source, dq_issue, count(*) n from quality.dq_quarantine group by all")
    }
    assert issues[("erp.purchase_orders", "duplicate_line")] == 12
    assert issues[("mes.production_runs", "duplicate_run")] == 6
    assert issues[("mes.downtime_events", "missing_reason")] == 4
    assert issues[("oms.sales_order_lines", "unknown_sku")] == 8
    assert ("erp.purchase_orders", "unsupported_currency") not in issues  # 'eur' is standardised, not dropped


def test_consumption_layer_is_clean(warehouse):
    assert warehouse.scalar("select count(*) from marts.fct_purchase_deliveries where delivered_kg < 0 or supplier_id is null") == 0
    assert warehouse.scalar("select count(*) - count(distinct order_line_id) from marts.fct_sales") == 0
    assert warehouse.scalar("select count(*) from marts.fct_sales where sku not in (select sku from marts.dim_product)") == 0


def test_business_stories_are_present(warehouse):
    # The planted events must be findable — otherwise the copilot has nothing true to explain.
    baltic = warehouse.scalar(
        "select avg(is_otif::int) from marts.fct_purchase_deliveries where supplier_id='SUP-01' and delivered_date between '2026-07-01' and '2026-08-31'"
    )
    others = warehouse.scalar(
        "select avg(is_otif::int) from marts.fct_purchase_deliveries where supplier_id<>'SUP-01' and delivered_date between '2026-07-01' and '2026-08-31'"
    )
    assert baltic < others - 0.3
    line2 = warehouse.scalar(
        "select sum(good_kg)/sum(ideal_output_kg) from marts.fct_production where line_key='PL01-L2' and production_date between '2026-08-01' and '2026-08-31'"
    )
    assert line2 < 0.78
