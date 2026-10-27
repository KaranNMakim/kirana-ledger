"""Product alias resolution + unit normalisation against the seeded ontology."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import ProductCandidate, ResolvedItem
from app.kg.graph_store import GraphStore
from app.kg.names import canon, canon_phrase, similarity
from app.kg.ontology import Ontology, ProductDef
from app.kg.provenance import Provenance

EXACT_CONF = 0.97
GENERIC_DEFAULT_CONF = 0.8
AMBIGUOUS_CONF = 0.45
FUZZY_MIN = 0.86
FUZZY_MARGIN = 0.03
UNIT_MISMATCH_PENALTY = 0.3


@dataclass
class Span:
    start: int
    end: int  # exclusive
    key: str
    kind: str  # "alias" | "generic"


@dataclass
class Resolution:
    match: str  # exact | generic_default | fuzzy | ambiguous | none
    sku: str | None
    confidence: float
    alternatives: list[ProductCandidate]


class ProductCatalog:
    def __init__(self, ontology: Ontology):
        self.onto = ontology
        self.products = ontology.products
        self.alias_index: dict[str, str] = {}
        self.alias_lang: dict[str, str] = {}
        for p in self.products.values():
            for lang, alias in [("en", p.name.lower()), *p.all_aliases()]:
                key = canon_phrase(alias)
                if key and key not in ontology.generic_terms:
                    self.alias_index.setdefault(key, p.sku)
                    self.alias_lang.setdefault(key, lang)
        self.generic = ontology.generic_terms
        self.max_len = max(len(k.split()) for k in [*self.alias_index, *self.generic])
        self.unit_index: dict[str, str] = {}
        for code, u in ontology.units.items():
            for s in (code, *u.surface):
                self.unit_index[canon_phrase(s)] = code

    # ------------------------------------------------------------ spans
    def find_spans(self, ctoks: list[str]) -> list[Span]:
        """Greedy longest-match of alias / generic phrases over canonical tokens."""
        spans: list[Span] = []
        i = 0
        while i < len(ctoks):
            hit = None
            for n in range(min(self.max_len, len(ctoks) - i), 0, -1):
                key = " ".join(ctoks[i:i + n])
                if key in self.alias_index:
                    hit = Span(i, i + n, key, "alias")
                elif key in self.generic:
                    hit = Span(i, i + n, key, "generic")
                if hit:
                    break
            if hit:
                spans.append(hit)
                i = hit.end
            else:
                i += 1
        return spans

    def unit_code(self, token: str) -> str | None:
        return self.unit_index.get(canon(token))

    # ------------------------------------------------------------ resolution
    def resolve(self, text: str) -> Resolution:
        key = canon_phrase(text)
        if not key:
            return Resolution("none", None, 0.0, [])
        if key in self.alias_index:
            return Resolution("exact", self.alias_index[key], EXACT_CONF, [])
        if key in self.generic:
            g = self.generic[key]
            alts = [self._cand(s, 0.0) for s in g.candidates]
            if g.default:
                return Resolution("generic_default", g.default, GENERIC_DEFAULT_CONF,
                                  [a for a in alts if a.sku != g.default])
            return Resolution("ambiguous", None, AMBIGUOUS_CONF, alts)
        return self._fuzzy(key)

    def _fuzzy(self, key: str) -> Resolution:
        best: dict[str, float] = {}
        for alias, sku in self.alias_index.items():
            s = similarity(key, alias, phonetic_floor=False)
            if s > best.get(sku, 0.0):
                best[sku] = s
        for term, g in self.generic.items():
            s = similarity(key, term, phonetic_floor=False)
            if s >= FUZZY_MIN:
                for sku in g.candidates:
                    best[sku] = max(best.get(sku, 0.0), s - 0.05)
        ranked = sorted(best.items(), key=lambda kv: -kv[1])[:5]
        if not ranked or ranked[0][1] < FUZZY_MIN:
            return Resolution("none", None, 0.0, [self._cand(s, sc) for s, sc in ranked[:3] if sc > 0.7])
        top_sku, top = ranked[0]
        rivals = [(s, sc) for s, sc in ranked[1:] if top - sc < FUZZY_MARGIN]
        if rivals:
            return Resolution("ambiguous", None, AMBIGUOUS_CONF,
                              [self._cand(s, sc) for s, sc in [ranked[0], *rivals]])
        return Resolution("fuzzy", top_sku, round(top * 0.9, 3),
                          [self._cand(s, sc) for s, sc in ranked[1:3]])

    def _cand(self, sku: str, score: float) -> ProductCandidate:
        return ProductCandidate(sku=sku, name=self.products[sku].name, score=round(score, 3))

    # ------------------------------------------------------------ units & pricing
    def convert(self, qty: float, unit: str | None, product: ProductDef) -> tuple[float, bool]:
        """Quantity in the product's own unit; returns (qty, compatible)."""
        if unit is None:
            return qty, True
        spoken = self.onto.units[unit]
        native = self.onto.units[product.unit]
        if spoken.kind == native.kind:
            return round(qty * spoken.factor / native.factor, 4), True
        if spoken.kind == "count" and native.kind == "pack":  # "2 piece Parle-G" ≈ 2 packets
            return qty * spoken.factor, True
        return qty, False

    def build_item(self, raw: str, product_text: str, qty: float | None, unit_text: str | None,
                   stated_amount: float | None, parse_conf: float) -> ResolvedItem:
        res = self.resolve(product_text)
        unit = self.unit_code(unit_text) if unit_text else None
        qty_conf = 1.0
        if qty is None:
            qty, qty_conf = 1.0, 0.7
        item = ResolvedItem(raw=raw, product_text=product_text, qty=qty, unit=unit or "", match=res.match,
                            alternatives=res.alternatives)
        notes = item.notes
        if qty_conf < 1:
            notes.append("quantity not stated, assumed 1")
        conf = min(res.confidence, parse_conf, qty_conf)
        if res.sku:
            p = self.products[res.sku]
            native_qty, ok = self.convert(qty, unit, p)
            if not ok:
                conf -= UNIT_MISMATCH_PENALTY
                notes.append(f"unit '{unit_text}' unusual for {p.name} (sold per {p.unit})")
            item.sku, item.product_name, item.unit = p.sku, p.name, unit or p.unit
            item.qty_in_product_unit, item.unit_price = native_qty, p.price
            if res.match == "generic_default":
                notes.append(f"'{product_text}' assumed to mean {p.name}")
            if res.match == "fuzzy":
                notes.append(f"'{product_text}' sounds like {p.name}")
        if stated_amount is not None:
            item.line_amount, item.amount_source = stated_amount, "stated"
        elif item.unit_price is not None and item.qty_in_product_unit is not None:
            item.line_amount = round(item.unit_price * item.qty_in_product_unit, 2)
            item.amount_source = "price_list"
        item.confidence = round(max(conf, 0.0), 3)
        return item

    # ------------------------------------------------------------ graph seeding
    def seed_graph(self, store: GraphStore) -> None:
        prov = Provenance.seed("products.yaml")
        with store.batch():
            for p in self.products.values():
                pid = f"product:{p.sku}"
                props = {"sku": p.sku, "name": p.name, "category": p.category, "unit": p.unit,
                         "unit_kind": self.onto.unit_kind(p.unit), "price": p.price}
                if p.brand:
                    props["brand"] = p.brand
                store.upsert_node(pid, "Product", props, prov)
                for lang, alias in p.all_aliases():
                    key = canon_phrase(alias)
                    aid = f"alias:{lang}:{key.replace(' ', '_')}"
                    store.upsert_node(aid, "Alias", {"text": alias, "lang": lang, "canonical": key}, prov)
                    store.upsert_edge(f"alias_of:{aid}", aid, "alias_of", pid, {}, prov)

    def alias_table(self, q: str | None = None) -> list[dict]:
        rows = []
        for p in self.products.values():
            row = {"sku": p.sku, "name": p.name, "category": p.category, "unit": p.unit, "price": p.price,
                   "aliases": p.aliases}
            rows.append(row)
        if q:
            res = self.resolve(q)
            want = {res.sku} | {a.sku for a in res.alternatives}
            rows = [r for r in rows if r["sku"] in want]
        return rows
