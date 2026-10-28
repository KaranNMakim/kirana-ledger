"""Payment-behaviour features, the explainable 'indicative payment pattern', and shop-level insights.

The pattern is a transparent demo heuristic over this shop's own ledger. It is NOT a credit score.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.core.ledger import LedgerService
from app.core.models import LedgerEventOut

DISCLAIMER = ("Indicative payment pattern: a demo heuristic computed only from this shop's own ledger. "
              "It is not a credit score and must not be used for lending or any decision about a person.")
CALENDAR_PATH = Path(__file__).resolve().parents[2] / "data" / "calendar.yaml"


@dataclass(frozen=True)
class Season:
    id: str
    name: str
    kind: str
    start: dt.date
    end: dt.date

    def contains(self, d: dt.date) -> bool:
        return self.start <= d <= self.end

    @property
    def counts_for_lateness(self) -> bool:
        return self.kind in ("festival", "wedding")


SPILLOVER_DAYS = 30  # purchases soon after a festival queue behind its (late) bill, so they are not a baseline


def _festive(d: dt.date, seasons: list[Season]) -> bool:
    return any(s.counts_for_lateness and s.contains(d) for s in seasons)


def _baseline(d: dt.date, seasons: list[Season]) -> bool:
    return not any(s.counts_for_lateness and s.start <= d <= s.end + dt.timedelta(days=SPILLOVER_DAYS)
                   for s in seasons)


def load_seasons(path: Path = CALENDAR_PATH) -> list[Season]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [Season(s["id"], s["name"], s["kind"], _d(s["start"]), _d(s["end"])) for s in raw["seasons"]]


def _d(v) -> dt.date:
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _wavg(pairs: list[tuple[float, float]]) -> float | None:
    """amount-weighted mean of (days, amount)."""
    tot = sum(a for _, a in pairs)
    return round(sum(d * a for d, a in pairs) / tot, 1) if tot else None


# ---------------------------------------------------------------- per-customer features
def customer_features(events: list[LedgerEventOut], today: dt.date, seasons: list[Season]) -> dict:
    evs = sorted((e for e in events if e.status == "active"),
                 key=lambda e: (e.date, 0 if e.kind == "credit_sale" else 1))
    open_sales: list[list] = []  # [date, original, remaining]
    settled: list[tuple[dt.date, dt.date, float]] = []
    balance = 0.0
    payments: list[LedgerEventOut] = []
    partial = 0
    purchases = 0
    for e in evs:
        if e.kind == "credit_sale":
            purchases += 1
            open_sales.append([e.date, e.amount, e.amount])
            balance += e.amount
            continue
        if e.kind == "payment":
            payments.append(e)
            if e.amount < balance - 1:
                partial += 1
        balance -= e.amount
        x = e.amount
        while x > 0.01 and open_sales:
            head = open_sales[0]
            pay = min(x, head[2])
            head[2] -= pay
            x -= pay
            if head[2] <= 0.5:
                settled.append((head[0], e.date, head[1]))
                open_sales.pop(0)

    days = [((s2 - s1).days, amt) for s1, s2, amt in settled]
    # only judge seasons (and baseline purchases) that have had time to come due, else recent ones look fast
    cutoff = today - dt.timedelta(days=SPILLOVER_DAYS)
    seasons = [s for s in seasons if s.end <= cutoff]
    settled_m = [x for x in settled if x[0] <= cutoff]
    festive = [((s2 - s1).days, amt) for s1, s2, amt in settled_m if _festive(s1, seasons)]
    normal = [((s2 - s1).days, amt) for s1, s2, amt in settled_m if _baseline(s1, seasons)]
    # unsettled festive purchases count with their current age (they are late *now*)
    festive += [((today - o[0]).days, o[2]) for o in open_sales if _festive(o[0], seasons)]
    normal += [((today - o[0]).days, o[2]) for o in open_sales if o[0] <= cutoff and _baseline(o[0], seasons)]
    first = evs[0].date if evs else today
    span_days = max(30, (today - first).days)
    last_pay = payments[-1] if payments else None
    return {
        "balance": round(balance, 2),
        "purchases": purchases,
        "payments": len(payments),
        "settled_purchases": len(settled),
        "avg_days_to_pay": _wavg(days),
        "payments_per_month": round(len(payments) * 30 / span_days, 2),
        "partial_payment_share": round(partial / len(payments), 2) if payments else None,
        "oldest_unpaid_days": (today - open_sales[0][0]).days if open_sales and balance > 1 else 0,
        "oldest_unpaid_date": open_sales[0][0].isoformat() if open_sales and balance > 1 else None,
        "unpaid_purchases": len(open_sales) if balance > 1 else 0,
        "festive_avg_days": _wavg(festive),
        "normal_avg_days": _wavg(normal),
        "last_payment_date": last_pay.date.isoformat() if last_pay else None,
        "last_payment_amount": last_pay.amount if last_pay else None,
        "days_since_last_payment": (today - last_pay.date).days if last_pay else None,
        "first_seen": first.isoformat(),
    }


def payment_pattern(f: dict) -> dict:
    """Explainable 0-100 heuristic + band + evidence. Every deduction is listed."""
    evidence: list[dict] = []

    def add(factor: str, value: str, points: float, why: str) -> None:
        evidence.append({"factor": factor, "value": value, "impact": -round(points, 1), "explanation": why})

    avg = f["avg_days_to_pay"]
    if avg is None and f["oldest_unpaid_days"]:
        old0 = f["oldest_unpaid_days"]
        add("Average days to pay", f"nothing fully cleared; oldest open {old0} days", _clamp((old0 - 10) / 50) * 35,
            "No purchase has been fully paid off yet, so the age of the oldest open purchase is used instead.")
    elif avg is None:
        add("Average days to pay", "no purchases yet", 0, "No credit purchases, nothing to measure.")
    else:
        add("Average days to pay", f"{avg:.0f} days", _clamp((avg - 10) / 50) * 35,
            "Deducted once purchases take more than 10 days to clear on average (up to 35 points at 60+ days).")
    old = f["oldest_unpaid_days"]
    add("Oldest unpaid purchase", f"{old} days" if old else "none", _clamp((old - 30) / 60) * 25,
        "Deducted when something has been unpaid for more than 30 days (up to 25 points at 90+ days).")
    share = f["partial_payment_share"]
    add("Partial payments", f"{share:.0%} of payments" if share is not None else "no payments yet",
        (share or 0) * 15, "Share of payments that left a balance. Common and not bad in itself (up to 15 points).")
    since = f["days_since_last_payment"]
    quiet = f["balance"] > 1 and (since is None or since > 45)
    add("Recent payment", f"{since} days ago" if since is not None else "never paid",
        10 if quiet else 0, "10 points when money is owed and nothing was paid in the last 45 days.")
    fa, na = f["festive_avg_days"], f["normal_avg_days"]
    gap = (fa - na) if fa is not None and na is not None else None
    add("Festival / wedding season", f"{fa:.0f} vs {na:.0f} days" if gap is not None else "not enough data",
        _clamp((gap - 5) / 30) * 15 if gap is not None else 0,
        "Deducted when festive-season purchases take noticeably longer to clear than usual (up to 15 points).")

    score = round(100 + sum(e["impact"] for e in evidence))
    n = f["purchases"]
    data = "low" if n < 4 else "medium" if n < 10 else "high"
    if score >= 75:
        band = "Pays regularly"
    elif score >= 55:
        band = "Usually pays, sometimes slow"
    elif score >= 35:
        band = "Often slow to pay"
    else:
        band = "Frequently late"
    summary = _summary(f, band)
    return {"label": "Indicative payment pattern (demo heuristic)", "score": score, "band": band,
            "data_sufficiency": data, "summary": summary,
            "evidence": sorted(evidence, key=lambda e: e["impact"]), "disclaimer": DISCLAIMER}


def _summary(f: dict, band: str) -> str:
    bits = [band + "."]
    if f["avg_days_to_pay"] is not None:
        bits.append(f"Clears purchases in about {f['avg_days_to_pay']:.0f} days.")
    if f["oldest_unpaid_days"] > 30:
        bits.append(f"Oldest unpaid item is {f['oldest_unpaid_days']} days old.")
    fa, na = f["festive_avg_days"], f["normal_avg_days"]
    if fa is not None and na is not None and fa - na > 10:
        bits.append(f"Slower around festivals ({fa:.0f} vs {na:.0f} days).")
    return " ".join(bits)


# ---------------------------------------------------------------- shop-level
class InsightsService:
    def __init__(self, ledger: LedgerService, seasons: list[Season] | None = None):
        self.ledger = ledger
        self.seasons = seasons if seasons is not None else load_seasons()
        self._cache: tuple[int, dict] | None = None

    def _all_events(self) -> dict[str, list[LedgerEventOut]]:
        by_c: dict[str, list[LedgerEventOut]] = defaultdict(list)
        for e in self.ledger.events():
            by_c[e.customer_id].append(e)
        return by_c

    def customer_profiles(self) -> dict[str, dict]:
        """Features + pattern for every customer (cached on graph version)."""
        ver = self.ledger.store.version
        if self._cache and self._cache[0] == ver:
            return self._cache[1]
        today = self.ledger.today()
        by_c = self._all_events()
        out = {}
        for c in self.ledger.store.nodes("Customer"):
            f = customer_features(by_c.get(c.id, []), today, self.seasons)
            out[c.id] = {"id": c.id, "name": c.props["name"], "locality": c.props.get("locality"),
                         "gender": c.props.get("gender"), "features": f, "pattern": payment_pattern(f)}
        self._cache = (ver, out)
        return out

    def profile(self, cid: str) -> dict:
        self.ledger.customer(cid)
        return self.customer_profiles()[cid]

    def shop_insights(self) -> dict:
        today = self.ledger.today()
        profiles = self.customer_profiles()
        events = self.ledger.events()
        owing = sorted((p for p in profiles.values() if p["features"]["balance"] > 1),
                       key=lambda p: -p["features"]["balance"])

        def row(p: dict) -> dict:
            f = p["features"]
            return {"id": p["id"], "name": p["name"], "balance": f["balance"],
                    "oldest_unpaid_days": f["oldest_unpaid_days"], "avg_days_to_pay": f["avg_days_to_pay"],
                    "last_payment_date": f["last_payment_date"], "band": p["pattern"]["band"],
                    "score": p["pattern"]["score"]}

        late = [p for p in owing if (p["features"]["avg_days_to_pay"] or 0) > 30
                or p["features"]["oldest_unpaid_days"] > 45]
        late.sort(key=lambda p: p["pattern"]["score"])

        monthly: dict[str, dict] = {}
        for e in events:
            m = monthly.setdefault(e.date.strftime("%Y-%m"), {"month": e.date.strftime("%Y-%m"), "credit": 0.0,
                                                              "payments": 0.0, "returns": 0.0, "events": 0})
            key = {"credit_sale": "credit", "payment": "payments", "return": "returns"}[e.kind]
            m[key] = round(m[key] + e.amount, 2)
            m["events"] += 1

        sales = [e for e in events if e.kind == "credit_sale"]
        seasons_out = []
        for s in self.seasons:
            in_s = [e for e in sales if s.contains(e.date)]
            if not in_s:
                continue
            days = (s.end - s.start).days + 1
            seasons_out.append({
                "id": s.id, "name": s.name, "kind": s.kind, "start": s.start.isoformat(), "end": s.end.isoformat(),
                "credit_total": round(sum(e.amount for e in in_s), 2),
                "credit_per_day": round(sum(e.amount for e in in_s) / days, 1),
                "top_products": self._top_products(in_s, 5),
            })
        festive_dates = [e for e in sales if any(s.contains(e.date) for s in self.seasons)]
        normal_dates = [e for e in sales if not any(s.contains(e.date) for s in self.seasons)]
        first = min((e.date for e in events), default=today)
        span = max(1, (today - first).days + 1)
        festive_days = sum(max(0, (min(s.end, today) - max(s.start, first)).days + 1) for s in self.seasons)
        fa = [p["features"]["festive_avg_days"] for p in profiles.values() if p["features"]["festive_avg_days"]]
        na = [p["features"]["normal_avg_days"] for p in profiles.values() if p["features"]["normal_avg_days"]]

        bands: dict[str, int] = defaultdict(int)
        for p in profiles.values():
            if p["features"]["purchases"]:
                bands[p["pattern"]["band"]] += 1
        return {
            "as_of": today.isoformat(),
            "totals": {
                "outstanding": round(sum(p["features"]["balance"] for p in owing), 2),
                "customers": len(profiles), "customers_owing": len(owing),
                "credit_last_30d": round(sum(e.amount for e in sales if (today - e.date).days < 30), 2),
                "collected_last_30d": round(sum(e.amount for e in events
                                                if e.kind == "payment" and (today - e.date).days < 30), 2),
            },
            "top_owed": [row(p) for p in owing[:10]],
            "late_payers": [row(p) for p in late[:10]],
            "monthly": sorted(monthly.values(), key=lambda m: m["month"]),
            "seasons": seasons_out,
            "seasonality": {
                "festive_credit_per_day": round(sum(e.amount for e in festive_dates) / max(1, festive_days), 1),
                "normal_credit_per_day": round(sum(e.amount for e in normal_dates) / max(1, span - festive_days), 1),
                "festive_avg_days_to_pay": round(sum(fa) / len(fa), 1) if fa else None,
                "normal_avg_days_to_pay": round(sum(na) / len(na), 1) if na else None,
            },
            "top_products": self._top_products(sales, 10),
            "pattern_bands": dict(bands),
            "disclaimer": DISCLAIMER,
        }

    @staticmethod
    def _top_products(sales: list[LedgerEventOut], n: int) -> list[dict]:
        agg: dict[str, dict] = {}
        for e in sales:
            for it in e.items:
                a = agg.setdefault(it.sku, {"sku": it.sku, "name": it.name, "value": 0.0, "times": 0})
                a["value"] = round(a["value"] + (it.amount or 0), 2)
                a["times"] += 1
        return sorted(agg.values(), key=lambda a: -a["value"])[:n]

    def graph_elements(self, limit: int = 25, customer_id: str | None = None) -> dict:
        """Cytoscape-ready elements: shop ← owes ← customers → bought → products."""
        profiles = self.customer_profiles()
        shop = self.ledger.shop()
        if customer_id:
            chosen = [profiles[customer_id]] if customer_id in profiles else []
        else:
            chosen = sorted((p for p in profiles.values() if p["features"]["balance"] > 1),
                            key=lambda p: -p["features"]["balance"])[:limit]
        nodes = [{"data": {"id": shop.id, "label": shop.props["name"], "type": "Shop"}}]
        edges = []
        prod_seen: dict[str, dict] = {}
        for p in chosen:
            f = p["features"]
            nodes.append({"data": {"id": p["id"], "label": p["name"], "type": "Customer", "balance": f["balance"],
                                   "band": p["pattern"]["band"], "score": p["pattern"]["score"]}})
            edges.append({"data": {"id": f"owes:{p['id']}", "source": p["id"], "target": shop.id, "rel": "owes",
                                   "amount": f["balance"]}})
            bought: dict[str, float] = defaultdict(float)
            for e in self.ledger.store.edges(rel="bought", src=p["id"]):
                bought[e.dst] += e.props.get("amount") or 0
            for pid, amt in sorted(bought.items(), key=lambda kv: -kv[1])[:4 if not customer_id else 12]:
                if pid not in prod_seen:
                    node = self.ledger.store.get_node(pid)
                    prod_seen[pid] = {"data": {"id": pid, "label": node.props["name"], "type": "Product",
                                               "category": node.props["category"]}}
                edges.append({"data": {"id": f"b:{p['id']}:{pid}", "source": p["id"], "target": pid,
                                       "rel": "bought", "amount": round(amt, 2)}})
        return {"nodes": nodes + list(prod_seen.values()), "edges": edges}
