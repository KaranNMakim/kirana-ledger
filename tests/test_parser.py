import datetime as dt

import pytest

from app.core.dates import parse_relative_date
from app.kg.llm import MockLLMClient, get_llm_client

from .conftest import TODAY


def items(p):
    return [(i.product_text, i.qty, i.unit_text) for i in p.items]


# ------------------------------------------------------------------ the four examples from the brief
def test_spec_credit_sale(parse):
    p = parse("Ramesh bhai ko 2 kilo chawal udhaar")
    assert p.intent == "credit_sale" and p.intent_confidence > 0.9
    assert p.customer_text == "ramesh bhai"
    assert items(p) == [("chawal", 2.0, "kilo")]


def test_spec_payment(parse):
    p = parse("Meena ben ne 500 diye")
    assert (p.intent, p.customer_text, p.amount) == ("payment", "meena ben", 500.0)
    assert p.items == []


def test_spec_multi_item(parse):
    p = parse("Suresh ka 3 packet Parle-G aur 1 litre tel likh do")
    assert p.intent == "credit_sale" and p.customer_text == "suresh"
    assert items(p) == [("parle-g", 3.0, "packet"), ("tel", 1.0, "litre")]


def test_spec_half_settlement(parse):
    p = parse("aaj Kishore ne aadha hisaab chukta kiya")
    assert p.intent == "payment" and p.customer_text == "kishore"
    assert p.amount is None and p.amount_expr == "half_balance" and p.amount_confidence < 0.75
    assert p.days_ago == 0 and p.date_text == "aaj"


# ------------------------------------------------------------------ scripts & languages
def test_devanagari_input(parse):
    p = parse("रमेश भाई को 2 किलो चावल उधार")
    assert p.intent == "credit_sale" and p.customer_text.startswith("ramesh")
    assert p.items[0].qty == 2.0


def test_gujarati_transliterated(parse):
    p = parse("Rameshbhai na khata ma 2 kilo khand lakhi do")
    assert p.intent == "credit_sale" and p.customer_text == "rameshbhai"
    assert items(p) == [("khand", 2.0, "kilo")]
    q = parse("Meenaben e 500 rupiya aapya")
    assert (q.intent, q.amount, q.amount_confidence) == ("payment", 500.0, 0.95)


def test_gujarati_script(parse):
    p = parse("મીના બેન ને 500 આપ્યા")
    assert p.intent == "payment" and p.amount == 500.0


# ------------------------------------------------------------------ numbers, units, amounts
@pytest.mark.parametrize("text,qty,unit", [
    ("Anil ko paav kilo ghee", 1.0, "paav"),
    ("Anil ko dedh kilo cheeni", 1.5, "kilo"),
    ("Anil ko aadha kilo jeera", 0.5, "kilo"),
    ("Anil ko do packet maggi", 2.0, "packet"),
    ("Anil ko ek dozen ande", 1.0, "dozen"),
    ("Anil ko 500 gram besan", 500.0, "gram"),
    ("Anil ko dhai kilo aata", 2.5, "kilo"),
])
def test_quantities(parse, text, qty, unit):
    p = parse(text)
    assert (p.items[0].qty, p.items[0].unit_text) == (qty, unit)


def test_number_words_amount(parse):
    assert parse("parso Ravi se do sau rupaye mile").amount == 200.0
    assert parse("Ravi ne dedh sau diye").amount == 150.0
    assert parse("Ravi ne 2 hazaar diye").amount == 2000.0
    assert parse("Ravi ne 1,200 diye").amount == 1200.0


def test_line_amount_and_post_quantity(parse):
    p = parse("Ramesh ko 50 rupaye ka tel aur 2 kilo aata")
    assert p.items[0].amount == 50.0 and p.items[1].qty == 2.0
    q = parse("Mahesh ko 2 kilo cheeni 1 kilo dal")
    assert items(q) == [("cheeni", 2.0, "kilo"), ("dal", 1.0, "kilo")]
    r = parse("Ramesh Patel ko dal 1 kilo")
    assert items(r) == [("dal", 1.0, "kilo")]


def test_amount_only_sale(parse):
    p = parse("Deepak ka 500 ka saman likh do")
    assert (p.intent, p.customer_text, p.amount, p.items) == ("credit_sale", "deepak", 500.0, [])


def test_orphan_word_becomes_fuzzy_item(parse):
    p = parse("Anil ko 2 kilo chwal")
    assert items(p) == [("chwal", 2.0, "kilo")]
    assert p.items[0].confidence < 0.9


def test_multiple_amounts_lower_confidence(parse):
    p = parse("Ravi ne 200 rupaye aur 300 rupaye diye")
    assert p.amount == 300.0 and p.amount_confidence < 0.75


# ------------------------------------------------------------------ intents
@pytest.mark.parametrize("text,intent", [
    ("Ramesh ka kitna baaki hai", "query"),
    ("Pooja ji 1 packet Maggi wapas kiya", "return"),
    ("Raju ne pura hisaab chukta kar diya", "payment"),
    ("Kishorbhai e aadhu chukvi didhu", "payment"),
    ("Sonal ne 300 UPI se bhej diye", "payment"),
    ("Ramesh ko 1 kilo cheeni de do", "credit_sale"),
    ("Hari ne 200 wapas kiye", "payment"),
    ("Hari 2 kilo chawal", "credit_sale"),
])
def test_intents(parse, text, intent):
    assert parse(text).intent == intent


def test_full_balance_and_half_without_hisaab(parse):
    assert parse("Raju ne pura hisaab chukta kar diya").amount_expr == "full_balance"
    p = parse("Kishorbhai e aadhu chukvi didhu")
    assert p.amount_expr == "half_balance" and p.amount_confidence <= 0.6


def test_mixed_payment_and_sale_needs_confirmation(parse):
    p = parse("Kavita ben ne 1200 diye aur 2 kilo chawal liya")
    assert p.intent_confidence < 0.75 and p.notes


def test_no_cues_defaults(parse):
    assert parse("Hari 500").intent == "payment"
    assert parse("Hari 500").intent_confidence == 0.5
    assert parse("hmm").intent == "query"


def test_customer_without_postposition(parse):
    p = parse("Ramesh bhai 2 kilo chawal")
    assert p.customer_text == "ramesh bhai" and p.customer_confidence == 0.85
    q = parse("500 diye Meena ben ne")
    assert q.customer_text == "meena ben"


def test_name_that_is_also_product(parse):
    p = parse("Sooji ko 1 kilo cheeni")
    assert p.customer_text == "sooji" and items(p) == [("cheeni", 1.0, "kilo")]


# ------------------------------------------------------------------ dates
@pytest.mark.parametrize("phrase,days,conf_min", [
    ("aaj", 0, 0.9), ("kal", 1, 0.8), ("parso", 2, 0.8), ("3 din pehle", 3, 0.8), ("teen din pehle", 3, 0.8),
    ("pichhle hafte", 7, 0.5), ("somvar ko", (TODAY.weekday() - 0) % 7, 0.7),
])
def test_relative_dates(phrase, days, conf_min):
    hit = parse_relative_date(phrase.split(), TODAY)
    assert hit.days_ago == days and hit.confidence >= conf_min


def test_default_date_is_today():
    hit = parse_relative_date(["ramesh"], dt.date(2025, 1, 1))
    assert (hit.days_ago, hit.text) == (0, None)


# ------------------------------------------------------------------ LLM client wiring
def test_mock_llm_client(catalog):
    client = get_llm_client("mock", catalog, "x")
    assert isinstance(client, MockLLMClient) and client.mode == "mock"
    assert client.parse_utterance("Meena ben ne 500 diye", TODAY).method == "rule"
    assert client.draft_text("hi") is None


def test_live_without_key_falls_back(catalog, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    assert get_llm_client("live", catalog, "claude-opus-5-5").mode == "mock"
