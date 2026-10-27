import datetime as dt

import pytest

from app.core.insights import DISCLAIMER, Season, customer_features, load_seasons, payment_pattern
from app.core.ledger import LedgerError, LedgerService
from app.core.models import EditRequest, ItemOverride
from app.core.reminders import addressed, draft_reminder, record_draft, rupees
from app.kg.provenance import Provenance

from .conftest import TODAY

D = dt.date


@pytest.fixture
def ledger(store, catalog):
    catalog.seed_graph(store)
    return LedgerService(store, catalog, lambda: TODAY)


def P(src="utt-1", method="rule", conf=0.9):
    return Provenance(source=src, method=method, confidence=conf)


# ------------------------------------------------------------------ ledger
def test_record_and_balance(ledger, store):
    rice = ledger.line_item("RICE-KOLAM", 2, "kg")
    assert rice.amount == 120.0
    ev = ledger.record_event("credit_sale", "cust:ramesh-patel", 120, D(2025, 11, 1), [rice], P())
    ledger.record_event("payment", "cust:ramesh-patel", 50, D(2025, 11, 5), [], P("utt-2"))
    assert ledger.balance("cust:ramesh-patel") == 70.0
    owes = store.edges(rel="owes", src="cust:ramesh-patel")[0]
    assert owes.props["amount"] == 70.0 and owes.prov.source == "utt-2"
    assert store.edges(rel="bought", src="cust:ramesh-patel")[0].props["event"] == ev.id
    assert len(store.edges(rel="paid", src="cust:ramesh-patel")) == 1
    assert ev.provenance["source"] == "utt-1" and ev.provenance["method"] == "rule"
    assert [e.kind for e in ledger.events("cust:ramesh-patel")] == ["payment", "credit_sale"]
    assert ledger.last_payment("cust:ramesh-patel").amount == 50
    assert ledger.last_payment("cust:meena-joshi") is None


def test_record_validation(ledger):
    with pytest.raises(LedgerError, match="unknown customer"):
        ledger.record_event("payment", "cust:nobody", 10, TODAY, [], P())
    with pytest.raises(LedgerError, match="positive"):
        ledger.record_event("payment", "cust:ramesh-patel", 0, TODAY, [], P())
    with pytest.raises(LedgerError, match="cannot carry items"):
        ledger.record_event("payment", "cust:ramesh-patel", 10, TODAY, [ledger.line_item("SUGAR", 1)], P())
    with pytest.raises(LedgerError, match="unknown product"):
        ledger.line_item("NOPE", 1)
    with pytest.raises(LedgerError, match="unknown event"):
        ledger.event("evt-999999")


def test_undo_is_provenance_tracked(ledger, store):
    ev = ledger.record_event("credit_sale", "cust:meena-joshi", 45, TODAY, [ledger.line_item("SUGAR", 1)], P())
    undone = ledger.undo(ev.id, reason="wrong customer")
    assert undone.status == "voided" and ledger.balance("cust:meena-joshi") == 0
    h = undone.history[0]
    assert h["action"] == "undo" and h["by"] == "human" and h["source"].startswith("correction:")
    assert store.edges(rel="bought", src="cust:meena-joshi") == []
    assert ledger.events("cust:meena-joshi") == []
    assert len(ledger.events("cust:meena-joshi", include_voided=True)) == 1
    with pytest.raises(LedgerError, match="already voided"):
        ledger.undo(ev.id)


def test_edit_creates_correcting_event(ledger, store):
    ev = ledger.record_event("credit_sale", "cust:suresh-mehta", 120, TODAY, [ledger.line_item("RICE-KOLAM", 2)], P())
    new = ledger.edit(ev.id, EditRequest(items=[ItemOverride(sku="RICE-KOLAM", qty=3)], reason="was 3 kilo"))
    assert new.amount == 180.0 and new.supersedes == ev.id and new.provenance["method"] == "human"
    old = ledger.event(ev.id)
    assert old.status == "voided" and old.superseded_by == new.id
    assert store.edges(rel="corrects", src=new.id)[0].dst == ev.id
    assert ledger.balance("cust:suresh-mehta") == 180.0
    moved = ledger.edit(new.id, EditRequest(customer_id="cust:kishore-desai", amount=200))
    assert ledger.balance("cust:suresh-mehta") == 0 and ledger.balance("cust:kishore-desai") == 200
    assert moved.amount_source == "stated"
    pay = ledger.edit(moved.id, EditRequest(kind="payment"))
    assert pay.items == [] and pay.kind == "payment"
    with pytest.raises(LedgerError):
        ledger.edit(ev.id, EditRequest(amount=1))


def test_add_customer_unique_ids(ledger):
    a = ledger.add_customer("ramesh patel", P(method="human"))
    assert a.id == "cust:ramesh-patel-2" and a.props["name"] == "Ramesh Patel"
    b = ledger.add_customer("Joseph D'Souza", P(method="human"), gender="m")
    assert b.props["surname"] == "D'Souza"
    with pytest.raises(LedgerError):
        ledger.add_customer("  ", P())
    assert ledger.balance(a.id) == 0


# ------------------------------------------------------------------ features & pattern
def ev(kind, amount, d, cid="c"):
    from app.core.models import LedgerEventOut
    return LedgerEventOut(id=f"e{d}{kind}", kind=kind, customer_id=cid, customer_name="C", amount=amount, date=d,
                          status="active", provenance={})


SEASONS = [Season("diwali", "Diwali", "festival", D(2025, 10, 10), D(2025, 10, 25))]


def test_fifo_features():
    events = [ev("credit_sale", 100, D(2025, 9, 1)), ev("credit_sale", 100, D(2025, 9, 11)),
              ev("payment", 50, D(2025, 9, 15)), ev("payment", 150, D(2025, 9, 21)),
              ev("credit_sale", 300, D(2025, 10, 15))]
    f = customer_features(events, TODAY, SEASONS)
    assert f["balance"] == 300 and f["purchases"] == 3 and f["payments"] == 2
    assert f["avg_days_to_pay"] == 15.0  # (20*100 + 10*100) / 200
    assert f["partial_payment_share"] == 0.5
    assert f["oldest_unpaid_days"] == (TODAY - D(2025, 10, 15)).days
    assert f["festive_avg_days"] == (TODAY - D(2025, 10, 15)).days  # unpaid festive purchase counts at its age
    assert f["normal_avg_days"] == 15.0
    assert f["last_payment_amount"] == 150


def test_pattern_good_vs_late():
    good = payment_pattern(customer_features(
        [ev("credit_sale", 100, D(2025, 11, d)) for d in (1, 8, 15)] +
        [ev("payment", 100, D(2025, 11, d + 3)) for d in (1, 8, 15)], TODAY, SEASONS))
    assert good["band"] == "Pays regularly" and good["score"] >= 90
    late = payment_pattern(customer_features(
        [ev("credit_sale", 500, D(2025, 7, 1)), ev("payment", 100, D(2025, 9, 1))], TODAY, SEASONS))
    assert late["band"] == "Frequently late" and late["score"] < 35
    assert late["disclaimer"] == DISCLAIMER and "not a credit score" in DISCLAIMER
    assert "demo heuristic" in late["label"]
    assert all({"factor", "value", "impact", "explanation"} <= set(e) for e in late["evidence"])
    assert late["evidence"][0]["impact"] < 0  # sorted: biggest deduction first
    empty = payment_pattern(customer_features([], TODAY, SEASONS))
    assert empty["score"] == 100 and empty["data_sufficiency"] == "low"


def test_festival_lateness_detected():
    events = []
    for m in (7, 8):  # baseline: paid in 5 days
        events += [ev("credit_sale", 100, D(2025, m, 5)), ev("payment", 100, D(2025, m, 10))]
    events += [ev("credit_sale", 100, D(2025, 10, 12)), ev("payment", 100, D(2025, 11, 25))]  # Diwali: 44 days
    f = customer_features(events, TODAY, SEASONS)
    assert f["festive_avg_days"] == 44 and f["normal_avg_days"] == 5
    p = payment_pattern(f)
    fest = next(e for e in p["evidence"] if e["factor"].startswith("Festival"))
    assert fest["impact"] < 0 and "festivals" in p["summary"]


def test_seasons_file():
    ids = {s.id for s in load_seasons()}
    assert {"diwali", "navratri", "wedding_winter"} <= ids


# ------------------------------------------------------------------ reminders
def test_rupees_and_address():
    assert rupees(123456) == "₹1,23,456" and rupees(999) == "₹999" and rupees(-1500) == "-₹1,500"
    assert addressed("Meena", "f", "gu") == "Meenaben" and addressed("Ramesh", "m", "hinglish") == "Ramesh bhai"
    assert addressed("Ravi", "m", "en") == "Ravi ji"


@pytest.mark.parametrize("lang,tone,needle", [
    ("hinglish", "gentle", "hisaab baaki"), ("hinglish", "firm", "is hafte"), ("gu", "gentle", "baaki chhe"),
    ("gu", "firm", "athvadiya"), ("en", "gentle", "gentle reminder"), ("en", "firm", "this week"),
])
def test_reminder_templates(store, lang, tone, needle):
    f = {"balance": 1240.0, "oldest_unpaid_date": "2025-10-12", "last_payment_date": "2025-11-02",
         "last_payment_amount": 500.0}
    d = draft_reminder({"id": "cust:x", "name": "Ramesh Patel", "given_name": "Ramesh", "gender": "m"}, f,
                       "Shree Ganesh Kirana", lang, tone)
    assert needle in d.text and "₹1,240" in d.text and "₹500" in d.text and "12 Oct" in d.text
    assert d.sent is False and "Draft only" in d.note
    rid = record_draft(store, d.model_copy(update={"customer_id": "cust:ramesh-patel"}))
    assert store.get_node(rid).props["sent"] == "no"


def test_reminder_uses_live_llm_when_amount_kept():
    class Live:
        mode = "live"

        def __init__(self, reply):
            self.reply = reply

        def draft_text(self, _):
            return self.reply

    f = {"balance": 300.0, "oldest_unpaid_date": None, "last_payment_date": None}
    c = {"id": "c", "name": "Meena Joshi", "gender": "f"}
    ok = draft_reminder(c, f, "S", "en", "gentle", llm=Live("Hi Meena ji, ₹300 pending. Thanks!"))
    assert ok.method == "model"
    bad = draft_reminder(c, f, "S", "en", "gentle", llm=Live("Hi, please pay soon"))
    assert bad.method == "rule"  # model dropped the amount → keep the template
