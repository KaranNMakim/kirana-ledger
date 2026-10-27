"""Pydantic schemas shared by the parser (mock + live LLM), the pipeline and the API."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["credit_sale", "payment", "return", "query"]
EventKind = Literal["credit_sale", "payment", "return"]
AmountExpr = Literal["absolute", "half_balance", "full_balance"]
Language = Literal["en", "hinglish", "gu"]


# ---------------------------------------------------------------- raw extraction (LLM / rule parser output)
class ParsedItem(BaseModel):
    """One line item as heard, before catalogue resolution."""
    raw: str = Field(description="Span of the utterance this item came from")
    product_text: str = Field(description="Product words as spoken, e.g. 'chawal', 'parle g'")
    qty: float | None = Field(default=None, description="Quantity as spoken, e.g. 2, 0.5 for aadha")
    unit_text: str | None = Field(default=None, description="Unit word as spoken, e.g. 'kilo', 'packet'")
    amount: float | None = Field(default=None, description="Rupee amount stated for this line, if any")
    confidence: float = Field(ge=0, le=1, default=0.9)


class ParsedUtterance(BaseModel):
    """Structured extraction of one spoken ledger entry. Identical schema for mock and live modes."""
    text: str
    normalized: str = Field(description="Romanised, lower-cased text used for parsing")
    intent: Intent
    intent_confidence: float = Field(ge=0, le=1)
    customer_text: str | None = Field(default=None, description="Customer name as spoken incl. honorific")
    customer_confidence: float = Field(ge=0, le=1, default=0.0)
    items: list[ParsedItem] = Field(default_factory=list)
    amount: float | None = None
    amount_expr: AmountExpr | None = Field(default=None, description="'half_balance' for 'aadha hisaab' etc.")
    amount_confidence: float = Field(ge=0, le=1, default=0.0)
    date_text: str | None = Field(default=None, description="Relative-date phrase as spoken: aaj, kal, parso")
    days_ago: int = Field(default=0, ge=0, description="Resolved offset from today (0 = today)")
    date_confidence: float = Field(ge=0, le=1, default=0.9)
    method: Literal["rule", "model"] = "rule"
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- resolution
class CustomerCandidate(BaseModel):
    id: str
    name: str
    score: float
    balance: float = 0.0
    locality: str | None = None


class CustomerResolution(BaseModel):
    status: Literal["matched", "ambiguous", "new", "missing"]
    query: str | None = None
    customer_id: str | None = None
    name: str | None = None
    confidence: float = 0.0
    gender_hint: str | None = None
    candidates: list[CustomerCandidate] = Field(default_factory=list)


class ProductCandidate(BaseModel):
    sku: str
    name: str
    score: float


class ResolvedItem(BaseModel):
    raw: str
    product_text: str
    sku: str | None = None
    product_name: str | None = None
    qty: float
    unit: str
    qty_in_product_unit: float | None = None
    unit_price: float | None = None
    line_amount: float | None = None
    amount_source: Literal["stated", "price_list", "unknown"] = "unknown"
    confidence: float = 0.0
    match: Literal["exact", "generic_default", "fuzzy", "ambiguous", "none"] = "none"
    alternatives: list[ProductCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FieldCheck(BaseModel):
    field: str
    value: str | None
    confidence: float
    ok: bool
    reason: str | None = None


class Question(BaseModel):
    """A disambiguation / confirmation question for the shopkeeper."""
    field: str
    prompt: str
    options: list[dict] = Field(default_factory=list)


class Interpretation(BaseModel):
    intent: Intent
    customer: CustomerResolution
    items: list[ResolvedItem] = Field(default_factory=list)
    amount: float | None = None
    amount_source: Literal["stated", "price_list", "balance_fraction", "unknown"] = "unknown"
    date: dt.date
    fields: list[FieldCheck] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    confidence: float = 0.0
    summary: str = ""


class LedgerItem(BaseModel):
    sku: str
    name: str
    qty: float
    unit: str
    unit_price: float | None = None
    amount: float | None = None


class LedgerEventOut(BaseModel):
    id: str
    kind: EventKind
    customer_id: str
    customer_name: str
    amount: float
    date: dt.date
    items: list[LedgerItem] = Field(default_factory=list)
    status: Literal["active", "voided"]
    utterance: str | None = None
    amount_source: str | None = None
    supersedes: str | None = None
    superseded_by: str | None = None
    history: list[dict] = Field(default_factory=list)
    provenance: dict


class UtteranceResult(BaseModel):
    utterance_id: str
    decision: Literal["saved", "needs_confirmation", "answered", "rejected"]
    parsed: ParsedUtterance
    interpretation: Interpretation
    pending_id: str | None = None
    event: LedgerEventOut | None = None
    answer: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ItemOverride(BaseModel):
    sku: str
    qty: float = Field(gt=0)
    unit: str | None = None
    amount: float | None = Field(default=None, ge=0)


class ConfirmRequest(BaseModel):
    pending_id: str
    intent: EventKind | None = None
    customer_id: str | None = None
    new_customer_name: str | None = Field(default=None, description="Create this customer instead of matching")
    items: list[ItemOverride] | None = None
    amount: float | None = Field(default=None, ge=0)
    date: dt.date | None = None
    cancel: bool = False


class EditRequest(BaseModel):
    kind: EventKind | None = None
    customer_id: str | None = None
    items: list[ItemOverride] | None = None
    amount: float | None = Field(default=None, ge=0)
    date: dt.date | None = None
    reason: str | None = None


class ReminderRequest(BaseModel):
    customer_id: str
    language: Language = "hinglish"
    tone: Literal["gentle", "firm"] = "gentle"


class ReminderDraft(BaseModel):
    customer_id: str
    customer_name: str
    language: Language
    tone: str
    balance: float
    text: str
    method: Literal["rule", "model"] = "rule"
    sent: Literal[False] = False
    note: str = "Draft only. Nothing has been sent; copy and send it yourself if you choose."
