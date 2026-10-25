"""FastAPI application (Phase 0 skeleton)."""

from __future__ import annotations

from fastapi import FastAPI

from app.logging_config import configure_logging
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    api = FastAPI(title="kirana-ledger", version="0.1.0")

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "llm_mode": settings.llm_mode, "today": settings.today().isoformat()}

    return api


app = create_app()
