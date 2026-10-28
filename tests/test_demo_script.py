"""The three flows in docs/demo-script.md, end to end through the API, on fresh seeded data."""

import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from app.settings import Settings
from data.generate import generate


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(db_path=str(tmp_path_factory.mktemp("demo") / "kirana.db"))
    generate(settings, verbose=False)
    return TestClient(create_app(settings))


def test_flow1_speak_a_credit_sale(client):
    r = client.post("/utterance", json={"text": "Suresh ka 3 packet Parle-G aur 1 litre tel likh do"}).json()
    assert r["decision"] == "saved"
    ev = r["event"]
    assert ev["customer_name"] == "Suresh Mehta" and ev["amount"] == 180
    assert [i["name"] for i in ev["items"]] == ["Parle-G", "Sunflower Oil (loose)"]
    assert client.get("/ledger?limit=1").json()[0]["id"] == ev["id"]
    undone = client.post(f"/ledger/{ev['id']}/undo", json={"reason": "demo"}).json()
    assert undone["status"] == "voided" and undone["history"][-1]["by"] == "human"


def test_flow2_resolve_ambiguous_customer(client):
    before = client.get("/customers/cust:ramesh-shah").json()["features"]["balance"]
    r = client.post("/utterance", json={"text": "Ramesh bhai ko 2 kilo chawal udhaar"}).json()
    assert r["decision"] == "needs_confirmation"
    q = r["interpretation"]["questions"][0]
    assert q["prompt"] == "Which Ramesh?" and {o["label"] for o in q["options"]} == {"Ramesh Patel", "Ramesh Shah"}
    done = client.post("/utterance/confirm", json={"pending_id": r["pending_id"], "customer_id": "cust:ramesh-shah",
                                                   "intent": "credit_sale"}).json()
    assert done["decision"] == "saved" and done["event"]["provenance"]["method"] == "human"
    assert client.get("/customers/cust:ramesh-shah").json()["features"]["balance"] == pytest.approx(before + 120)
    gu = client.post("/utterance", json={"text": "Kavitaben na khata ma 1 kilo khand lakhi do"}).json()
    assert gu["interpretation"]["customer"]["status"] == "ambiguous"


def test_flow3_reminder_to_late_payer(client):
    late = client.get("/insights").json()["late_payers"]
    assert any(p["id"] == "cust:kishore-desai" for p in late)
    c = client.get("/customers/cust:kishore-desai").json()
    assert c["pattern"]["band"] in ("Frequently late", "Often slow to pay")
    assert "not a credit score" in c["pattern"]["disclaimer"] and c["pattern"]["evidence"]
    for lang, needle in [("hinglish", "hisaab baaki"), ("gu", "Kishorebhai"), ("en", "pending")]:
        d = client.post("/reminders/draft", json={"customer_id": "cust:kishore-desai", "language": lang}).json()
        assert needle in d["text"] and d["sent"] is False


def test_extra_half_settlement_card(client):
    r = client.post("/utterance", json={"text": "aaj Kishore ne aadha hisaab chukta kiya"}).json()
    assert r["decision"] == "needs_confirmation" and any("half of balance" in x for x in r["reasons"])
