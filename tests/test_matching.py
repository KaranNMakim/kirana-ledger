import pytest

from app.core.customers import CustomerMatcher


# ------------------------------------------------------------------ products
@pytest.mark.parametrize("text,sku", [
    ("chawal", "RICE-KOLAM"), ("chokha", "RICE-KOLAM"), ("tandul", "RICE-KOLAM"), ("saakar", "SUGAR"),
    ("cheeni", "SUGAR"), ("parle-g", "PARLEG"), ("Parle G", "PARLEG"), ("tuvar dal", "DAL-TOOR"),
    ("sing tel", "OIL-GROUNDNUT"), ("sarson ka tel", "OIL-MUSTARD"), ("चावल", "RICE-KOLAM"),
])
def test_exact_alias(catalog, text, sku):
    r = catalog.resolve(text)
    assert (r.match, r.sku) == ("exact", sku)


def test_generic_with_default_and_ambiguous(catalog):
    tel = catalog.resolve("tel")
    assert (tel.match, tel.sku) == ("generic_default", "OIL-SUNFLOWER") and tel.confidence < 0.97
    assert len(tel.alternatives) >= 3
    dal = catalog.resolve("dal")
    assert dal.match == "ambiguous" and dal.sku is None and len(dal.alternatives) == 5


def test_fuzzy_and_none(catalog):
    r = catalog.resolve("chwal")
    assert (r.match, r.sku) == ("fuzzy", "RICE-KOLAM")
    assert catalog.resolve("xyzzy").match == "none"
    assert catalog.resolve("").match == "none"


def test_build_item_units_and_price(catalog):
    it = catalog.build_item("2 kilo chawal", "chawal", 2, "kilo", None, 0.95)
    assert (it.sku, it.unit, it.qty_in_product_unit, it.line_amount, it.amount_source) == (
        "RICE-KOLAM", "kg", 2.0, 120.0, "price_list")
    g = catalog.build_item("500 gram besan", "besan", 500, "gram", None, 0.95)
    assert g.qty_in_product_unit == 0.5 and g.line_amount == 50.0
    paav = catalog.build_item("paav ghee", "ghee", 1, "paav", None, 0.95)
    assert paav.qty_in_product_unit == 0.25
    eggs = catalog.build_item("1 dozen ande", "ande", 1, "dozen", None, 0.95)
    assert eggs.qty_in_product_unit == 12 and eggs.line_amount == 84


def test_build_item_flags(catalog):
    stated = catalog.build_item("50 ka tel", "tel", None, None, 50.0, 0.95)
    assert stated.line_amount == 50.0 and stated.amount_source == "stated"
    assert stated.confidence <= 0.7 and "quantity not stated" in stated.notes[0]
    mismatch = catalog.build_item("2 kilo parle", "parle g", 2, "kilo", None, 0.95)
    assert mismatch.confidence < 0.75 and any("unusual" in n for n in mismatch.notes)
    unknown = catalog.build_item("2 kilo xyz", "xyz", 2, "kilo", None, 0.75)
    assert unknown.sku is None and unknown.confidence == 0.0


def test_seed_graph_and_alias_table(catalog, store):
    catalog.seed_graph(store)
    assert len(store.nodes("Product")) == len(catalog.products)
    assert len(store.edges("alias_of")) > 600
    rows = catalog.alias_table("chawal")
    assert rows[0]["sku"] == "RICE-KOLAM" and {"RICE-BASMATI", "RICE-SONA"} <= {r["sku"] for r in rows}
    assert len(catalog.alias_table()) == len(catalog.products)


# ------------------------------------------------------------------ customers
def test_ambiguous_customer_asks(store):
    m = CustomerMatcher(store, balance_of=lambda cid: 100.0)
    r = m.match("Ramesh bhai")
    assert r.status == "ambiguous"
    assert {c.id for c in r.candidates} == {"cust:ramesh-patel", "cust:ramesh-shah"}
    assert all(c.balance == 100.0 for c in r.candidates)


def test_surname_disambiguates(store):
    r = CustomerMatcher(store).match("Ramesh Patel")
    assert (r.status, r.customer_id) == ("matched", "cust:ramesh-patel")


@pytest.mark.parametrize("text,cid", [
    ("Meena ben", "cust:meena-joshi"), ("meenaben", "cust:meena-joshi"), ("Kishor", "cust:kishore-desai"),
    ("Shri Kishore ji", "cust:kishore-desai"), ("sureshbhai", "cust:suresh-mehta"),
    ("मीना बेन", "cust:meena-joshi"), ("Rakesh", "cust:rakesh-verma"),
])
def test_fuzzy_customer_match(store, text, cid):
    r = CustomerMatcher(store).match(text)
    assert (r.status, r.customer_id) == ("matched", cid)


def test_new_and_missing_customer(store):
    m = CustomerMatcher(store)
    new = m.match("Babulal ji")
    assert new.status == "new" and new.name == "Babulal" and new.confidence < 0.75
    assert m.match(None).status == "missing"
    assert m.match("bhai").status == "missing"


def test_gender_hint_penalises(store):
    r = CustomerMatcher(store).match("Suresh ben")
    assert r.status != "matched" or r.confidence < 0.8
