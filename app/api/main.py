"""FastAPI application (Phase 0 skeleton)."""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse

from app.kg.ontology import load_ontology
from app.logging_config import configure_logging
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    onto = load_ontology()
    api = FastAPI(title="kirana-ledger", version="0.1.0")

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "llm_mode": settings.llm_mode, "today": settings.today().isoformat()}

    @api.get("/ontology")
    def ontology(format: str = Query("json", pattern="^(json|jsonld|turtle)$")):
        if format == "turtle":
            return PlainTextResponse(onto.to_turtle(), media_type="text/turtle")
        if format == "jsonld":
            return onto.to_jsonld()
        return onto.summary()

    return api


app = create_app()
