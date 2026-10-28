"""Export the shop's whole knowledge graph: instances + relations + provenance, as RDF (Turtle / JSON-LD) or JSON.

Nodes become typed resources (`kl:Customer`, `kl:LedgerEvent`, ...) with their properties as literals. Every
relation is a direct triple *and* an `rdf:Statement` carrying W3C PROV-O provenance (source, time, confidence,
method), so the "who said so" survives the export.
"""

from __future__ import annotations

import json
import re
from typing import Any

from rdflib import RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.namespace import PROV

from app.kg.graph_store import GraphStore
from app.kg.ontology import Ontology

CATALOG_TYPES = {"Product", "Alias"}


def _iri(base: Namespace, node_id: str) -> URIRef:
    return base[re.sub(r"[^A-Za-z0-9_\-.:]", "_", node_id).replace(":", "/")]


def _literal(value: Any) -> Literal:
    if isinstance(value, bool):
        return Literal(value)
    if isinstance(value, int | float):
        return Literal(value, datatype=XSD.decimal)
    if isinstance(value, list | dict):
        return Literal(json.dumps(value, ensure_ascii=False), datatype=RDF.JSON)
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return Literal(value, datatype=XSD.date)
    return Literal(value)


def _wanted(ntype: str, include_catalog: bool, used: set[str], node_id: str) -> bool:
    if ntype not in CATALOG_TYPES or include_catalog:
        return True
    return ntype == "Product" and node_id in used  # keep products the ledger references


def export_rdf(store: GraphStore, ontology: Ontology, include_catalog: bool = False) -> Graph:
    kl = Namespace(ontology.namespace)
    data = Namespace(ontology.namespace.rstrip("#") + "/data/")
    g = Graph()
    g.bind(ontology.prefix, kl)
    g.bind("data", data)
    g.bind("prov", PROV)
    used = {e.dst for e in store.edges() if e.rel in ("bought", "includes")}
    keep = {n.id for n in store.nodes() if _wanted(n.type, include_catalog, used, n.id)}

    def prov_of(subject: URIRef, prov) -> None:
        g.add((subject, PROV.wasDerivedFrom, Literal(prov.source)))
        g.add((subject, PROV.generatedAtTime, Literal(prov.timestamp, datatype=XSD.dateTime)))
        g.add((subject, kl.confidence, Literal(prov.confidence, datatype=XSD.decimal)))
        g.add((subject, kl.method, Literal(prov.method)))

    for n in store.nodes():
        if n.id not in keep:
            continue
        s = _iri(data, n.id)
        g.add((s, RDF.type, kl[n.type]))
        if "name" in n.props:
            g.add((s, RDFS.label, Literal(n.props["name"])))
        for k, v in n.props.items():
            if v not in (None, "", []):
                g.add((s, kl[f"{n.type[0].lower()}{n.type[1:]}_{k}"], _literal(v)))
        prov_of(s, n.prov)
    for e in store.edges():
        if e.src not in keep or e.dst not in keep:
            continue
        s, o, p = _iri(data, e.src), _iri(data, e.dst), kl[e.rel]
        g.add((s, p, o))
        st = _iri(data, f"statement:{e.id}")
        g.add((st, RDF.type, RDF.Statement))
        g.add((st, RDF.subject, s))
        g.add((st, RDF.predicate, p))
        g.add((st, RDF.object, o))
        for k, v in e.props.items():
            if v not in (None, ""):
                g.add((st, kl[f"{e.rel}_{k}"], _literal(v)))
        prov_of(st, e.prov)
    return g


def export_json(store: GraphStore, include_catalog: bool = False) -> dict:
    used = {e.dst for e in store.edges() if e.rel in ("bought", "includes")}
    nodes = [n.model_dump() for n in store.nodes() if _wanted(n.type, include_catalog, used, n.id)]
    keep = {n["id"] for n in nodes}
    edges = [e.model_dump() for e in store.edges() if e.src in keep and e.dst in keep]
    return {"format": "kirana-ledger-graph/v1", "nodes": nodes, "edges": edges}
