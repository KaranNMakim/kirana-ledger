"""FastAPI application: ledger API at the root, mobile web app (static export) under /app."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.core.ledger import LedgerError
from app.core.models import (
    ConfirmRequest,
    EditRequest,
    LedgerEventOut,
    ReminderDraft,
    ReminderRequest,
    UtteranceResult,
)
from app.core.reminders import draft_reminder, record_draft
from app.core.service import KiranaApp
from app.logging_config import configure_logging, get_logger
from app.settings import Settings

log = get_logger("kirana.api")


class UtteranceIn(BaseModel):
    text: str = Field(min_length=1, max_length=500, examples=["Ramesh bhai ko 2 kilo chawal udhaar"])
    lang: str | None = Field(default=None, description="Speech language used by the client, e.g. hi-IN")


def _err(exc: LedgerError) -> HTTPException:
    msg = str(exc)
    return HTTPException(status_code=404 if msg.startswith("unknown") else 400, detail=msg)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    core = KiranaApp(settings)
    api = FastAPI(title="kirana-ledger", version="0.1.0",
                  description="Voice-first udhaar ledger POV. Synthetic data only.")
    api.state.core = core
    api.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3141", "http://127.0.0.1:3141"],
                       allow_methods=["*"], allow_headers=["*"])

    @api.middleware("http")
    async def request_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        if not request.url.path.startswith("/app/_next"):
            log.info("request", extra={"request_id": rid, "method": request.method, "path": request.url.path,
                                       "status": response.status_code,
                                       "ms": round((time.perf_counter() - t0) * 1000, 1)})
        response.headers["x-request-id"] = rid
        return response

    # ------------------------------------------------------------ meta
    @api.get("/health")
    def health() -> dict:
        shop = core.ledger.shop()
        return {"status": "ok", "llm_mode": core.llm.mode, "today": settings.today().isoformat(),
                "shop": shop.props["name"], "graph": core.store.stats(),
                "confirm_threshold": settings.confirm_threshold}

    @api.get("/ontology")
    def ontology(format: str = Query("json", pattern="^(json|jsonld|turtle)$")):
        if format == "turtle":
            return PlainTextResponse(core.ontology.to_turtle(), media_type="text/turtle")
        if format == "jsonld":
            return core.ontology.to_jsonld()
        return core.ontology.summary()

    # ------------------------------------------------------------ utterances
    @api.post("/utterance", response_model=UtteranceResult)
    def utterance(body: UtteranceIn) -> UtteranceResult:
        return core.pipeline.handle(body.text)

    @api.post("/utterance/confirm", response_model=UtteranceResult)
    def confirm(body: ConfirmRequest) -> UtteranceResult:
        try:
            return core.pipeline.confirm(body)
        except LedgerError as exc:
            raise _err(exc) from exc

    # ------------------------------------------------------------ customers
    @api.get("/customers")
    def customers(q: str | None = None, sort: str = Query("balance", pattern="^(balance|name|score)$"),
                  owing_only: bool = False) -> list[dict]:
        rows = []
        for p in core.insights.customer_profiles().values():
            f, pat = p["features"], p["pattern"]
            rows.append({"id": p["id"], "name": p["name"], "locality": p["locality"], "balance": f["balance"],
                         "last_payment_date": f["last_payment_date"], "last_payment_amount": f["last_payment_amount"],
                         "oldest_unpaid_days": f["oldest_unpaid_days"], "band": pat["band"], "score": pat["score"],
                         "summary": pat["summary"]})
        if q:
            res = core.matcher.match(q)
            ids = {res.customer_id} | {c.id for c in res.candidates}
            ql = q.lower()
            rows = [r for r in rows if r["id"] in ids or ql in r["name"].lower()]
        if owing_only:
            rows = [r for r in rows if r["balance"] > 1]
        key = {"balance": lambda r: -r["balance"], "name": lambda r: r["name"], "score": lambda r: r["score"]}[sort]
        return sorted(rows, key=key)

    @api.get("/customers/{cid}")
    def customer(cid: str) -> dict:
        try:
            prof = core.insights.profile(cid)
        except LedgerError as exc:
            raise _err(exc) from exc
        node = core.ledger.customer(cid)
        reminders = [{"id": e.src, **core.store.get_node(e.src).props, "provenance": e.prov.model_dump()}
                     for e in core.store.edges(rel="about", dst=cid)]
        return {**prof, "props": node.props, "provenance": node.prov.model_dump(),
                "events": [e.model_dump(mode="json") for e in core.ledger.events(cid, include_voided=True)],
                "reminders": reminders}

    # ------------------------------------------------------------ ledger
    @api.get("/ledger", response_model=list[LedgerEventOut])
    def ledger(customer_id: str | None = None, include_voided: bool = False,
               limit: int = Query(50, ge=1, le=5000)) -> list[LedgerEventOut]:
        return core.ledger.events(customer_id, include_voided=include_voided, limit=limit)

    @api.get("/ledger/{eid}", response_model=LedgerEventOut)
    def ledger_event(eid: str) -> LedgerEventOut:
        try:
            return core.ledger.event(eid)
        except LedgerError as exc:
            raise _err(exc) from exc

    class UndoIn(BaseModel):
        reason: str | None = None

    @api.post("/ledger/{eid}/undo", response_model=LedgerEventOut)
    def undo(eid: str, body: UndoIn | None = None) -> LedgerEventOut:
        try:
            return core.ledger.undo(eid, body.reason if body else None)
        except LedgerError as exc:
            raise _err(exc) from exc

    @api.post("/ledger/{eid}/edit", response_model=LedgerEventOut)
    def edit(eid: str, body: EditRequest) -> LedgerEventOut:
        try:
            return core.ledger.edit(eid, body)
        except LedgerError as exc:
            raise _err(exc) from exc

    # ------------------------------------------------------------ insights, graph, reminders, products
    @api.get("/insights")
    def insights() -> dict:
        return core.insights.shop_insights()

    @api.get("/graph")
    def graph(limit: int = Query(25, ge=1, le=60), customer_id: str | None = None) -> dict:
        if customer_id and core.store.get_node(customer_id) is None:
            raise HTTPException(404, f"unknown customer {customer_id}")
        return core.insights.graph_elements(limit=limit, customer_id=customer_id)

    @api.post("/reminders/draft", response_model=ReminderDraft)
    def reminder(body: ReminderRequest) -> ReminderDraft:
        try:
            prof = core.insights.profile(body.customer_id)
        except LedgerError as exc:
            raise _err(exc) from exc
        if prof["features"]["balance"] <= 1:
            raise HTTPException(400, "nothing is owed, no reminder needed")
        node = core.ledger.customer(body.customer_id)
        draft = draft_reminder({"id": node.id, **node.props}, prof["features"], core.ledger.shop().props["name"],
                               body.language, body.tone, llm=core.llm)
        record_draft(core.store, draft)
        return draft

    @api.get("/products/aliases")
    def product_aliases(q: str | None = None) -> dict:
        resolution = None
        if q:
            r = core.catalog.resolve(q)
            resolution = {"query": q, "match": r.match, "sku": r.sku, "confidence": r.confidence,
                          "alternatives": [a.model_dump() for a in r.alternatives]}
        return {"resolution": resolution, "generic_terms": {
            k: {"default": g.default, "candidates": g.candidates} for k, g in core.catalog.generic.items()},
            "products": core.catalog.alias_table(q)}

    # ------------------------------------------------------------ web app
    @api.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/app/")

    if settings.web_dir.exists():
        api.mount("/app", StaticFiles(directory=settings.web_dir, html=True), name="web")
    else:
        @api.get("/app/", include_in_schema=False)
        def no_web():
            return PlainTextResponse("Web app not built yet: run `make web-build` (or `make demo`).", 503)

    return api


app = create_app()
