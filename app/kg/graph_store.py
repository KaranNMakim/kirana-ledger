"""GraphStore interface and a NetworkX (in-memory) + SQLite (durable) implementation.

Every node and edge carries a Provenance. Writes are validated against the ontology (class, required
properties, enum values, relation domain/range) and written through to SQLite; on start-up the graph is
rebuilt from SQLite.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Protocol

import networkx as nx
from pydantic import BaseModel

from app.kg.ontology import Ontology
from app.kg.provenance import Provenance


class Node(BaseModel):
    id: str
    type: str
    props: dict[str, Any]
    prov: Provenance


class Edge(BaseModel):
    id: str
    src: str
    rel: str
    dst: str
    props: dict[str, Any]
    prov: Provenance


class GraphStore(Protocol):
    def upsert_node(self, node_id: str, ntype: str, props: dict[str, Any], prov: Provenance) -> Node: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def nodes(self, ntype: str | None = None) -> list[Node]: ...
    def upsert_edge(self, edge_id: str, src: str, rel: str, dst: str, props: dict[str, Any],
                    prov: Provenance) -> Edge: ...
    def edges(self, rel: str | None = None, src: str | None = None, dst: str | None = None) -> list[Edge]: ...
    def remove_edge(self, edge_id: str) -> None: ...
    def remove_node(self, node_id: str) -> None: ...
    def batch(self) -> Any: ...
    @property
    def version(self) -> int: ...
    @property
    def nx(self) -> nx.MultiDiGraph: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, type TEXT NOT NULL, props TEXT NOT NULL, prov TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS edges (id TEXT PRIMARY KEY, src TEXT NOT NULL, rel TEXT NOT NULL, dst TEXT NOT NULL,
                                  props TEXT NOT NULL, prov TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_edges_rel ON edges(rel);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
"""


class NetworkXSQLiteStore:
    def __init__(self, ontology: Ontology, path: str = ":memory:"):
        self.ontology = ontology
        self.path = path
        self._g = nx.MultiDiGraph()
        self._edge_index: dict[str, tuple[str, str]] = {}
        self._lock = threading.RLock()
        self._batch_depth = 0
        self._version = 0
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.executescript(_SCHEMA)
        self._load()

    # ------------------------------------------------------------ persistence
    def _load(self) -> None:
        for nid, ntype, props, prov in self._db.execute("SELECT id, type, props, prov FROM nodes"):
            self._g.add_node(nid, type=ntype, props=json.loads(props), prov=Provenance.model_validate_json(prov))
        for eid, src, rel, dst, props, prov in self._db.execute("SELECT id, src, rel, dst, props, prov FROM edges"):
            self._g.add_edge(src, dst, key=eid, rel=rel, props=json.loads(props),
                             prov=Provenance.model_validate_json(prov))
            self._edge_index[eid] = (src, dst)

    def _commit(self) -> None:
        self._version += 1
        if self._batch_depth == 0:
            self._db.commit()

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Group many writes into one SQLite transaction."""
        with self._lock:
            self._batch_depth += 1
            try:
                yield
            finally:
                self._batch_depth -= 1
                if self._batch_depth == 0:
                    self._db.commit()

    def clear(self) -> None:
        with self._lock:
            self._db.executescript("DELETE FROM nodes; DELETE FROM edges;")
            self._db.commit()
            self._g.clear()
            self._edge_index.clear()
            self._version += 1

    # ------------------------------------------------------------ nodes
    def upsert_node(self, node_id: str, ntype: str, props: dict[str, Any], prov: Provenance) -> Node:
        self.ontology.check_node(ntype, props)
        with self._lock:
            if node_id in self._g and self._g.nodes[node_id]["type"] != ntype:
                raise ValueError(f"node {node_id} already exists with type {self._g.nodes[node_id]['type']}")
            self._g.add_node(node_id, type=ntype, props=dict(props), prov=prov)
            self._db.execute("INSERT OR REPLACE INTO nodes VALUES (?,?,?,?)",
                             (node_id, ntype, json.dumps(props, ensure_ascii=False), prov.model_dump_json()))
            self._commit()
        return Node(id=node_id, type=ntype, props=props, prov=prov)

    def get_node(self, node_id: str) -> Node | None:
        if node_id not in self._g:
            return None
        d = self._g.nodes[node_id]
        return Node(id=node_id, type=d["type"], props=d["props"], prov=d["prov"])

    def nodes(self, ntype: str | None = None) -> list[Node]:
        return [Node(id=n, type=d["type"], props=d["props"], prov=d["prov"])
                for n, d in self._g.nodes(data=True) if ntype is None or d["type"] == ntype]

    # ------------------------------------------------------------ edges
    def upsert_edge(self, edge_id: str, src: str, rel: str, dst: str, props: dict[str, Any],
                    prov: Provenance) -> Edge:
        s, d = self.get_node(src), self.get_node(dst)
        if s is None or d is None:
            raise KeyError(f"edge {edge_id}: missing endpoint {src if s is None else dst}")
        self.ontology.check_edge(rel, s.type, d.type)
        with self._lock:
            if edge_id in self._edge_index:
                old_src, old_dst = self._edge_index[edge_id]
                self._g.remove_edge(old_src, old_dst, key=edge_id)
            self._g.add_edge(src, dst, key=edge_id, rel=rel, props=dict(props), prov=prov)
            self._edge_index[edge_id] = (src, dst)
            self._db.execute("INSERT OR REPLACE INTO edges VALUES (?,?,?,?,?,?)",
                             (edge_id, src, rel, dst, json.dumps(props, ensure_ascii=False),
                              prov.model_dump_json()))
            self._commit()
        return Edge(id=edge_id, src=src, rel=rel, dst=dst, props=props, prov=prov)

    def remove_edge(self, edge_id: str) -> None:
        with self._lock:
            if edge_id not in self._edge_index:
                return
            src, dst = self._edge_index.pop(edge_id)
            self._g.remove_edge(src, dst, key=edge_id)
            self._db.execute("DELETE FROM edges WHERE id=?", (edge_id,))
            self._commit()

    def remove_node(self, node_id: str) -> None:
        """Delete a node and every edge touching it."""
        with self._lock:
            if node_id not in self._g:
                return
            for _, _, key in list(self._g.in_edges(node_id, keys=True)) + list(self._g.out_edges(node_id, keys=True)):
                self._edge_index.pop(key, None)
            self._g.remove_node(node_id)
            self._db.execute("DELETE FROM edges WHERE src=? OR dst=?", (node_id, node_id))
            self._db.execute("DELETE FROM nodes WHERE id=?", (node_id,))
            self._commit()

    def edges(self, rel: str | None = None, src: str | None = None, dst: str | None = None) -> list[Edge]:
        if src is not None:
            if src not in self._g:
                return []
            it = self._g.out_edges(src, keys=True, data=True)
        elif dst is not None:
            if dst not in self._g:
                return []
            it = self._g.in_edges(dst, keys=True, data=True)
        else:
            it = self._g.edges(keys=True, data=True)
        out = []
        for s, d, k, data in it:
            if (rel is None or data["rel"] == rel) and (dst is None or d == dst) and (src is None or s == src):
                out.append(Edge(id=k, src=s, rel=data["rel"], dst=d, props=data["props"], prov=data["prov"]))
        return out

    @property
    def version(self) -> int:
        return self._version

    @property
    def nx(self) -> nx.MultiDiGraph:
        return self._g

    def stats(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        for _, d in self._g.nodes(data=True):
            by_type[d["type"]] = by_type.get(d["type"], 0) + 1
        by_rel: dict[str, int] = {}
        for *_, d in self._g.edges(data=True):
            by_rel[d["rel"]] = by_rel.get(d["rel"], 0) + 1
        return {"nodes": by_type, "edges": by_rel}
