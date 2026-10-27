"""LLMClient interface. LLM_MODE=mock → deterministic rule parser; LLM_MODE=live → Anthropic API.

Both implementations return the same `ParsedUtterance` schema. The LLM only extracts surface strings;
resolution to graph entities (customers, SKUs) is always deterministic and happens in the pipeline.
"""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from app.core.models import ParsedUtterance
from app.core.parser import RuleParser
from app.core.products import ProductCatalog
from app.logging_config import get_logger

log = get_logger(__name__)


class LLMClient(Protocol):
    mode: str

    def parse_utterance(self, text: str, today: dt.date) -> ParsedUtterance: ...

    def draft_text(self, instruction: str) -> str | None: ...


class MockLLMClient:
    mode = "mock"

    def __init__(self, catalog: ProductCatalog):
        self.parser = RuleParser(catalog)

    def parse_utterance(self, text: str, today: dt.date) -> ParsedUtterance:
        return self.parser.parse(text, today)

    def draft_text(self, instruction: str) -> str | None:
        return None  # reminders fall back to deterministic templates


def get_llm_client(mode: str, catalog: ProductCatalog, model: str) -> LLMClient:
    if mode == "live":
        from app.kg.llm_anthropic import AnthropicLLMClient

        try:
            return AnthropicLLMClient(catalog, model)
        except Exception as exc:  # missing key / SDK problems → stay usable offline
            log.warning("live LLM unavailable, falling back to mock", extra={"error": str(exc)})
    return MockLLMClient(catalog)
