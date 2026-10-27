import pytest
import yaml
from rdflib import Graph

from app.kg.graph_store import NetworkXSQLiteStore
from app.kg.names import canon, phonetic_key, romanize, similarity, strip_honorifics, tokenize
from app.kg.ontology import OntologyError, load_ontology
from app.kg.provenance import Provenance


@pytest.fixture(scope="module")
def onto():
    return load_ontology()


# ------------------------------------------------------------------ ontology
def test_ontology_loads_catalogue(onto):
    counts = onto.summary()["counts"]
    assert counts["products"] >= 150
    assert counts["aliases"] >= 600
    assert {"Shop", "Customer", "Product", "LedgerEvent", "Reminder"} <= set(onto.classes)
    assert {"owes", "bought", "paid", "alias_of", "belongs_to_shop"} <= set(onto.relations)


def test_spec_aliases_present(onto):
    def has(sku, alias):
        return alias in [a for _, a in onto.products[sku].all_aliases()]
    assert has("RICE-KOLAM", "chawal") and has("SUGAR", "saakar") and has("PARLEG", "parle g")
    assert "tel" in onto.generic_terms and onto.generic_terms["tel"].default == "OIL-SUNFLOWER"
    assert onto.generic_terms["dal"].default is None


def test_turtle_and_jsonld_roundtrip(onto):
    g = Graph().parse(data=onto.to_turtle(), format="turtle")
    assert len(g) > 1000
    doc = onto.to_jsonld()
    assert isinstance(doc, list | dict)


def test_validation_rejects_bad_relation(tmp_path, onto):
    with open("app/kg/ontology.yaml", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw["relations"]["owes"]["range"] = "Planet"
    p = tmp_path / "o.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(OntologyError, match="not a class"):
        load_ontology(schema_path=p)


def test_validation_rejects_alias_collision(tmp_path):
    prods = {"products": [
        {"sku": "A", "name": "A", "cat": "grains", "unit": "kg", "price": 1, "aliases": {"en": ["same"]}},
        {"sku": "B", "name": "B", "cat": "grains", "unit": "kg", "price": 1, "aliases": {"hi": ["saame"]}},
    ]}
    p = tmp_path / "p.yaml"
    p.write_text(yaml.safe_dump(prods), encoding="utf-8")
    with pytest.raises(OntologyError, match="declare it generic"):
        load_ontology(products_path=p)


@pytest.mark.parametrize("row,msg", [
    ({"sku": "A", "name": "A", "cat": "nope", "unit": "kg", "price": 1}, "unknown category"),
    ({"sku": "A", "name": "A", "cat": "grains", "unit": "bushel", "price": 1}, "unknown unit"),
    ({"sku": "A", "name": "A", "cat": "grains", "unit": "kg", "price": 0}, "price"),
    ({"sku": "A", "name": "A", "cat": "grains", "unit": "kg", "price": 1, "aliases": {"xx": ["a"]}}, "language"),
])
def test_validation_rejects_bad_products(tmp_path, row, msg):
    p = tmp_path / "p.yaml"
    p.write_text(yaml.safe_dump({"products": [row]}), encoding="utf-8")
    with pytest.raises(OntologyError, match=msg):
        load_ontology(products_path=p)


def test_check_node_and_edge(onto):
    with pytest.raises(OntologyError, match="unknown class"):
        onto.check_node("Planet", {})
    with pytest.raises(OntologyError, match="missing required"):
        onto.check_node("Customer", {"name": "x"})
    with pytest.raises(OntologyError, match="unknown properties"):
        onto.check_node("Shop", {"name": "x", "colour": "red"})
    with pytest.raises(OntologyError, match="not in"):
        onto.check_node("LedgerEvent", {"kind": "gift", "amount": 1, "date": "2025-01-01", "status": "active", "customer_id": "c"})
    with pytest.raises(OntologyError, match="expects"):
        onto.check_edge("owes", "Shop", "Customer")
    with pytest.raises(OntologyError, match="unknown relation"):
        onto.check_edge("likes", "Shop", "Customer")


# ------------------------------------------------------------------ graph store
def test_graph_store_roundtrip(tmp_path, onto):
    db = str(tmp_path / "g.db")
    s = NetworkXSQLiteStore(onto, db)
    prov = Provenance(source="utt-1", confidence=0.9, method="model")
    s.upsert_node("shop:1", "Shop", {"name": "Test Kirana"}, prov)
    s.upsert_node("cust:1", "Customer", {"name": "Ramesh Patel", "given_name": "Ramesh"}, prov)
    with s.batch():
        s.upsert_edge("owes:cust:1", "cust:1", "owes", "shop:1", {"amount": 100}, prov)
        s.upsert_edge("owes:cust:1", "cust:1", "owes", "shop:1", {"amount": 250}, prov)  # upsert replaces
    assert [e.props["amount"] for e in s.edges("owes")] == [250]
    s2 = NetworkXSQLiteStore(onto, db)  # reload from SQLite
    assert s2.get_node("cust:1").props["name"] == "Ramesh Patel"
    e = s2.edges(rel="owes", src="cust:1")[0]
    assert e.prov.source == "utt-1" and e.prov.method == "model" and e.prov.confidence == 0.9
    assert s2.edges(dst="shop:1")[0].id == "owes:cust:1"
    assert s2.edges(src="nope") == [] and s2.edges(dst="nope") == []
    s2.remove_edge("owes:cust:1")
    s2.remove_edge("missing")
    assert s2.edges("owes") == []
    assert s2.stats()["nodes"] == {"Shop": 1, "Customer": 1}
    assert len(s2.nodes("Customer")) == 1 and s2.get_node("x") is None
    s2.clear()
    assert s2.nodes() == []


def test_graph_store_validates(onto):
    s = NetworkXSQLiteStore(onto)
    prov = Provenance.seed("t")
    s.upsert_node("shop:1", "Shop", {"name": "S"}, prov)
    with pytest.raises(KeyError):
        s.upsert_edge("e", "shop:1", "owes", "cust:404", {}, prov)
    s.upsert_node("cust:1", "Customer", {"name": "A", "given_name": "A"}, prov)
    with pytest.raises(OntologyError):
        s.upsert_edge("e", "shop:1", "owes", "cust:1", {}, prov)
    with pytest.raises(ValueError, match="already exists"):
        s.upsert_node("shop:1", "Customer", {"name": "A", "given_name": "A"}, prov)


# ------------------------------------------------------------------ names
def test_romanize_devanagari_and_gujarati():
    assert romanize("रमेश भाई को 2 किलो चावल उधार") == "ramesh bhaaee ko 2 kilo chaaval udhaar"
    assert romanize("મીના બેન ને 500 આપ્યા") == "meenaa ben ne 500 aapyaa"
    assert romanize("२०० रुपये") == "200 rupaye"
    assert romanize("plain latin") == "plain latin"
    assert canon(romanize("चावल")) == canon("chawal")


def test_canon_and_phonetics():
    assert canon("Chaawal") == canon("chawal") == "chaval"
    assert canon("udhaar") == canon("udhar")
    assert canon("Parle-G") == "parleg"
    assert phonetic_key("Kishore") == phonetic_key("Kishor") == phonetic_key("kisor")
    assert phonetic_key("") == ""
    assert tokenize("₹500 diye, Parle-G!") == ["₹", "500", "diye", "parle-g"]


def test_similarity_and_honorifics():
    assert similarity("Kishore", "Kishor") > 0.95
    assert similarity("Suresh", "Mahesh") < 0.8
    assert similarity("", "x") == 0.0
    assert strip_honorifics(["rameshbhai"]) == (["ramesh"], "m")
    assert strip_honorifics(["Meena", "ben"]) == (["meena"], "f")
    assert strip_honorifics(["Shri", "Kishore", "ji"]) == (["kishore"], "m")
    assert strip_honorifics(["smt", "kavita"]) == (["kavita"], "f")
