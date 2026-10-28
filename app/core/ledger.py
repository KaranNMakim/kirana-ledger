"""Ledger service: events in the graph, running balances, undo/edit with provenance."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Callable

from app.core.models import EditRequest, EventKind, LedgerEventOut, LedgerItem
from app.core.products import ProductCatalog
from app.kg.graph_store import GraphStore, Node
from app.kg.provenance import Provenance, utcnow

SHOP_ID = "shop:main"


class LedgerError(ValueError):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "customer"


class LedgerService:
    def __init__(self, store: GraphStore, catalog: ProductCatalog, today: Callable[[], dt.date]):
        self.store = store
        self.catalog = catalog
        self.today = today
        self._balances: dict[str, float] | None = None
        self._seq = len(store.nodes("LedgerEvent"))
        self._balance_cache()  # build before any write, so new events are only counted via _apply

    # ------------------------------------------------------------ shop & customers
    def ensure_shop(self, name: str = "Shree Ganesh Kirana Stores",
                    locality: str | None = "Maninagar, Ahmedabad") -> Node:
        node = self.store.get_node(SHOP_ID)
        if node is None:
            props = {"name": name, **({"locality": locality} if locality else {})}
            node = self.store.upsert_node(SHOP_ID, "Shop", props, Provenance.seed("shop"))
        return node

    def shop(self) -> Node:
        return self.ensure_shop()

    def update_shop(self, name: str, locality: str | None, language: str | None, prov: Provenance) -> Node:
        name = " ".join(name.split())
        if not name:
            raise LedgerError("shop name is empty")
        props = {**self.shop().props, "name": name, "configured": "yes"}
        for k, v in (("locality", locality), ("language", language)):
            if v:
                props[k] = v.strip()
        return self.store.upsert_node(SHOP_ID, "Shop", props, prov)

    def start_empty(self) -> dict[str, int]:
        """Delete every customer, ledger entry and reminder (the product catalogue and shop stay)."""
        removed = {}
        with self.store.batch():
            for ntype in ("LedgerEvent", "Reminder", "Customer"):
                nodes = self.store.nodes(ntype)
                for n in nodes:
                    self.store.remove_node(n.id)
                removed[ntype] = len(nodes)
        self._balances = {}
        self._seq = 0
        return removed

    def add_customer(self, name: str, prov: Provenance, gender: str | None = None,
                     locality: str | None = None, nickname: str | None = None,
                     created_from: str | None = None) -> Node:
        parts = name.strip().split()
        if not parts:
            raise LedgerError("customer name is empty")
        base = f"cust:{_slug(name)}"
        cid, n = base, 2
        while self.store.get_node(cid) is not None:
            cid, n = f"{base}-{n}", n + 1
        fix = (lambda w: w[:1].upper() + w[1:]) if name != name.lower() else str.capitalize
        parts = [fix(p) for p in parts]
        props = {"name": " ".join(parts), "given_name": parts[0]}
        if len(parts) > 1:
            props["surname"] = " ".join(parts[1:])
        for k, v in (("gender", gender), ("locality", locality), ("nickname", nickname),
                     ("created_from", created_from)):
            if v:
                props[k] = v
        self.ensure_shop()
        node = self.store.upsert_node(cid, "Customer", props, prov)
        self.store.upsert_edge(f"belongs:{cid}", cid, "belongs_to_shop", SHOP_ID, {}, prov)
        self._balance_cache()[cid] = 0.0
        return node

    def customer(self, cid: str) -> Node:
        node = self.store.get_node(cid)
        if node is None or node.type != "Customer":
            raise LedgerError(f"unknown customer {cid}")
        return node

    # ------------------------------------------------------------ balances
    def _balance_cache(self) -> dict[str, float]:
        if self._balances is None:
            bal = {c.id: 0.0 for c in self.store.nodes("Customer")}
            for ev in self.store.nodes("LedgerEvent"):
                if ev.props["status"] == "active":
                    cid = ev.props["customer_id"]
                    bal[cid] = bal.get(cid, 0.0) + self._delta(ev.props["kind"], ev.props["amount"])
            self._balances = bal
        return self._balances

    @staticmethod
    def _delta(kind: str, amount: float) -> float:
        return amount if kind == "credit_sale" else -amount

    def balance(self, cid: str) -> float:
        return round(self._balance_cache().get(cid, 0.0), 2)

    def balances(self) -> dict[str, float]:
        return {k: round(v, 2) for k, v in self._balance_cache().items()}

    def _apply(self, cid: str, delta: float, prov: Provenance) -> None:
        cache = self._balance_cache()
        cache[cid] = cache.get(cid, 0.0) + delta
        self.store.upsert_edge(f"owes:{cid}", cid, "owes", SHOP_ID, {"amount": round(cache[cid], 2)}, prov)

    # ------------------------------------------------------------ events
    def _next_id(self) -> str:
        self._seq += 1
        return f"evt-{self._seq:06d}"

    def record_event(self, kind: EventKind, customer_id: str, amount: float, date: dt.date,
                     items: list[LedgerItem], prov: Provenance, utterance: str | None = None,
                     amount_source: str | None = None, supersedes: str | None = None) -> LedgerEventOut:
        self.customer(customer_id)
        if amount <= 0:
            raise LedgerError("amount must be positive")
        if kind == "payment" and items:
            raise LedgerError("a payment cannot carry items")
        self.ensure_shop()
        eid = self._next_id()
        props = {"kind": kind, "amount": round(float(amount), 2), "date": date.isoformat(),
                 "items": [i.model_dump() for i in items], "status": "active", "customer_id": customer_id,
                 "history": []}
        if utterance:
            props["utterance"] = utterance
        if amount_source:
            props["amount_source"] = amount_source
        if supersedes:
            props["supersedes"] = supersedes
        with self.store.batch():
            self.store.upsert_node(eid, "LedgerEvent", props, prov)
            self.store.upsert_edge(f"for:{eid}", eid, "recorded_for", customer_id, {}, prov)
            for n, it in enumerate(items):
                pid = f"product:{it.sku}"
                if self.store.get_node(pid) is None:
                    continue
                self.store.upsert_edge(f"inc:{eid}:{n}", eid, "includes", pid, {"qty": it.qty, "unit": it.unit}, prov)
                if kind == "credit_sale":
                    self.store.upsert_edge(f"bought:{eid}:{n}", customer_id, "bought", pid,
                                           {"qty": it.qty, "unit": it.unit, "date": props["date"],
                                            "event": eid, "amount": it.amount}, prov)
            if kind == "payment":
                self.store.upsert_edge(f"paid:{eid}", customer_id, "paid", SHOP_ID,
                                       {"amount": props["amount"], "date": props["date"], "event": eid}, prov)
            if supersedes:
                self.store.upsert_edge(f"corrects:{eid}", eid, "corrects", supersedes, {}, prov)
            self._apply(customer_id, self._delta(kind, props["amount"]), prov)
        return self.event(eid)

    def event(self, eid: str) -> LedgerEventOut:
        node = self.store.get_node(eid)
        if node is None or node.type != "LedgerEvent":
            raise LedgerError(f"unknown event {eid}")
        return self._out(node)

    def _out(self, node: Node, names: dict[str, str] | None = None) -> LedgerEventOut:
        p = node.props
        cid = p["customer_id"]
        if names is not None:
            cname = names.get(cid, cid)
        else:
            cnode = self.store.get_node(cid)
            cname = cnode.props["name"] if cnode else cid
        return LedgerEventOut(id=node.id, kind=p["kind"], customer_id=cid, customer_name=cname,
                              amount=p["amount"], date=dt.date.fromisoformat(p["date"]),
                              items=[LedgerItem(**i) for i in p.get("items", [])], status=p["status"],
                              utterance=p.get("utterance"), amount_source=p.get("amount_source"),
                              supersedes=p.get("supersedes"), superseded_by=p.get("superseded_by"),
                              history=p.get("history", []), provenance=node.prov.model_dump())

    def events(self, customer_id: str | None = None, include_voided: bool = False,
               limit: int | None = None) -> list[LedgerEventOut]:
        names = {c.id: c.props["name"] for c in self.store.nodes("Customer")}
        nodes = [n for n in self.store.nodes("LedgerEvent")
                 if (customer_id is None or n.props["customer_id"] == customer_id)
                 and (include_voided or n.props["status"] == "active")]
        nodes.sort(key=lambda n: (n.props["date"], n.id), reverse=True)
        if limit:
            nodes = nodes[:limit]
        return [self._out(n, names) for n in nodes]

    # ------------------------------------------------------------ corrections
    def _void(self, eid: str, action: str, reason: str | None, prov: Provenance,
              superseded_by: str | None = None) -> Node:
        node = self.store.get_node(eid)
        if node is None or node.type != "LedgerEvent":
            raise LedgerError(f"unknown event {eid}")
        if node.props["status"] != "active":
            raise LedgerError(f"event {eid} is already {node.props['status']}")
        props = dict(node.props)
        props["status"] = "voided"
        props["history"] = [*props.get("history", []),
                            {"action": action, "at": prov.timestamp, "by": prov.method, "source": prov.source,
                             "reason": reason, "superseded_by": superseded_by}]
        if superseded_by:
            props["superseded_by"] = superseded_by
        with self.store.batch():
            # node keeps its original provenance; the correction itself is recorded in history + new prov edges
            self.store.upsert_node(eid, "LedgerEvent", props, node.prov)
            for e in self.store.edges(src=props["customer_id"]):
                if e.rel in ("bought", "paid") and e.props.get("event") == eid:
                    self.store.remove_edge(e.id)
            self._apply(props["customer_id"], -self._delta(props["kind"], props["amount"]), prov)
        return self.store.get_node(eid)

    def undo(self, eid: str, reason: str | None = None) -> LedgerEventOut:
        prov = Provenance(source=f"correction:{uuid.uuid4().hex[:8]}", method="human", confidence=1.0)
        return self._out(self._void(eid, "undo", reason, prov))

    def edit(self, eid: str, req: EditRequest) -> LedgerEventOut:
        old = self.event(eid)
        if old.status != "active":
            raise LedgerError(f"event {eid} is already {old.status}")
        kind = req.kind or old.kind
        customer_id = req.customer_id or old.customer_id
        self.customer(customer_id)
        items = old.items
        if req.items is not None:
            items = [self.line_item(o.sku, o.qty, o.unit, o.amount) for o in req.items]
        if kind == "payment":
            items = []
        amount = req.amount
        source = "stated" if req.amount is not None else old.amount_source
        if amount is None:
            amount = sum(i.amount or 0 for i in items) if req.items is not None and items else old.amount
            source = "price_list" if req.items is not None and items else old.amount_source
        date = req.date or old.date
        cid = uuid.uuid4().hex[:8]
        prov = Provenance(source=f"correction:{cid}", method="human", confidence=1.0, timestamp=utcnow())
        new_id = f"evt-{self._seq + 1:06d}"
        self._void(eid, "edit", req.reason, prov, superseded_by=new_id)
        new = self.record_event(kind, customer_id, amount, date, items, prov, utterance=old.utterance,
                                amount_source=source, supersedes=eid)
        return new

    # ------------------------------------------------------------ helpers
    def line_item(self, sku: str, qty: float, unit: str | None = None, amount: float | None = None) -> LedgerItem:
        p = self.catalog.products.get(sku)
        if p is None:
            raise LedgerError(f"unknown product {sku}")
        native_qty, _ = self.catalog.convert(qty, unit, p)
        amt = amount if amount is not None else round(native_qty * p.price, 2)
        return LedgerItem(sku=sku, name=p.name, qty=qty, unit=unit or p.unit, unit_price=p.price, amount=amt)

    def last_payment(self, cid: str) -> LedgerEventOut | None:
        pays = [e for e in self.events(cid) if e.kind == "payment"]
        return pays[0] if pays else None
