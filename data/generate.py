"""Synthetic source systems for a fictional snack manufacturer ("Crunchwell Snacks").

Writes the *landing zone*: raw CSV extracts exactly as three source systems would deliver
them (ERP procurement, MES manufacturing, order management/sales), plus a load manifest.
Values are deterministic (seeded) so the evaluation set can assert exact numbers.

Business stories are planted so there is something real to find:
  * sunflower-oil prices rise above contract from April 2026 (purchase price variance);
  * supplier "Baltic Agro" misses delivery dates in July-August 2026 (OTIF drop);
  * plant PL01 line 2 has repeated breakdowns in August 2026 (OEE drop, unplanned downtime);
  * the Netherlands runs heavy promotions in Q3 2026 (promo share up).

And realistic data-quality defects so the quality layer has work to do:
  duplicate lines, negative quantities, missing keys, lower-case currency codes,
  delivery dates in the future, unknown SKUs.

    python data/generate.py            # -> data/landing/...
"""

from __future__ import annotations

import csv
import json
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LANDING = ROOT / "landing"
START = date(2025, 1, 1)
AS_OF = date(2026, 9, 30)
rng = random.Random(20261018)

PLANTS = [
    ("DE01", "Rhine Valley", "DE"),
    ("NL01", "Polderland", "NL"),
    ("PL01", "Vistula", "PL"),
]
LINES = ["L1", "L2", "L3"]

MATERIALS = [  # id, name, category, contract price EUR/kg, monthly kg per plant
    ("MAT-POT", "Potatoes", "Raw material", 0.21, 900_000),
    ("MAT-OIL", "Sunflower oil", "Raw material", 1.35, 140_000),
    ("MAT-PNT", "Peanuts", "Raw material", 2.10, 60_000),
    ("MAT-CRN", "Corn grits", "Raw material", 0.48, 120_000),
    ("MAT-SEA", "Seasoning blends", "Ingredient", 6.80, 15_000),
    ("MAT-PCK", "Packaging film", "Packaging", 4.20, 25_000),
]

SUPPLIERS = [  # id, name, country, materials
    ("SUP-01", "Baltic Agro", "PL", ["MAT-POT", "MAT-CRN"]),
    ("SUP-02", "Rhenish Potato Coop", "DE", ["MAT-POT"]),
    ("SUP-03", "Danube Oils", "AT", ["MAT-OIL"]),
    ("SUP-04", "Black Sea Seeds", "RO", ["MAT-OIL"]),
    ("SUP-05", "Sahel Nut Traders", "NL", ["MAT-PNT"]),
    ("SUP-06", "Flavourhouse", "DE", ["MAT-SEA"]),
    ("SUP-07", "Polyfilm Europe", "BE", ["MAT-PCK"]),
    ("SUP-08", "Lowlands Grain", "NL", ["MAT-CRN", "MAT-POT"]),
]

PRODUCTS = [  # sku, name, brand, category, kg per case, list price EUR per case
    ("SKU-101", "Crunchwell Classic Salted 175g", "Crunchwell", "Potato chips", 2.1, 18.40),
    ("SKU-102", "Crunchwell Paprika 175g", "Crunchwell", "Potato chips", 2.1, 18.90),
    ("SKU-103", "Crunchwell Sour Cream 175g", "Crunchwell", "Potato chips", 2.1, 18.90),
    ("SKU-201", "Nutty Roasted Peanuts 200g", "Nutty", "Nuts", 2.4, 21.60),
    ("SKU-202", "Nutty Honey Peanuts 150g", "Nutty", "Nuts", 1.8, 19.80),
    ("SKU-301", "Curlz Cheese 125g", "Curlz", "Extruded snacks", 1.5, 15.20),
    ("SKU-302", "Curlz Ketchup 125g", "Curlz", "Extruded snacks", 1.5, 15.20),
    ("SKU-401", "Crunchwell Party Pack 400g", "Crunchwell", "Potato chips", 4.8, 36.50),
]

CUSTOMERS = [  # id, name, channel, country — all fictional
    ("CUS-DE1", "Westmarkt Retail", "Retail", "DE"),
    ("CUS-DE2", "Rheinland Supermärkte", "Retail", "DE"),
    ("CUS-DE3", "Discount Nord", "Discount", "DE"),
    ("CUS-DE4", "FuelStop Shops", "Convenience", "DE"),
    ("CUS-NL1", "Kanaal Supermarkten", "Retail", "NL"),
    ("CUS-NL2", "Polder Foods", "Retail", "NL"),
    ("CUS-PL1", "Tani Rynek", "Discount", "PL"),
    ("CUS-PL2", "Kiosk24", "Convenience", "PL"),
    ("CUS-FR1", "Hexagone Retail", "Retail", "FR"),
    ("CUS-FR2", "Marché Central", "Retail", "FR"),
]

DOWNTIME_REASONS = [  # reason, planned
    ("Planned maintenance", True),
    ("Changeover", True),
    ("Cleaning", True),
    ("Mechanical breakdown", False),
    ("Electrical fault", False),
    ("Material shortage", False),
    ("Quality hold", False),
]


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def write_csv(path: Path, header: list[str], rows: list[list]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return len(rows)


def gen_master() -> dict[str, int]:
    counts = {}
    counts["erp/suppliers.csv"] = write_csv(
        LANDING / "erp" / "suppliers.csv", ["supplier_id", "supplier_name", "country"], [[s[0], s[1], s[2]] for s in SUPPLIERS]
    )
    counts["erp/materials.csv"] = write_csv(
        LANDING / "erp" / "materials.csv",
        ["material_id", "material_name", "category", "contract_price_eur_per_kg"],
        [[m[0], m[1], m[2], m[3]] for m in MATERIALS],
    )
    counts["erp/plants.csv"] = write_csv(LANDING / "erp" / "plants.csv", ["plant_id", "plant_name", "country"], [list(p) for p in PLANTS])
    counts["oms/products.csv"] = write_csv(
        LANDING / "oms" / "products.csv",
        ["sku", "product_name", "brand", "category", "kg_per_case", "list_price_eur_per_case"],
        [list(p) for p in PRODUCTS],
    )
    counts["oms/customers.csv"] = write_csv(
        LANDING / "oms" / "customers.csv", ["customer_id", "customer_name", "channel", "country"], [list(c) for c in CUSTOMERS]
    )
    return counts


def gen_purchase_orders() -> list[list]:
    rows: list[list] = []
    n = 0
    month = date(START.year, START.month, 1)
    while month <= AS_OF:
        for plant_id, _, _ in PLANTS:
            for mat_id, _, _, contract, monthly_kg in MATERIALS:
                suppliers = [s for s in SUPPLIERS if mat_id in s[3]]
                for delivery in range(2):  # two deliveries per material, plant and month
                    sup = rng.choice(suppliers)
                    n += 1
                    order_day = month + timedelta(days=rng.randint(0, 12) + delivery * 14)
                    promised = order_day + timedelta(days=rng.randint(5, 10))
                    ordered = round(monthly_kg / 2 * rng.uniform(0.85, 1.15))
                    late = rng.random() < 0.08
                    short = rng.random() < 0.05
                    # Story: Baltic Agro struggles in July-August 2026.
                    if sup[0] == "SUP-01" and date(2026, 7, 1) <= promised <= date(2026, 8, 31):
                        late = rng.random() < 0.55
                        short = rng.random() < 0.30
                    delivered_day = promised + timedelta(days=rng.randint(1, 6)) if late else promised - timedelta(days=rng.randint(0, 2))
                    delivered = round(ordered * (rng.uniform(0.85, 0.96) if short else rng.uniform(0.99, 1.01)))
                    price = contract * rng.uniform(0.98, 1.03)
                    # Story: sunflower oil price spike from April 2026.
                    if mat_id == "MAT-OIL" and order_day >= date(2026, 4, 1):
                        price = contract * rng.uniform(1.18, 1.30)
                    rejected = round(delivered * rng.uniform(0.0, 0.012)) if rng.random() < 0.3 else 0
                    rows.append(
                        [
                            f"PO-{n:06d}",
                            sup[0],
                            mat_id,
                            plant_id,
                            order_day.isoformat(),
                            promised.isoformat(),
                            delivered_day.isoformat(),
                            ordered,
                            delivered,
                            f"{price:.4f}",
                            "EUR",
                            rejected,
                        ]
                    )
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

    # --- data-quality defects, as real extracts have them ---
    for i in rng.sample(range(len(rows)), 12):
        rows.append(list(rows[i]))  # exact duplicate lines (re-sent extract)
    for i in rng.sample(range(len(rows)), 5):
        rows[i][8] = -abs(int(rows[i][8]))  # negative delivered quantity
    for i in rng.sample(range(len(rows)), 4):
        rows[i][1] = ""  # missing supplier
    for i in rng.sample(range(len(rows)), 30):
        rows[i][10] = "eur"  # lower-case currency: valid, must be standardised not dropped
    for i in rng.sample(range(len(rows)), 3):
        rows[i][6] = (AS_OF + timedelta(days=rng.randint(30, 90))).isoformat()  # delivered in the future
    return rows


def gen_production() -> tuple[list[list], list[list]]:
    runs: list[list] = []
    events: list[list] = []
    ideal_rate = {"L1": 55.0, "L2": 48.0, "L3": 40.0}  # kg per minute
    ev = 0
    for d in days(START, AS_OF):
        if d.weekday() == 6:  # no production on Sundays
            continue
        for plant_id, _, _ in PLANTS:
            for line in LINES:
                planned = 960  # two 8-hour shifts
                downtime = []
                if rng.random() < 0.35:
                    downtime.append(("Changeover", rng.randint(20, 45)))
                if rng.random() < 0.06:
                    downtime.append(("Planned maintenance", rng.randint(60, 180)))
                if rng.random() < 0.15:
                    downtime.append(("Cleaning", rng.randint(15, 30)))
                if rng.random() < 0.07:
                    downtime.append(
                        (rng.choice(["Mechanical breakdown", "Electrical fault", "Material shortage", "Quality hold"]), rng.randint(15, 90))
                    )
                # Story: PL01 line 2 gearbox problems in August 2026.
                if plant_id == "PL01" and line == "L2" and date(2026, 8, 1) <= d <= date(2026, 8, 31) and rng.random() < 0.6:
                    downtime.append(("Mechanical breakdown", rng.randint(120, 300)))
                down = min(sum(m for _, m in downtime), planned - 60)
                run = planned - down
                perf = rng.uniform(0.86, 0.95)
                total = run * ideal_rate[line] * perf
                scrap_share = rng.uniform(0.015, 0.035)
                if plant_id == "PL01" and line == "L2" and d.month == 8 and d.year == 2026:
                    scrap_share += 0.02  # restarts after breakdowns produce more scrap
                scrap = total * scrap_share
                runs.append(
                    [
                        f"RUN-{plant_id}-{line}-{d.isoformat()}",
                        plant_id,
                        line,
                        d.isoformat(),
                        planned,
                        run,
                        ideal_rate[line],
                        round(total - scrap, 1),
                        round(scrap, 1),
                    ]
                )
                for reason, minutes in downtime:
                    ev += 1
                    start = datetime(d.year, d.month, d.day, 6, 0) + timedelta(minutes=rng.randint(0, 800))
                    events.append([f"DT-{ev:07d}", plant_id, line, start.isoformat(), minutes, reason])
    for i in rng.sample(range(len(runs)), 6):
        runs.append(list(runs[i]))  # duplicate run records from a MES re-sync
    for i in rng.sample(range(len(events)), 4):
        events[i][5] = ""  # downtime without a reason code
    return runs, events


def gen_sales() -> list[list]:
    rows: list[list] = []
    n = 0
    weights = {"DE": 1.0, "NL": 0.55, "PL": 0.6, "FR": 0.7}
    for d in days(START, AS_OF):
        if d.weekday() >= 5:
            continue
        season = 1.25 if d.month in (6, 7, 8, 12) else 1.0  # summer and Christmas peaks
        for cus_id, _, channel, country in CUSTOMERS:
            if rng.random() > 0.55:
                continue
            for sku, _, _, _, kg_case, list_price in rng.sample(PRODUCTS, rng.randint(2, 4)):
                n += 1
                cases = max(1, round(rng.gauss(140, 40) * weights[country] * season * (1.3 if channel == "Discount" else 1.0)))
                gross = cases * list_price
                promo = rng.random() < 0.18
                # Story: heavy NL promotions in Q3 2026.
                if country == "NL" and date(2026, 7, 1) <= d <= date(2026, 9, 30):
                    promo = rng.random() < 0.55
                discount = gross * rng.uniform(0.15, 0.30) if promo else 0.0
                if promo:
                    cases = round(cases * 1.35)  # promotions lift volume
                    gross = cases * list_price
                    discount = gross * (discount / max(cases / 1.35 * list_price, 1))
                returned = rng.randint(1, 6) if rng.random() < 0.03 else 0
                rows.append(
                    [f"SO-{n:07d}", d.isoformat(), cus_id, sku, cases, round(cases * kg_case, 1), round(gross, 2), round(discount, 2), returned]
                )
    for i in rng.sample(range(len(rows)), 8):
        rows[i][3] = "SKU-999"  # SKU unknown to master data
    for i in rng.sample(range(len(rows)), 10):
        rows.append(list(rows[i]))
    return rows


def main() -> None:
    counts = gen_master()
    po = gen_purchase_orders()
    counts["erp/purchase_orders.csv"] = write_csv(
        LANDING / "erp" / "purchase_orders.csv",
        [
            "po_line_id",
            "supplier_id",
            "material_id",
            "plant_id",
            "order_date",
            "promised_date",
            "delivered_date",
            "ordered_qty_kg",
            "delivered_qty_kg",
            "unit_price",
            "currency",
            "rejected_qty_kg",
        ],
        po,
    )
    runs, events = gen_production()
    counts["mes/production_runs.csv"] = write_csv(
        LANDING / "mes" / "production_runs.csv",
        ["run_id", "plant_id", "line_id", "production_date", "planned_minutes", "run_minutes", "ideal_rate_kg_per_min", "good_kg", "scrap_kg"],
        runs,
    )
    counts["mes/downtime_events.csv"] = write_csv(
        LANDING / "mes" / "downtime_events.csv", ["event_id", "plant_id", "line_id", "started_at", "duration_minutes", "reason"], events
    )
    sales = gen_sales()
    counts["oms/sales_order_lines.csv"] = write_csv(
        LANDING / "oms" / "sales_order_lines.csv",
        ["order_line_id", "order_date", "customer_id", "sku", "cases", "volume_kg", "gross_revenue_eur", "promo_discount_eur", "returned_cases"],
        sales,
    )
    manifest = {
        "load_id": "LOAD-20261001-0600",
        "extracted_at": datetime(2026, 10, 1, 6, 0, tzinfo=UTC).isoformat(),
        "data_as_of": AS_OF.isoformat(),
        "files": counts,
    }
    (LANDING / "_load_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for k, v in counts.items():
        print(f"{k:32s} {v:>7d} rows")


if __name__ == "__main__":
    main()
