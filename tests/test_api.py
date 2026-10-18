"""HTTP API: authentication, roles, row-level access, validation, feedback, headers, rate limits."""

import pytest
from fastapi.testclient import TestClient

from insight.api.app import create_app
from insight.observability import Observability

ANALYST = {"X-API-Key": "demo-analyst-key"}
NL = {"X-API-Key": "demo-sales-nl-key"}
ADMIN = {"X-API-Key": "demo-admin-key"}


@pytest.fixture(scope="module")
def client(settings, engine, tmp_path_factory):
    obs = Observability(tmp_path_factory.mktemp("obs") / "app.sqlite")
    return TestClient(create_app(settings, engine, obs, ask_limit_per_min=100))


def test_requires_a_valid_key(client):
    assert client.post("/v1/ask", json={"question": "oee"}).status_code == 401
    r = client.post("/v1/ask", json={"question": "oee this year"}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "unauthorized"


def test_ask_returns_a_traceable_answer(client):
    r = client.post("/v1/ask", json={"question": "Purchase price variance by material in Q3 2026"}, headers=ANALYST).json()
    assert r["status"] == "answered" and r["rows"][0]["material"] == "Sunflower oil"
    assert r["metrics"][0]["owner"] == "Procurement" and r["sql"] and r["interaction_id"]


def test_row_level_access_through_the_api(client):
    r = client.post("/v1/ask", json={"question": "Net revenue by country this year"}, headers=NL).json()
    assert [row["country"] for row in r["rows"]] == ["NL"]
    q = client.post("/v1/query", json={"metrics": ["net_revenue"], "dimensions": ["country"]}, headers=NL).json()
    assert [row["country"] for row in q["rows"]] == ["NL"]


def test_governed_query_endpoint_returns_csv_for_bi_tools(client):
    r = client.post(
        "/v1/query",
        json={"metrics": ["oee", "scrap_rate"], "dimensions": ["plant"], "period": {"kind": "last_quarter"}, "format": "csv"},
        headers=ANALYST,
    )
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0] == "plant,oee,scrap_rate" and len(r.text.splitlines()) == 4


def test_validation_errors_use_one_envelope(client):
    r = client.post("/v1/query", json={"metrics": ["ebitda"]}, headers=ANALYST)
    assert r.status_code == 400 and "Unknown metric" in r.json()["error"]["message"]
    r = client.post("/v1/ask", json={"question": "x" * 600}, headers=ANALYST)
    assert r.status_code == 400 and r.json()["error"]["details"][0]["field"] == "question"


def test_catalog_lineage_and_data_quality(client):
    items = client.get("/v1/metrics", headers=ANALYST).json()["items"]
    assert {"oee", "otif_rate", "net_revenue"} <= {i["name"] for i in items}
    card = client.get("/v1/metrics/otif_rate", headers=ANALYST).json()
    assert "erp/purchase_orders.csv" in card["landing_files"]
    assert client.get("/v1/metrics/ebitda", headers=ANALYST).status_code == 404
    dq = client.get("/v1/data-quality", headers=ANALYST).json()
    assert dq["data_as_of"] == "2026-09-30" and len(dq["sources"]) == 4


def test_feedback_only_by_the_asker_and_ai_kpis_only_for_admins(client):
    iid = client.post("/v1/ask", json={"question": "OEE this year"}, headers=ANALYST).json()["interaction_id"]
    assert client.post("/v1/feedback", json={"interaction_id": iid, "rating": "up"}, headers=NL).status_code == 404
    assert client.post("/v1/feedback", json={"interaction_id": iid, "rating": "up"}, headers=ANALYST).status_code == 204
    assert client.get("/v1/ai-kpis", headers=ANALYST).status_code == 403
    k = client.get("/v1/ai-kpis", headers=ADMIN).json()
    assert k["questions"] >= 1 and k["feedback_up"] >= 1 and k["numbers_verified_rate"] == 1.0


def test_security_headers_and_web_ui(client):
    r = client.get("/")
    assert r.status_code == 200 and "Insight Copilot" in r.text
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-request-id"]


def test_rate_limit(settings, engine, tmp_path):
    c = TestClient(create_app(settings, engine, Observability(tmp_path / "a.sqlite"), ask_limit_per_min=2))
    codes = [c.post("/v1/ask", json={"question": "OEE this year"}, headers=ANALYST).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_prometheus_metrics(client):
    client.post("/v1/ask", json={"question": "OEE this year"}, headers=ANALYST)
    text = client.get("/ops/prometheus").text
    assert "insight_questions_total" in text and "insight_verification_total" in text
