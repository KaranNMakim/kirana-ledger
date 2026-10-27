"""API contract tests against a freshly generated demo database."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.settings import Settings
from data.generate import generate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("db") / "kirana.db")
    settings = Settings(db_path=db, web_dir=tmp_path_factory.mktemp("noweb") / "out")
    generate(settings, verbose=False)
    return TestClient(create_app(settings))


def keys(d, *ks):
    missing = [k for k in ks if k not in d]
    assert not missing, f"missing keys {missing} in {sorted(d)}"


def test_health_and_ontology(client):
    h = client.get("/health").json()
    keys(h, "status", "llm_mode", "today", "shop", "graph", "confirm_threshold")
    assert h["graph"]["nodes"]["Customer"] == 60
    assert client.get("/ontology").json()["counts"]["products"] >= 150
    r = client.get("/health")
    assert r.headers["x-request-id"]


def test_utterance_saved_contract(client):
    r = client.post("/utterance", json={"text": "Meena ben ne 500 diye", "lang": "hi-IN"})
    assert r.status_code == 200
    body = r.json()
    keys(body, "utterance_id", "decision", "parsed", "interpretation", "pending_id", "event", "answer", "reasons")
    assert body["decision"] == "saved" and body["event"]["kind"] == "payment"
    keys(body["parsed"], "intent", "intent_confidence", "customer_text", "customer_confidence", "items", "amount",
         "amount_confidence", "days_ago", "date_confidence", "method")
    keys(body["interpretation"], "intent", "customer", "items", "amount", "date", "fields", "questions",
         "confidence", "summary")
    keys(body["event"]["provenance"], "source", "timestamp", "confidence", "method")
    assert body["event"]["provenance"]["source"] == body["utterance_id"]


def test_utterance_validation(client):
    assert client.post("/utterance", json={"text": ""}).status_code == 422
    assert client.post("/utterance", json={}).status_code == 422


def test_disambiguation_and_confirm(client):
    body = client.post("/utterance", json={"text": "Ramesh bhai ko 2 kilo chawal udhaar"}).json()
    assert body["decision"] == "needs_confirmation" and body["pending_id"]
    q = body["interpretation"]["questions"][0]
    keys(q, "field", "prompt", "options")
    keys(q["options"][0], "id", "label", "balance")
    choice = q["options"][0]["id"]
    done = client.post("/utterance/confirm", json={"pending_id": body["pending_id"], "customer_id": choice}).json()
    assert done["decision"] == "saved" and done["event"]["customer_id"] == choice
    assert done["event"]["provenance"]["method"] == "human"
    again = client.post("/utterance/confirm", json={"pending_id": body["pending_id"], "customer_id": choice})
    assert again.status_code == 404
    bad = client.post("/utterance", json={"text": "Ramesh bhai ko 1 kilo cheeni"}).json()
    r = client.post("/utterance/confirm", json={"pending_id": bad["pending_id"]})
    assert r.status_code == 400 and "customer" in r.json()["detail"]


def test_query_answer(client):
    body = client.post("/utterance", json={"text": "Kishore ka kitna baaki hai"}).json()
    assert body["decision"] == "answered" and "Kishore Desai owes" in body["answer"]


def test_customers_list_and_detail(client):
    rows = client.get("/customers").json()
    assert len(rows) == 60
    keys(rows[0], "id", "name", "balance", "last_payment_date", "band", "score", "summary")
    assert rows[0]["balance"] >= rows[-1]["balance"]
    assert [r["name"] for r in client.get("/customers?q=ramesh").json()][:2] == sorted(
        ["Ramesh Patel", "Ramesh Shah"], key=lambda n: -next(r["balance"] for r in rows if r["name"] == n))
    assert all(r["balance"] > 1 for r in client.get("/customers?owing_only=true").json())
    assert client.get("/customers?sort=name").json()[0]["name"] <= client.get("/customers?sort=name").json()[1]["name"]
    d = client.get("/customers/cust:kishore-desai").json()
    keys(d, "id", "name", "features", "pattern", "events", "reminders", "props", "provenance")
    keys(d["pattern"], "label", "score", "band", "evidence", "disclaimer", "summary", "data_sufficiency")
    assert "not a credit score" in d["pattern"]["disclaimer"]
    assert client.get("/customers/cust:nobody").status_code == 404
    assert client.get("/customers?sort=bogus").status_code == 422


def test_ledger_undo_edit(client):
    feed = client.get("/ledger?limit=5").json()
    assert len(feed) == 5
    keys(feed[0], "id", "kind", "customer_id", "customer_name", "amount", "date", "items", "status", "provenance")
    saved = client.post("/utterance", json={"text": "Suresh ka 3 packet Parle-G likh do"}).json()["event"]
    eid = saved["id"]
    assert client.get(f"/ledger/{eid}").json()["amount"] == 30
    edited = client.post(f"/ledger/{eid}/edit", json={"items": [{"sku": "PARLEG", "qty": 5}], "reason": "5 not 3"})
    assert edited.status_code == 200 and edited.json()["amount"] == 50 and edited.json()["supersedes"] == eid
    old = client.get(f"/ledger/{eid}").json()
    assert old["status"] == "voided" and old["history"][0]["action"] == "edit"
    new_id = edited.json()["id"]
    undone = client.post(f"/ledger/{new_id}/undo", json={"reason": "duplicate"}).json()
    assert undone["status"] == "voided" and undone["history"][-1]["by"] == "human"
    assert client.post(f"/ledger/{new_id}/undo").status_code == 400
    assert client.get("/ledger/evt-xyz").status_code == 404
    voided = client.get("/ledger?include_voided=true&customer_id=cust:suresh-mehta&limit=5000").json()
    assert {eid, new_id} <= {e["id"] for e in voided}


def test_insights_contract(client):
    ins = client.get("/insights").json()
    keys(ins, "as_of", "totals", "top_owed", "late_payers", "monthly", "seasons", "seasonality", "top_products",
         "pattern_bands", "disclaimer")
    keys(ins["totals"], "outstanding", "customers", "customers_owing", "credit_last_30d", "collected_last_30d")
    assert len(ins["monthly"]) == 6
    keys(ins["top_owed"][0], "id", "name", "balance", "oldest_unpaid_days", "band", "score")


def test_graph_contract(client):
    g = client.get("/graph?limit=5").json()
    assert {n["data"]["type"] for n in g["nodes"]} == {"Shop", "Customer", "Product"}
    keys(g["edges"][0]["data"], "id", "source", "target", "rel")
    assert client.get("/graph?customer_id=cust:nobody").status_code == 404
    assert client.get("/graph?customer_id=cust:meena-joshi").status_code == 200


@pytest.mark.parametrize("language", ["en", "hinglish", "gu"])
def test_reminder_draft_contract(client, language):
    r = client.post("/reminders/draft", json={"customer_id": "cust:kishore-desai", "language": language})
    assert r.status_code == 200
    d = r.json()
    keys(d, "customer_id", "customer_name", "language", "tone", "balance", "text", "sent", "note", "method")
    assert d["sent"] is False and "₹" in d["text"]
    assert client.get("/customers/cust:kishore-desai").json()["reminders"]


def test_reminder_errors(client):
    assert client.post("/reminders/draft", json={"customer_id": "cust:nobody"}).status_code == 404
    assert client.post("/reminders/draft", json={"customer_id": "cust:kishore-desai",
                                                 "language": "fr"}).status_code == 422
    rows = client.get("/customers").json()
    settled = next((r for r in rows if r["balance"] <= 1), None)
    if settled:
        assert client.post("/reminders/draft", json={"customer_id": settled["id"]}).status_code == 400


def test_product_aliases(client):
    body = client.get("/products/aliases?q=chokha").json()
    assert body["resolution"]["sku"] == "RICE-KOLAM" and body["products"][0]["sku"] == "RICE-KOLAM"
    assert "tel" in body["generic_terms"]
    assert len(client.get("/products/aliases").json()["products"]) >= 150


def test_web_not_built_message(client):
    assert client.get("/", follow_redirects=False).status_code == 307
    assert client.get("/app/").status_code == 503
