"""Polite WhatsApp-style reminder drafts. Drafts only: nothing is ever sent."""

from __future__ import annotations

import datetime as dt

from app.core.models import Language, ReminderDraft
from app.kg.provenance import Provenance

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def rupees(x: float) -> str:
    """Indian digit grouping: 123456 → ₹1,23,456."""
    n = round(x)
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def short_date(d: dt.date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]}"


def addressed(given: str, gender: str | None, language: Language) -> str:
    if language == "gu":
        return f"{given}{'ben' if gender == 'f' else 'bhai'}"
    if language == "hinglish":
        return f"{given} {'ji' if gender == 'f' else 'bhai'}"
    return f"{given} ji"


TEMPLATES: dict[tuple[Language, str], str] = {
    ("hinglish", "gentle"): ("Namaste {name} 🙏\n{shop} se yaad dila rahe hain: aapka {amount} ka hisaab baaki hai"
                             "{since}.{last} Jab suvidha ho tab de dijiyega, cash ya UPI dono chalega.\nDhanyavaad!"),
    ("hinglish", "firm"): ("Namaste {name} 🙏\n{shop} se: aapka {amount} ka hisaab kaafi samay se baaki hai{since}."
                           "{last} Kripya is hafte tak chukta kar dijiye. Koi dikkat ho to bata dijiye, "
                           "thoda-thoda bhi chalega.\nDhanyavaad."),
    ("gu", "gentle"): ("Jai Shree Krishna {name} 🙏\n{shop} taraf thi yaad apaviye chhiye: tamaru {amount} nu "
                       "hisaab baaki chhe{since}.{last} Anukulta hoy tyare aapi dejo, rokda ke UPI bane chalse."
                       "\nAabhar!"),
    ("gu", "firm"): ("Jai Shree Krishna {name} 🙏\n{shop} taraf thi: tamaru {amount} nu hisaab ghana samay thi "
                     "baaki chhe{since}.{last} Krupa kari aa athvadiya ma chukvi dejo. Taklif hoy to kahejo, "
                     "thodu-thodu pan chalse.\nAabhar."),
    ("en", "gentle"): ("Namaste {name} 🙏\nA gentle reminder from {shop}: {amount} is pending on your account"
                       "{since}.{last} Please pay whenever convenient, cash or UPI.\nThank you!"),
    ("en", "firm"): ("Namaste {name} 🙏\nFrom {shop}: {amount} has been pending on your account for a while"
                     "{since}.{last} Kindly clear it this week. If that is difficult, part payments are welcome."
                     "\nThank you."),
}
SINCE = {"hinglish": " ({d} se)", "gu": " ({d} thi)", "en": " (since {d})"}
LAST = {"hinglish": " Pichhla payment {amt} ({d}) ke liye shukriya.",
        "gu": " Chhellu payment {amt} ({d}) mate aabhar.",
        "en": " Thank you for your last payment of {amt} on {d}."}


def draft_reminder(customer: dict, features: dict, shop_name: str, language: Language, tone: str,
                   llm=None) -> ReminderDraft:
    given = customer.get("given_name") or customer["name"].split()[0]
    name = addressed(given, customer.get("gender"), language)
    balance = features["balance"]
    since = ""
    if features.get("oldest_unpaid_date"):
        since = SINCE[language].format(d=short_date(dt.date.fromisoformat(features["oldest_unpaid_date"])))
    last = ""
    if features.get("last_payment_date"):
        last = LAST[language].format(amt=rupees(features["last_payment_amount"]),
                                     d=short_date(dt.date.fromisoformat(features["last_payment_date"])))
    text = TEMPLATES[(language, tone)].format(name=name, shop=shop_name, amount=rupees(balance), since=since,
                                              last=last)
    method = "rule"
    if llm is not None and getattr(llm, "mode", "mock") == "live":
        lang_name = {"en": "English", "hinglish": "Hinglish (Roman script)", "gu": "Gujarati in Roman script"}
        better = llm.draft_text(
            f"Rewrite this WhatsApp payment reminder from a kirana shopkeeper to a regular customer in "
            f"{lang_name[language]}, {tone} and respectful, under 60 words. Keep the amount {rupees(balance)} "
            f"exactly. Return only the message.\n\n{text}")
        if better and rupees(balance) in better:
            text, method = better.strip(), "model"
    return ReminderDraft(customer_id=customer["id"], customer_name=customer["name"], language=language,
                         tone=tone, balance=balance, text=text, method=method)


def record_draft(store, draft: ReminderDraft) -> str:
    """Keep a provenance-tracked record of the draft in the graph (never sent)."""
    rid = f"reminder:{draft.customer_id}:{len(store.edges(rel='about', dst=draft.customer_id)) + 1}"
    prov = Provenance(source=f"draft:{rid}", method=draft.method, confidence=1.0)
    store.upsert_node(rid, "Reminder", {"language": draft.language, "text": draft.text, "balance": draft.balance,
                                        "tone": draft.tone, "customer_id": draft.customer_id, "sent": "no"}, prov)
    store.upsert_edge(f"about:{rid}", rid, "about", draft.customer_id, {}, prov)
    return rid
