"""Provenance carried by every graph fact."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

Method = Literal["rule", "model", "human"]


def utcnow() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Provenance(BaseModel):
    source: str = Field(description="Where the fact came from: utterance id, 'seed:<generator>', 'correction:<id>'")
    timestamp: str = Field(default_factory=utcnow)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    method: Method = "rule"

    @classmethod
    def seed(cls, name: str) -> Provenance:
        return cls(source=f"seed:{name}", confidence=1.0, method="rule")
