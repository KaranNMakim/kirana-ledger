import pytest

from app.core.ledger import LedgerError
from app.core.models import ConfirmRequest, ItemOverride
from app.core.service import KiranaApp
from app.settings import Settings


@pytest.fixture
def app():
    a = KiranaApp(Settings(db_path=":memory:"))
    from app.kg.provenance import Provenance
    prov = Provenance.seed("test")
    for name, g in [("Ramesh Patel", "m"), ("Ramesh Shah", "m"), ("Meena Joshi", "f"), ("Suresh Mehta", "m"),
                    ("Kishore Desai", "m")]:
        a.ledger.add_customer(name, prov, gender=g)
    sugar = a.ledger.line_item("SUGAR", 10)
    a.ledger.record_event("credit_sale", "cust:kishore-desai", sugar.amount * 4, a.ledger.today(), [sugar], prov)
    return a


def test_auto_save_high_confidence(app):
    r = app.pipeline.handle("Meena ben ne 500 diye")
    assert r.decision == "saved" and r.event.kind == "payment" and r.event.amount == 500
    assert r.event.customer_id == "cust:meena-joshi" and r.event.provenance["source"] == r.utterance_id
    assert app.ledger.balance("cust:meena-joshi") == -500


def test_multi_item_sale_uses_price_list(app):
    r = app.pipeline.handle("Suresh ka 3 packet Parle-G aur 1 litre tel likh do")
    assert r.decision == "saved"
    assert [i.sku for i in r.event.items] == ["PARLEG", "OIL-SUNFLOWER"]
    assert r.event.amount == 3 * 10 + 150 and r.event.amount_source == "price_list"


def test_ambiguous_customer_needs_disambiguation(app):
    r = app.pipeline.handle("Ramesh bhai ko 2 kilo chawal udhaar")
    assert r.decision == "needs_confirmation" and r.pending_id
    q = r.interpretation.questions[0]
    assert q.field == "customer" and {o["id"] for o in q.options} == {"cust:ramesh-patel", "cust:ramesh-shah"}
    assert any("could be 2 customers" in x for x in r.reasons)
    done = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id, customer_id="cust:ramesh-shah"))
    assert done.decision == "saved" and done.event.customer_id == "cust:ramesh-shah"
    assert done.event.provenance["method"] == "human" and done.event.amount == 120
    with pytest.raises(LedgerError, match="unknown or expired"):
        app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id, customer_id="cust:ramesh-shah"))


def test_half_settlement_confirms_with_computed_amount(app):
    r = app.pipeline.handle("aaj Kishore ne aadha hisaab chukta kiya")
    assert r.decision == "needs_confirmation"
    assert r.interpretation.amount == 900.0 and r.interpretation.amount_source == "balance_fraction"
    assert any("half of balance" in x for x in r.reasons)
    done = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id))
    assert done.event.amount == 900.0 and app.ledger.balance("cust:kishore-desai") == 900.0


def test_new_customer_flow(app):
    r = app.pipeline.handle("Babulal ji ko 1 kilo cheeni")
    assert r.decision == "needs_confirmation" and r.interpretation.customer.status == "new"
    done = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id, new_customer_name="Babulal"))
    assert done.event.customer_name == "Babulal" and app.store.get_node(done.event.customer_id).props[
        "created_from"] == r.utterance_id


def test_ambiguous_product_and_item_override(app):
    r = app.pipeline.handle("Meena ben ko 1 kilo dal")
    assert r.decision == "needs_confirmation"
    assert any(q.field == "items[0]" and len(q.options) == 5 for q in r.interpretation.questions)
    with pytest.raises(LedgerError, match="choose a product"):
        app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id))
    done = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id,
                                               items=[ItemOverride(sku="DAL-MOONG", qty=1)]))
    assert done.event.items[0].sku == "DAL-MOONG" and done.event.amount == 130


def test_query_answered_without_saving(app):
    r = app.pipeline.handle("Kishore ka kitna baaki hai")
    assert r.decision == "answered" and "₹1,800" in r.answer
    app.pipeline.handle("Kishore ne 100 diye")
    assert "Last payment ₹100" in app.pipeline.handle("Kishore ka kitna baaki hai").answer
    amb = app.pipeline.handle("Ramesh ka kitna baaki hai")
    assert amb.decision == "needs_confirmation"
    with pytest.raises(LedgerError, match="pick credit_sale"):
        app.pipeline.confirm(ConfirmRequest(pending_id=amb.pending_id, customer_id="cust:ramesh-patel"))


def test_missing_amount_and_cancel(app):
    r = app.pipeline.handle("Meena ben ne paise diye")
    assert r.decision == "needs_confirmation" and any(q.field == "amount" for q in r.interpretation.questions)
    with pytest.raises(LedgerError, match="amount is required"):
        app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id))
    ok = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id, amount=250))
    assert ok.event.amount == 250
    r2 = app.pipeline.handle("koi ne kuch")
    assert app.pipeline.confirm(ConfirmRequest(pending_id=r2.pending_id, cancel=True)).decision == "rejected"


def test_intent_override_and_no_customer(app):
    r = app.pipeline.handle("500")
    assert r.decision == "needs_confirmation"
    assert any(q.prompt == "Whose account is this?" for q in r.interpretation.questions)
    with pytest.raises(LedgerError, match="choose a customer"):
        app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id))
    done = app.pipeline.confirm(ConfirmRequest(pending_id=r.pending_id, customer_id="cust:suresh-mehta",
                                               intent="payment"))
    assert done.event.kind == "payment" and done.event.amount == 500


def test_half_balance_without_balance(app):
    r = app.pipeline.handle("Meena ben ne aadha hisaab chukta kiya")
    assert r.decision == "needs_confirmation" and "no balance" in " ".join(r.reasons)
    amb = app.pipeline.handle("Ramesh ne pura hisaab chukta kiya")
    assert "need the customer first" in " ".join(amb.reasons)


def test_return_event(app):
    r = app.pipeline.handle("Meena ben ne 1 packet Maggi wapas kiya")
    assert r.decision == "saved" and r.event.kind == "return" and r.event.amount == 14


def test_generated_demo_data_profiles():
    from data.generate import generate

    a, summary = generate(Settings(db_path=":memory:"), verbose=False)
    assert summary["customers"] == 60 and summary["events"] > 2000
    ins = a.insights.shop_insights()
    assert ins["totals"]["customers_owing"] > 30 and ins["late_payers"]
    assert {s["id"] for s in ins["seasons"]} >= {"diwali", "wedding_winter"}
    assert ins["seasonality"]["festive_credit_per_day"] > ins["seasonality"]["normal_credit_per_day"]
    chronic = a.insights.profile("cust:kishore-desai")["pattern"]
    prompt = a.insights.profile("cust:ramesh-patel")["pattern"]
    assert chronic["score"] < 40 < 75 <= prompt["score"]
    g = a.insights.graph_elements(limit=10)
    assert sum(1 for n in g["nodes"] if n["data"]["type"] == "Customer") == 10
    one = a.insights.graph_elements(customer_id="cust:kishore-desai")
    assert any(e["data"]["rel"] == "bought" for e in one["edges"])
    # reproducible
    _, again = generate(Settings(db_path=":memory:"), verbose=False)
    assert again["events"] == summary["events"] and again["outstanding"] == summary["outstanding"]


def test_prefix_lookalike_product_is_not_auto_saved(app):
    # regression from the untuned eval: "chicken" once fuzzy-matched "chickpea" and saved silently
    r = app.pipeline.handle("Meena ben ko 1 kilo chicken")
    assert r.decision == "needs_confirmation"
    assert app.catalog.resolve("chicken").confidence < 0.75
