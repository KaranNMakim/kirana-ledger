"""Live LLMClient backed by the Anthropic API (LLM_MODE=live). Not exercised by tests or the offline demo."""

from __future__ import annotations

import datetime as dt
import os

import anthropic

from app.core.models import ParsedUtterance
from app.core.parser import RuleParser
from app.core.products import ProductCatalog
from app.kg.names import romanize
from app.logging_config import get_logger

log = get_logger(__name__)

SYSTEM = """You extract structured ledger entries from what a small Indian shopkeeper says about udhaar
(credit). Input is Hinglish, Hindi, or transliterated Gujarati/Marathi, possibly noisy speech-to-text.

Rules:
- intent: credit_sale (customer took goods on credit: udhaar, likh do, le gaya, lakhi do), payment
  (customer paid: diye, jama, chukta, aapya, UPI), return (goods brought back: wapas, pachu), query
  (asking a balance: kitna baaki).
- customer_text: the customer's name exactly as spoken, including honorifics (bhai, ben, ji). Do not guess.
- items: one per product; product_text is the product words as spoken (do not translate or map to SKUs),
  qty as a number (aadha=0.5, dedh=1.5, dhai=2.5, paav=1 with unit_text "paav"), unit_text as spoken.
- amount: rupees stated for the whole entry. "aadha hisaab" → amount_expr half_balance; "pura hisaab"
  → full_balance; leave amount null then.
- days_ago: aaj=0, kal=1 (ledger entries are past tense), parso=2, "3 din pehle"=3.
- Confidences are 0..1 and must reflect real uncertainty: unclear names, unknown products, missing
  quantities or two plausible readings → below 0.75.
- method must be "model". Copy the input into `text`."""


class AnthropicLLMClient:
    mode = "live"

    def __init__(self, catalog: ProductCatalog, model: str):
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        self.client = anthropic.Anthropic(timeout=30.0, max_retries=2)
        self.model = model
        self.fallback = RuleParser(catalog)

    def parse_utterance(self, text: str, today: dt.date) -> ParsedUtterance:
        try:
            resp = self.client.messages.parse(
                model=self.model,
                max_tokens=4000,
                output_config={"effort": "low"},
                system=SYSTEM,
                messages=[{"role": "user", "content": f"Today is {today.isoformat()}.\nUtterance: {text}"}],
                output_format=ParsedUtterance,
            )
            if resp.stop_reason == "refusal" or resp.parsed_output is None:
                raise ValueError(f"no parsed output (stop_reason={resp.stop_reason})")
            out = resp.parsed_output
            return out.model_copy(update={"text": text, "normalized": romanize(text).lower(), "method": "model"})
        except (anthropic.APIError, ValueError) as exc:
            log.warning("live parse failed, using rule parser", extra={"error": str(exc)})
            parsed = self.fallback.parse(text, today)
            parsed.notes.append("live model unavailable; parsed by rules")
            return parsed

    def draft_text(self, instruction: str) -> str | None:
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=2000, output_config={"effort": "low"},
                messages=[{"role": "user", "content": instruction}],
            )
            return next((b.text for b in resp.content if b.type == "text"), None)
        except anthropic.APIError as exc:
            log.warning("live draft failed", extra={"error": str(exc)})
            return None
