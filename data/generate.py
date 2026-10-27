"""Seeded, reproducible synthetic ledger: 1 shop, 60 customers, 6 months (Jun–Nov 2025).

    python -m data.generate            # writes data/kirana.db (path from KIRANA_DB)

SYNTHETIC ONLY: names are common Indian first names + surnames combined at random by hand; no real people.
Personas drive payment behaviour; Diwali / Navratri / wedding windows (data/calendar.yaml) boost volume and
basket mix, and "festival_late" customers clear festive purchases much later.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from app.core.insights import load_seasons
from app.core.service import KiranaApp
from app.kg.provenance import Provenance
from app.settings import DEMO_TODAY, Settings

SEED = 42
START = dt.date(2025, 6, 1)

# (name, gender, persona, locality)
CUSTOMERS = [
    ("Ramesh Patel", "m", "prompt", "Shivam Society"), ("Ramesh Shah", "m", "chronic", "Gali 3"),
    ("Meena Joshi", "f", "regular", "Shivam Society"), ("Suresh Mehta", "m", "regular", "Station Road"),
    ("Kishore Desai", "m", "chronic", "Gali 1"), ("Rakesh Verma", "m", "prompt", "Gali 2"),
    ("Mahesh Parmar", "m", "slow", "Krishna Nagar"), ("Mukesh Solanki", "m", "regular", "Krishna Nagar"),
    ("Sunita Rathod", "f", "prompt", "Gali 4"), ("Sunil Gupta", "m", "slow", "Station Road"),
    ("Kavita Shah", "f", "regular", "Shivam Society"), ("Kavitha Nair", "f", "prompt", "Ambika Flats"),
    ("Anil Yadav", "m", "regular", "Gali 2"), ("Anita Yadav", "f", "prompt", "Gali 2"),
    ("Pooja Sharma", "f", "prompt", "Ambika Flats"), ("Priya Pillai", "f", "regular", "Ambika Flats"),
    ("Hari Prasad", "m", "slow", "Gali 5"), ("Ravi Kumar", "m", "regular", "Station Road"),
    ("Raju Bhatt", "m", "prompt", "Gali 1"), ("Deepak Chauhan", "m", "slow", "Krishna Nagar"),
    ("Sonal Trivedi", "f", "prompt", "Shivam Society"), ("Nilesh Pandya", "m", "regular", "Gali 3"),
    ("Jignesh Modi", "m", "festival_late", "Gali 4"), ("Hetal Dave", "f", "festival_late", "Shivam Society"),
    ("Bhavna Panchal", "f", "regular", "Gali 5"), ("Alpesh Thakor", "m", "slow", "Gali 6"),
    ("Dinesh Chaudhary", "m", "festival_late", "Station Road"), ("Geeta Bhatia", "f", "prompt", "Ambika Flats"),
    ("Farhan Shaikh", "m", "regular", "Gali 6"), ("Salma Khan", "f", "prompt", "Gali 6"),
    ("Imran Pathan", "m", "chronic", "Gali 6"), ("Joseph D'Souza", "m", "prompt", "Ambika Flats"),
    ("Lata Kulkarni", "f", "regular", "Krishna Nagar"), ("Vijay Patil", "m", "slow", "Gali 2"),
    ("Sachin Jadhav", "m", "regular", "Gali 3"), ("Ganesh More", "m", "prompt", "Gali 1"),
    ("Manoj Tiwari", "m", "festival_late", "Station Road"), ("Rekha Mishra", "f", "festival_late", "Gali 4"),
    ("Prakash Rao", "m", "regular", "Ambika Flats"), ("Lakshmi Iyer", "f", "prompt", "Ambika Flats"),
    ("Arjun Reddy", "m", "regular", "Station Road"), ("Harish Vyas", "m", "slow", "Gali 5"),
    ("Chirag Patel", "m", "prompt", "Shivam Society"), ("Nikita Agarwal", "f", "regular", "Shivam Society"),
    ("Rohit Jain", "m", "prompt", "Station Road"), ("Komal Bhanushali", "f", "regular", "Gali 3"),
    ("Yogesh Rana", "m", "slow", "Gali 4"), ("Usha Gohil", "f", "chronic", "Gali 5"),
    ("Bharat Makwana", "m", "festival_late", "Krishna Nagar"), ("Paresh Vaghela", "m", "regular", "Gali 1"),
    ("Jayesh Barot", "m", "prompt", "Gali 2"), ("Kiran Soni", "f", "regular", "Krishna Nagar"),
    ("Asha Prajapati", "f", "prompt", "Gali 5"), ("Vinod Mistry", "m", "chronic", "Gali 6"),
    ("Mehul Sanghvi", "m", "regular", "Shivam Society"), ("Tejal Kapadia", "f", "prompt", "Ambika Flats"),
    ("Naresh Rawal", "m", "slow", "Gali 3"), ("Hemant Joshi", "m", "regular", "Gali 4"),
    ("Daksha Mehta", "f", "prompt", "Station Road"), ("Pankaj Dubey", "m", "slow", "Gali 1"),
]

# purchases per 30 days, (min,max) pay lag days, P(partial), P(never paid by today)
PERSONAS = {
    "prompt": (4.0, (2, 9), 0.05, 0.0),
    "regular": (3.5, (7, 22), 0.2, 0.02),
    "slow": (3.0, (20, 45), 0.4, 0.05),
    "chronic": (3.0, (40, 95), 0.6, 0.3),
    "festival_late": (3.5, (5, 14), 0.15, 0.0),
}

STAPLES = {"RICE-KOLAM": 6, "ATTA": 6, "SUGAR": 5, "DAL-TOOR": 4, "OIL-SUNFLOWER": 4, "OIL-GROUNDNUT": 3,
           "SALT-TATA": 3, "MILK-TAAZA": 6, "TEA-WAGHBAKRI": 3, "PARLEG": 4, "MAGGI": 3, "ONION": 4,
           "POTATO": 4, "TOMATO": 3, "DAL-MOONG": 2, "BESAN": 2, "HALDI": 1, "MIRCHI-POWDER": 1, "JEERA": 1,
           "SOAP-LIFEBUOY": 2, "DETERGENT-SURF": 2, "VIM-BAR": 2, "BREAD": 3, "EGGS": 2, "CURD": 2,
           "POHA": 2, "BUTTER": 1, "TOOTHPASTE": 1, "MATCHBOX": 1, "CHIPS": 2, "GOODDAY": 1, "BAJRA": 1,
           "GHEE": 1, "JAGGERY": 1, "SOOJI": 1, "AGARBATTI": 1, "SHAMPOO": 1, "NAMKEEN": 1}
BOOSTS = {
    "diwali": {"SUGAR": 6, "GHEE": 6, "MAIDA": 5, "BESAN": 4, "KAJU": 5, "BADAM": 5, "KISHMISH": 4, "SOOJI": 3,
               "DIYA": 6, "RANGOLI": 4, "AGARBATTI": 3, "OIL-GROUNDNUT": 4, "ELAICHI": 2, "COPRA": 2},
    "navratri": {"SABUDANA": 6, "SALT-ROCK": 4, "PEANUTS": 5, "COCONUT": 4, "KUMKUM": 3, "AGARBATTI": 3},
    "raksha_bandhan": {"SUGAR": 4, "GHEE": 4, "MAIDA": 3, "KAJU": 2, "BADAM": 2},
    "wedding_winter": {"RICE-BASMATI": 5, "OIL-GROUNDNUT": 5, "SUGAR": 4, "DAL-TOOR": 4, "GHEE": 4,
                       "DAL-CHANA": 2, "RICE-KOLAM": 3},
    "wedding_summer": {"RICE-BASMATI": 5, "OIL-GROUNDNUT": 4, "SUGAR": 4, "DAL-TOOR": 3, "GHEE": 3},
}
HOW = {"kg": [0.5, 1, 1, 2, 2, 3, 5], "l": [1, 1, 2], "packet": [1, 1, 2, 3], "pcs": [1, 2, 6, 12],
       "bar": [1, 2, 4], "bottle": [1], "box": [1]}
UNIT_WORD = {"kg": "kilo", "l": "litre", "packet": "packet", "pcs": "", "bar": "", "bottle": "bottle", "box": ""}


def _season_of(d: dt.date, seasons) -> str | None:
    return next((s.id for s in seasons if s.contains(d)), None)


def generate(settings: Settings, verbose: bool = True) -> tuple[KiranaApp, dict]:
    rng = random.Random(SEED)
    db = Path(settings.db_path)
    if settings.db_path != ":memory:":
        for p in (db, Path(str(db) + "-journal")):
            if p.exists():
                p.unlink()
    app = KiranaApp(settings)
    today = settings.today()
    end = min(today, DEMO_TODAY) if settings.today_override.lower() != "real" else today
    seasons = load_seasons()
    ledger, catalog = app.ledger, app.catalog
    prov = Provenance.seed("ledger-generator")
    events: list[tuple] = []  # (date, order, kind, cid, amount, items, utterance)

    with app.store.batch():
        ids = {}
        for name, gender, _persona, loc in CUSTOMERS:
            ids[name] = ledger.add_customer(name, prov, gender=gender, locality=loc).id
        # a few families have a wedding: one big purchase in a wedding window
        wedding_families = set(rng.sample([c[0] for c in CUSTOMERS], 6))

        for name, gender, persona, _ in CUSTOMERS:
            cid = ids[name]
            rate, (lag_lo, lag_hi), p_partial, p_never = PERSONAS[persona]
            alias_name = name.split()[0] + (" ben" if gender == "f" else " bhai")
            d = START + dt.timedelta(days=rng.randint(0, 6))
            last_due = d  # payments clear purchases in order (FIFO), so due dates never go backwards
            while d <= end:
                season = _season_of(d, seasons)
                weights = dict(STAPLES)
                for sku, w in BOOSTS.get(season or "", {}).items():
                    weights[sku] = weights.get(sku, 0) + w
                n_items = rng.choice([1, 1, 2, 2, 3, 4] + ([3, 4, 5] if season else []))
                skus = list(dict.fromkeys(rng.choices(list(weights), weights=list(weights.values()), k=n_items)))
                big = season and season.startswith("wedding") and name in wedding_families and rng.random() < 0.5
                items = []
                for sku in skus:
                    p = catalog.products[sku]
                    q = rng.choice(HOW.get(p.unit, [1])) * (3 if big else 1)
                    items.append(ledger.line_item(sku, q, p.unit))
                amount = round(sum(i.amount for i in items), 2)
                utt = f"{alias_name} ko " + " aur ".join(
                    f"{i.qty:g} {UNIT_WORD.get(i.unit, '')} {catalog.products[i.sku].aliases.get('hi', catalog.products[i.sku].aliases.get('en', [i.name]))[0]}".replace("  ", " ")
                    for i in items) + " udhaar"
                events.append((d, 0, "credit_sale", cid, amount, items, utt))

                # payment plan for this purchase
                lag = rng.randint(lag_lo, lag_hi)
                if persona == "festival_late" and season:
                    lag += rng.randint(25, 45)
                if persona == "chronic" and season:
                    lag += rng.randint(10, 30)
                pay_on = max(last_due, d + dt.timedelta(days=lag))
                if rng.random() < p_never:
                    # short-pays: a fraction is paid, the rest is carried indefinitely
                    events.append((pay_on, 1, "payment", cid, round(amount * rng.uniform(0.1, 0.4), 2), [], None))
                    last_due = pay_on
                elif rng.random() < p_partial:
                    first = round(amount * rng.uniform(0.4, 0.7) / 10) * 10 or amount
                    second_on = pay_on + dt.timedelta(days=int(lag * rng.uniform(0.6, 1.4)) + 3)
                    events.append((pay_on, 1, "payment", cid, first, [], None))
                    events.append((second_on, 1, "payment", cid, round(amount - first, 2), [], None))
                    last_due = pay_on
                else:
                    events.append((pay_on, 1, "payment", cid, amount, [], None))
                    last_due = pay_on
                if rng.random() < 0.03 and len(items) > 1:  # occasional return of one item
                    it = items[-1]
                    events.append((d + dt.timedelta(days=rng.randint(1, 3)), 2, "return", cid, it.amount,
                                   [it], f"{alias_name} ne {catalog.products[it.sku].name} wapas kiya"))
                gap = rng.expovariate(rate / 30) * (0.6 if season else 1.0)
                d += dt.timedelta(days=max(1, round(gap)))

        # merge same-day payments per customer; drop anything after "today"
        merged: dict[tuple, float] = defaultdict(float)
        rest = []
        for ev in events:
            if ev[0] > end:
                continue
            if ev[2] == "payment":
                merged[(ev[0], ev[3])] += ev[4]
            else:
                rest.append(ev)
        for (d, cid), amt in merged.items():
            amt = round(amt / 10) * 10 if amt > 50 else round(amt, 2)  # shopkeepers round to ₹10
            if amt > 0:
                rest.append((d, 1, "payment", cid, amt, [], None))
        rest.sort(key=lambda e: (e[0], e[1], e[3]))
        for d, _, kind, cid, amount, items, utt in rest:
            ledger.record_event(kind, cid, amount, d, items if kind != "payment" else [], prov,
                                utterance=utt, amount_source="price_list" if kind != "payment" else "stated")

    summary = {
        "seed": SEED, "period": [START.isoformat(), end.isoformat()], "customers": len(CUSTOMERS),
        "events": len(rest), "by_kind": {k: sum(1 for e in rest if e[2] == k) for k in
                                         ("credit_sale", "payment", "return")},
        "outstanding": round(sum(v for v in ledger.balances().values() if v > 0), 2),
        "graph": app.store.stats(),
    }
    if verbose:
        print(json.dumps(summary, indent=2))
    return app, summary


if __name__ == "__main__":
    _, s = generate(Settings.from_env())
    out = Path(__file__).parent / "seed_summary.json"
    out.write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
    sys.exit(0)
