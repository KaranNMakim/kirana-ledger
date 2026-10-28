"""Product alias resolution + unit normalisation against the seeded ontology."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass

from app.core.models import ProductCandidate, ResolvedItem
from app.kg.graph_store import GraphStore
from app.kg.names import canon, canon_phrase, edit_ratio, similarity
from app.kg.ontology import Ontology, ProductDef
from app.kg.provenance import Provenance

EXACT_CONF = 0.97
GENERIC_DEFAULT_CONF = 0.8
AMBIGUOUS_CONF = 0.45
FUZZY_MIN = 0.86
FUZZY_MARGIN = 0.03
FUZZY_DISCOUNT = 0.85
EDIT_SLACK = 0.15
UNIT_MISMATCH_PENALTY = 0.3


class CatalogError(ValueError):
    pass


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
        self.products = copy.deepcopy(ontology.products)  # shop edits must not leak into the shared ontology
        self.alias_index: dict[str, str] = {}
        self.alias_lang: dict[str, str] = {}
        for p in self.products.values():
            for lang, alias in [("en", p.name.lower()), *p.all_aliases()]:
                key = canon_phrase(alias)
                if key and key not in ontology.generic_terms:
                    self.alias_index.setdefault(key, p.sku)
                    self.alias_lang.setdefault(key, lang)
        self.generic = ontology.generic_terms
        self._refresh_max_len()
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

    def _refresh_max_len(self) -> None:
        self.max_len = max(len(k.split()) for k in [*self.alias_index, *self.generic])

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
            # Jaro-Winkler over-rewards shared prefixes (chicken ≈ chickpea 0.91); real typos are 1-2 edits
            # away, so cap it with the edit-distance ratio
            s = min(similarity(key, alias, phonetic_floor=False), edit_ratio(key, alias) + EDIT_SLACK)
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
        # a wrong SKU saved silently is the worst outcome (chicken → chickpea), so fuzzy matches are discounted
        # hard: only near-identical spellings clear the 0.75 auto-save bar
        return Resolution("fuzzy", top_sku, round(top * FUZZY_DISCOUNT, 3),
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
                   "aliases": p.aliases, "custom": p.sku.startswith("SHOP-")}
            rows.append(row)
        if q:
            res = self.resolve(q)
            want = {res.sku} | {a.sku for a in res.alternatives}
            ql = q.lower().strip()
            def text_hit(r: dict) -> bool:
                return ql in r["name"].lower() or any(ql in a for forms in r["aliases"].values() for a in forms)

            rows = [r for r in rows if r["sku"] in want or text_hit(r)]
            # exact alias first, then plain text matches, then fuzzy suggestions
            rows.sort(key=lambda r: (0 if res.match == "exact" and r["sku"] == res.sku else 1 if text_hit(r) else 2,
                                     r["name"]))
        return rows

    # ------------------------------------------------------------ shop-specific catalogue (persisted in the graph)
    def apply_store(self, store: GraphStore) -> None:
        """Load products / local names / prices the shop added or changed (graph is authoritative)."""
        for node in store.nodes("Product"):
            pr = node.props
            if pr["sku"] not in self.products:
                self.products[pr["sku"]] = ProductDef(pr["sku"], pr["name"], pr["category"], pr["unit"],
                                                      float(pr["price"]), pr.get("brand"), {})
                key = canon_phrase(pr["name"])
                if key and key not in self.generic:
                    self.alias_index.setdefault(key, pr["sku"])
            else:
                self.products[pr["sku"]].price = float(pr["price"])
        for e in store.edges(rel="alias_of"):
            alias = store.get_node(e.src)
            sku = e.dst.removeprefix("product:")
            key = alias.props.get("canonical") or canon_phrase(alias.props["text"])
            if sku in self.products and key not in self.alias_index and key not in self.generic:
                self.alias_index[key] = sku
                self.products[sku].aliases.setdefault(alias.props["lang"], []).append(alias.props["text"])
        self._refresh_max_len()

    def _check_alias(self, text: str, sku: str | None = None) -> str:
        key = canon_phrase(text)
        if not key:
            raise CatalogError("local name is empty")
        if key in self.generic:
            raise CatalogError(f"'{text}' is a shared word (like tel or dal) and cannot point to one product")
        owner = self.alias_index.get(key)
        if owner and owner != sku:
            raise CatalogError(f"'{text}' already means {self.products[owner].name}")
        return key

    def _write_alias(self, store: GraphStore, sku: str, text: str, lang: str, prov: Provenance) -> None:
        key = self._check_alias(text, sku)
        aid = f"alias:{lang}:{key.replace(' ', '_')}"
        store.upsert_node(aid, "Alias", {"text": text.lower(), "lang": lang, "canonical": key}, prov)
        store.upsert_edge(f"alias_of:{aid}", aid, "alias_of", f"product:{sku}", {}, prov)
        self.alias_index[key] = sku
        forms = self.products[sku].aliases.setdefault(lang, [])
        if text.lower() not in forms:
            forms.append(text.lower())

    def add_product(self, store: GraphStore, name: str, category: str, unit: str, price: float,
                    aliases: dict[str, list[str]], prov: Provenance, brand: str | None = None) -> ProductDef:
        name = " ".join(name.split())
        if not name:
            raise CatalogError("product name is empty")
        if category not in self.onto.categories:
            raise CatalogError(f"unknown category {category!r}")
        if unit not in self.onto.units:
            raise CatalogError(f"unknown unit {unit!r}")
        if price <= 0:
            raise CatalogError("price must be more than 0")
        for lang in aliases:
            if lang not in self.onto.languages:
                raise CatalogError(f"unknown language {lang!r}")
        name_key = canon_phrase(name)
        if name_key in self.alias_index:
            raise CatalogError(f"'{name}' already exists as {self.products[self.alias_index[name_key]].name}")
        forms = [(lang, a.strip()) for lang, items in aliases.items() for a in items if a.strip()]
        for _, a in forms:
            self._check_alias(a)
        base = "SHOP-" + (re.sub(r"[^A-Z0-9]+", "-", name.upper()).strip("-") or "ITEM")
        sku, n = base, 2
        while sku in self.products:
            sku, n = f"{base}-{n}", n + 1
        props = {"sku": sku, "name": name, "category": category, "unit": unit,
                 "unit_kind": self.onto.unit_kind(unit), "price": float(price), "custom": "yes"}
        if brand:
            props["brand"] = brand
        with store.batch():
            store.upsert_node(f"product:{sku}", "Product", props, prov)
            p = ProductDef(sku, name, category, unit, float(price), brand, {})
            self.products[sku] = p
            if name_key not in self.generic:
                self.alias_index[name_key] = sku
            for lang, a in forms:
                self._write_alias(store, sku, a, lang, prov)
        self._refresh_max_len()
        return p

    def add_alias(self, store: GraphStore, sku: str, text: str, lang: str, prov: Provenance) -> ProductDef:
        if sku not in self.products:
            raise CatalogError(f"unknown product {sku}")
        if lang not in self.onto.languages:
            raise CatalogError(f"unknown language {lang!r}")
        self._write_alias(store, sku, text.strip(), lang, prov)
        self._refresh_max_len()
        return self.products[sku]

    def set_price(self, store: GraphStore, sku: str, price: float, prov: Provenance) -> ProductDef:
        if sku not in self.products:
            raise CatalogError(f"unknown product {sku}")
        if price <= 0:
            raise CatalogError("price must be more than 0")
        node = store.get_node(f"product:{sku}")
        store.upsert_node(node.id, "Product", {**node.props, "price": float(price)}, prov)
        self.products[sku].price = float(price)
        return self.products[sku]

