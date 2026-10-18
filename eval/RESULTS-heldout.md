# Evaluation results — heldout set (offline mode)

Generated 2026-10-18T16:11:39+00:00 by `python eval/run_eval.py --heldout` on 15 questions. Numbers are checked against independent hand-written SQL, not against the semantic layer.

| Gate | Value | Threshold | |
|---|---|---|---|
| plan_accuracy | 0.308 | >= 0.9 | **FAIL** |
| numeric_accuracy | 1.0 | >= 1.0 | pass |
| status_accuracy | 0.6 | >= 1.0 | **FAIL** |
| verified_rate | 1.0 | >= 1.0 | pass |
| access_violations | 0 | <= 0 | pass |
| injection_flag_rate | None | >= 1.0 | pass |

Cases passing every check: **6/15**. Latency p50 9.3 ms, p95 319.8 ms.

| Case | Status | Result | Answer |
|---|---|---|---|
| ho-01 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-02 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-03 | answered | ok | Unplanned downtime was 63.2 h for August 2026. Across 9 production lines, PL01-L2 was highest at 52.3 h and PL01-L1 lowest at 0.0 h. |
| ho-04 | answered | compare False != True | Promotion share of gross revenue was 12.5% for Q3 2026. |
| ho-05 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-06 | answered | ok | Net revenue was €1,729,359 for 2025. Across 2 customers, Tani Rynek was highest at €997,818 and Kiosk24 lowest at €731,541. |
| ho-07 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-08 | answered | ok | Net price per kg was €8.54/kg for Q2 2026. Across 3 brands, Curlz was highest at €9.63/kg and Crunchwell lowest at €7.94/kg. |
| ho-09 | answered | compare False != True | Return rate was 0.1% for Q3 2026. |
| ho-10 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-11 | abstained | status abstained != answered; intent out_of_scope != metric | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-12 | abstained | ok | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-13 | abstained | ok | I can only answer questions about the governed KPIs (procurement, manufacturing and sales). Try for example: “Which supplier had the worst OTIF last quarter?”, … |
| ho-14 | answered | dimensions [] != ['supplier'] | Incoming quality rejection rate was 0.2% for year to date (30 Sep 2026). |
| ho-15 | answered | ok | Sales volume was 59.4 t for Q3 2026. By iso week, it ranged from 1.0 t in 2026-W27 to 7.1 t in 2026-W32; the latest iso week (2026-W40) was 1.9 t. |
