"""Ontology loader: YAML schema + product/alias instances, validated on load, exportable to JSON-LD / Turtle."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rdflib import OWL, RDF, RDFS, SKOS, XSD, Graph, Literal, Namespace, URIRef

from app.kg.names import canon_phrase

KG_DIR = Path(__file__).resolve().parent
DATA_DIR = KG_DIR.parent.parent / "data"
SCHEMA_PATH = KG_DIR / "ontology.yaml"
PRODUCTS_PATH = DATA_DIR / "products.yaml"


class OntologyError(ValueError):
    pass


@dataclass(frozen=True)
class UnitDef:
    code: str
    kind: str
    base: str
    factor: float
    surface: tuple[str, ...]


@dataclass
class ProductDef:
    sku: str
    name: str
    category: str
    unit: str
    price: float
    brand: str | None = None
    aliases: dict[str, list[str]] = field(default_factory=dict)  # lang → surface forms

    def all_aliases(self) -> list[tuple[str, str]]:
        return [(lang, a) for lang, forms in self.aliases.items() for a in forms]


@dataclass
class GenericTerm:
    term: str
    default: str | None
    candidates: list[str]


@dataclass
class Ontology:
    namespace: str
    prefix: str
    version: str
    classes: dict[str, dict[str, Any]]
    relations: dict[str, dict[str, str]]
    categories: list[str]
    units: dict[str, UnitDef]
    languages: dict[str, str]
    products: dict[str, ProductDef]
    generic_terms: dict[str, GenericTerm]

    # ------------------------------------------------------------ schema checks used by the GraphStore
    def check_node(self, ntype: str, props: dict[str, Any]) -> None:
        cls = self.classes.get(ntype)
        if cls is None:
            raise OntologyError(f"unknown class {ntype!r}")
        missing = [p for p in cls.get("required", []) if props.get(p) in (None, "")]
        if missing:
            raise OntologyError(f"{ntype} missing required {missing}")
        unknown = set(props) - set(cls.get("properties", {}))
        if unknown:
            raise OntologyError(f"{ntype} has unknown properties {sorted(unknown)}")
        for prop, allowed in cls.get("enums", {}).items():
            if prop in props and props[prop] not in allowed:
                raise OntologyError(f"{ntype}.{prop}={props[prop]!r} not in {allowed}")

    def check_edge(self, rel: str, src_type: str, dst_type: str) -> None:
        r = self.relations.get(rel)
        if r is None:
            raise OntologyError(f"unknown relation {rel!r}")
        if (r["domain"], r["range"]) != (src_type, dst_type):
            raise OntologyError(f"{rel} expects {r['domain']}→{r['range']}, got {src_type}→{dst_type}")

    def unit_kind(self, unit: str) -> str:
        return self.units[unit].kind

    # ------------------------------------------------------------ exports
    def to_rdf(self) -> Graph:
        ns = Namespace(self.namespace)
        g = Graph()
        g.bind(self.prefix, ns)
        g.bind("skos", SKOS)
        onto = URIRef(self.namespace.rstrip("#"))
        g.add((onto, RDF.type, OWL.Ontology))
        g.add((onto, OWL.versionInfo, Literal(self.version)))
        for cname, cdef in self.classes.items():
            g.add((ns[cname], RDF.type, OWL.Class))
            g.add((ns[cname], RDFS.comment, Literal(cdef.get("description", ""))))
            for prop, ptype in cdef.get("properties", {}).items():
                p = ns[f"{cname[0].lower()}{cname[1:]}_{prop}"]
                g.add((p, RDF.type, OWL.DatatypeProperty))
                g.add((p, RDFS.domain, ns[cname]))
                g.add((p, RDFS.label, Literal(prop)))
                xsd = {"number": XSD.decimal, "date": XSD.date}.get(ptype, XSD.string)
                g.add((p, RDFS.range, xsd))
        for rname, rdef in self.relations.items():
            g.add((ns[rname], RDF.type, OWL.ObjectProperty))
            g.add((ns[rname], RDFS.domain, ns[rdef["domain"]]))
            g.add((ns[rname], RDFS.range, ns[rdef["range"]]))
            g.add((ns[rname], RDFS.comment, Literal(rdef.get("description", ""))))
        lang_tag = {"en": "en", "hi": "hi-Latn", "gu": "gu-Latn", "mr": "mr-Latn"}
        for p in self.products.values():
            node = ns[f"product/{p.sku}"]
            g.add((node, RDF.type, ns.Product))
            g.add((node, SKOS.prefLabel, Literal(p.name, lang="en")))
            g.add((node, ns.product_sku, Literal(p.sku)))
            g.add((node, ns.product_category, Literal(p.category)))
            g.add((node, ns.product_unit, Literal(p.unit)))
            g.add((node, ns.product_price, Literal(p.price, datatype=XSD.decimal)))
            for lang, alias in p.all_aliases():
                g.add((node, SKOS.altLabel, Literal(alias, lang=lang_tag.get(lang, lang))))
        return g

    def to_jsonld(self) -> dict:
        return json.loads(self.to_rdf().serialize(format="json-ld", indent=2))

    def to_turtle(self) -> str:
        return self.to_rdf().serialize(format="turtle")

    def summary(self) -> dict:
        n_alias = sum(len(p.all_aliases()) for p in self.products.values())
        return {
            "namespace": self.namespace,
            "version": self.version,
            "classes": {k: {"description": v.get("description"), "properties": list(v.get("properties", {}))}
                        for k, v in self.classes.items()},
            "relations": self.relations,
            "units": {k: {"kind": u.kind, "base": u.base, "factor": u.factor, "surface": list(u.surface)}
                      for k, u in self.units.items()},
            "categories": self.categories,
            "counts": {"products": len(self.products), "aliases": n_alias, "generic_terms": len(self.generic_terms)},
        }


def _validate_schema(raw: dict) -> None:
    for key in ("namespace", "classes", "relations", "vocab"):
        if key not in raw:
            raise OntologyError(f"ontology missing top-level key {key!r}")
    classes = raw["classes"]
    for rname, r in raw["relations"].items():
        for end in ("domain", "range"):
            if r.get(end) not in classes:
                raise OntologyError(f"relation {rname}.{end}={r.get(end)!r} is not a class")
    for cname, c in classes.items():
        props = c.get("properties", {})
        for req in c.get("required", []):
            if req not in props:
                raise OntologyError(f"{cname}: required {req!r} not declared in properties")


def load_ontology(schema_path: Path = SCHEMA_PATH, products_path: Path = PRODUCTS_PATH) -> Ontology:
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    _validate_schema(raw)
    vocab = raw["vocab"]
    units = {code: UnitDef(code, u["kind"], u["base"], float(u["factor"]), tuple(u["surface"]))
             for code, u in vocab["units"].items()}
    categories = list(vocab["categories"])
    languages = dict(vocab["languages"])

    pdata = yaml.safe_load(products_path.read_text(encoding="utf-8"))
    products: dict[str, ProductDef] = {}
    for row in pdata["products"]:
        sku = row["sku"]
        if sku in products:
            raise OntologyError(f"duplicate sku {sku}")
        if row["cat"] not in categories:
            raise OntologyError(f"{sku}: unknown category {row['cat']!r}")
        if row["unit"] not in units:
            raise OntologyError(f"{sku}: unknown unit {row['unit']!r}")
        if float(row["price"]) <= 0:
            raise OntologyError(f"{sku}: price must be > 0")
        aliases: dict[str, list[str]] = {}
        for lang, forms in (row.get("aliases") or {}).items():
            if lang not in languages:
                raise OntologyError(f"{sku}: unknown alias language {lang!r}")
            aliases[lang] = list(dict.fromkeys(str(f).lower() for f in forms))
        products[sku] = ProductDef(sku, row["name"], row["cat"], row["unit"], float(row["price"]),
                                   row.get("brand"), aliases)

    generic: dict[str, GenericTerm] = {}
    for term, g in (pdata.get("generic_terms") or {}).items():
        for sku in g["candidates"] + ([g["default"]] if g.get("default") else []):
            if sku not in products:
                raise OntologyError(f"generic term {term!r} references unknown sku {sku}")
        generic[canon_phrase(term)] = GenericTerm(term, g.get("default"), list(g["candidates"]))

    # an alias may map to exactly one product unless declared generic
    seen: dict[str, str] = {}
    for p in products.values():
        for _, alias in p.all_aliases():
            key = canon_phrase(alias)
            if key in generic:
                raise OntologyError(f"{p.sku}: alias {alias!r} collides with generic term")
            if key in seen and seen[key] != p.sku:
                raise OntologyError(f"alias {alias!r} maps to both {seen[key]} and {p.sku}; declare it generic")
            seen[key] = p.sku

    return Ontology(raw["namespace"], raw.get("prefix", "kl"), str(raw.get("version", "0")), raw["classes"],
                    raw["relations"], categories, units, languages, products, generic)
