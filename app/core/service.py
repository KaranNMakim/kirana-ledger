"""Composition root: builds store, catalogue, ledger, matcher, LLM, pipeline and insights from Settings."""

from __future__ import annotations

from app.core.customers import CustomerMatcher
from app.core.insights import InsightsService
from app.core.ledger import LedgerService
from app.core.pipeline import UtterancePipeline
from app.core.products import ProductCatalog
from app.kg.graph_store import NetworkXSQLiteStore
from app.kg.llm import get_llm_client
from app.kg.ontology import Ontology, load_ontology
from app.settings import Settings


class KiranaApp:
    def __init__(self, settings: Settings, ontology: Ontology | None = None):
        self.settings = settings
        self.ontology = ontology or load_ontology()
        self.store = NetworkXSQLiteStore(self.ontology, settings.db_path)
        self.catalog = ProductCatalog(self.ontology)
        if not self.store.nodes("Product"):
            self.catalog.seed_graph(self.store)
        self.ledger = LedgerService(self.store, self.catalog, settings.today)
        self.ledger.ensure_shop()
        self.matcher = CustomerMatcher(self.store, self.ledger.balance)
        self.llm = get_llm_client(settings.llm_mode, self.catalog, settings.anthropic_model)
        self.pipeline = UtterancePipeline(self.llm, self.catalog, self.ledger, self.matcher,
                                          settings.confirm_threshold)
        self.insights = InsightsService(self.ledger)
