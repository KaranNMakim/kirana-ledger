"""Own-shop mode: setup, add customers/products/local names, start empty, export the graph."""

import json

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Namespace

from app.api.main import create_app
from app.settings import Settings
from data.generate import generate

KL = Namespace("https://kirana-ledger.example/ontology#")


@pytest.fixture
def own(tmp_path):
    settings = Settings(db_path=str(tmp_path / "myshop.db"), mode="own", web_dir=tmp_path / "noweb")
    return settings, TestClient(create_app(settings))


def test_fresh_own_shop_needs_setup(own):
    _, c = own
    s = c.get("/shop").json()
    assert s["mode"] == "own" and s["configured"] is False
    assert s["name"] == "My Kirana Store" and s["locality"] is None
    assert s["counts"]["customers"] == 0 and s["counts"]["entries"] == 0 and s["counts"]["products"] >= 150
    assert c.get("/health").json()["mode"] == "own"
    done = c.put("/shop", json={"name": "Patel Provision Store", "locality": "Navrangpura", "language": "gu-IN"}).json()
    assert done["configured"] is True and done["name"] == "Patel Provision Store" and done["language"] == "gu-IN"
    assert c.put("/shop", json={"name": ""}).status_code == 422
    assert c.put("/shop", json={"name": "X", "language": "fr-FR"}).status_code == 422


def test_add_customer_and_duplicate_guard(own):
    _, c = own
    r = c.post("/customers", json={"name": "Ramesh Patel", "gender": "m", "locality": "Gali 2"})
    assert r.status_code == 201 and r.json()["id"] == "cust:ramesh-patel"
    dup = c.post("/customers", json={"name": "Ramesh Patel"})
    assert dup.status_code == 409 and dup.json()["similar"][0]["name"] == "Ramesh Patel"
    forced = c.post("/customers", json={"name": "Ramesh Patel", "force": True})
    assert forced.status_code == 201 and forced.json()["id"] == "cust:ramesh-patel-2"
    detail = c.get("/customers/cust:ramesh-patel").json()
    assert detail["provenance"]["method"] == "human" and detail["provenance"]["source"] == "app:add-customer"
    # the voice flow now sees the new customer
    said = c.post("/utterance", json={"text": "Ramesh Patel ko 2 kilo chawal udhaar"}).json()
    assert said["interpretation"]["customer"]["status"] in ("matched", "ambiguous")


def test_add_product_with_local_names_teaches_the_parser(own):
    settings, c = own
    c.post("/customers", json={"name": "Meena Joshi", "gender": "f"})
    vocab = c.get("/products/vocab").json()
    assert "kg" in vocab["units"] and "staples" in vocab["categories"] and "gu" in vocab["languages"]
    r = c.post("/products", json={"name": "Hapus Mango", "category": "vegetables", "unit": "dozen", "price": 900,
                                  "aliases": {"hi": ["hapus aam", "alphonso"], "gu": ["hapus keri"]}})
    assert r.status_code == 201
    sku = r.json()["sku"]
    assert sku == "SHOP-HAPUS-MANGO"
    said = c.post("/utterance", json={"text": "Meena ben ko 1 dozen hapus keri udhaar"}).json()
    assert said["decision"] == "saved" and said["event"]["items"][0]["sku"] == sku
    assert said["event"]["amount"] == 900
    # teach a new local name for an existing product, change a price
    assert c.post("/products/RICE-KOLAM/aliases", json={"text": "bhaat", "lang": "mr"}).status_code == 200
    assert c.patch("/products/RICE-KOLAM", json={"price": 64}).json()["price"] == 64
    rice = c.post("/utterance", json={"text": "Meena ben ko 2 kilo bhaat"}).json()
    assert rice["event"]["items"][0]["sku"] == "RICE-KOLAM" and rice["event"]["amount"] == 128
    # survives a restart: the graph is the source of truth
    c2 = TestClient(create_app(settings))
    rows = c2.get("/products/aliases?q=hapus").json()["products"]
    assert rows[0]["sku"] == sku and rows[0]["custom"] is True
    assert c2.get("/products/aliases?q=bhaat").json()["resolution"]["sku"] == "RICE-KOLAM"
    assert c2.get("/shop").json()["counts"]["shop_products"] == 1


@pytest.mark.parametrize("body,code,msg", [
    ({"name": "Rice", "category": "grains", "unit": "kg", "price": 50}, 400, "already exists"),
    ({"name": "Thing", "category": "toys", "unit": "kg", "price": 5}, 400, "unknown category"),
    ({"name": "Thing", "category": "misc", "unit": "bushel", "price": 5}, 400, "unknown unit"),
    ({"name": "Thing", "category": "misc", "unit": "kg", "price": 5, "aliases": {"hi": ["chawal"]}}, 400, "already means"),
    ({"name": "Thing", "category": "misc", "unit": "kg", "price": 5, "aliases": {"hi": ["tel"]}}, 400, "shared word"),
    ({"name": "Thing", "category": "misc", "unit": "kg", "price": 5, "aliases": {"xx": ["a"]}}, 400, "language"),
    ({"name": "Thing", "category": "misc", "unit": "kg", "price": 0}, 422, ""),
])
def test_add_product_validation(own, body, code, msg):
    _, c = own
    r = c.post("/products", json=body)
    assert r.status_code == code and msg in json.dumps(r.json())


def test_alias_and_price_errors(own):
    _, c = own
    assert c.post("/products/NOPE/aliases", json={"text": "x"}).status_code == 404
    assert c.post("/products/SUGAR/aliases", json={"text": "chawal"}).status_code == 400
    assert c.post("/products/SUGAR/aliases", json={"text": "x", "lang": "fr"}).status_code == 400
    assert c.patch("/products/NOPE", json={"price": 3}).status_code == 404


def test_start_empty_keeps_shop_and_catalogue(tmp_path):
    settings = Settings(db_path=str(tmp_path / "k.db"), web_dir=tmp_path / "noweb")
    generate(settings, verbose=False)
    c = TestClient(create_app(settings))
    pending = c.post("/utterance", json={"text": "Ramesh bhai ko 2 kilo chawal udhaar"}).json()["pending_id"]
    assert c.post("/shop/start-empty", json={"confirm": "yes"}).status_code == 400
    out = c.post("/shop/start-empty", json={"confirm": "DELETE"}).json()
    assert out["removed"]["Customer"] == 60 and out["removed"]["LedgerEvent"] > 2000
    assert out["shop"]["counts"] == {**out["shop"]["counts"], "customers": 0, "entries": 0}
    assert c.get("/customers").json() == [] and c.get("/ledger").json() == []
    assert c.get("/insights").json()["totals"]["outstanding"] == 0
    assert c.post("/utterance/confirm", json={"pending_id": pending, "customer_id": "x"}).status_code == 404
    # the store keeps working from empty
    assert c.post("/customers", json={"name": "Asha Shah"}).status_code == 201
    assert c.post("/utterance", json={"text": "Asha ben ne 200 diye"}).json()["decision"] == "saved"
    reopened = TestClient(create_app(settings))
    assert len(reopened.get("/customers").json()) == 1


def test_export_graph_formats(own):
    _, c = own
    c.post("/customers", json={"name": "Meena Joshi", "gender": "f"})
    ev = c.post("/utterance", json={"text": "Meena ben ko 2 kilo chawal udhaar"}).json()["event"]
    ttl = c.get("/export?format=turtle")
    assert ttl.status_code == 200 and "attachment" in ttl.headers["content-disposition"]
    g = Graph().parse(data=ttl.text, format="turtle")
    assert (None, KL.owes, None) in g and (None, KL.bought, None) in g
    assert len(list(g.subjects(None, KL.Product))) == 1  # only products the ledger uses, unless asked
    prov = Namespace("http://www.w3.org/ns/prov#")
    assert any(str(o) == ev["provenance"]["source"] for o in g.objects(None, prov.wasDerivedFrom))
    full = Graph().parse(data=c.get("/export?format=turtle&include_catalog=true").text, format="turtle")
    assert len(list(full.subjects(None, KL.Product))) >= 150 and len(list(full.subjects(None, KL.Alias))) > 600
    jl = c.get("/export?format=jsonld")
    assert jl.headers["content-type"].startswith("application/ld+json") and isinstance(jl.json(), list | dict)
    js = c.get("/export?format=json").json()
    assert js["format"] == "kirana-graph/v1".replace("kirana-graph", "kirana-ledger-graph")
    assert {n["type"] for n in js["nodes"]} >= {"Shop", "Customer", "LedgerEvent", "Product"}
    assert all("prov" in e for e in js["edges"])
    assert c.get("/export?format=xml").status_code == 422
