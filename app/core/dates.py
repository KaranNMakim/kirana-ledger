"""Relative-date phrases: aaj, kal, parso, '3 din pehle', 'pichhle hafte', weekdays."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.core import lexicon as lx
from app.kg.names import canon


@dataclass
class DateHit:
    days_ago: int
    text: str | None
    confidence: float
    positions: tuple[int, ...] = ()


def parse_relative_date(tokens: list[str], today: dt.date) -> DateHit:
    """Find the first relative-date expression in `tokens` (raw tokens; folded internally)."""
    c = [canon(t) for t in tokens]
    for i, w in enumerate(c):
        nxt = c[i + 1] if i + 1 < len(c) else ""
        nxt2 = c[i + 2] if i + 2 < len(c) else ""
        # "3 din pehle" / "teen divas pehla"
        n = _num(w)
        if n is not None and nxt in lx.DAYS_AGO_MARKERS and nxt2 in lx.AGO_MARKERS:
            return DateHit(int(n), " ".join(tokens[i:i + 3]), 0.85, (i, i + 1, i + 2))
        if w in lx.DATE_TODAY:
            return DateHit(0, tokens[i], 0.95, (i,))
        if w in lx.DATE_YESTERDAY:
            # in a ledger statement 'kal' is past tense → yesterday; slightly lower confidence
            return DateHit(1, tokens[i], 0.85, (i,))
        if w in lx.DATE_DAY_BEFORE:
            return DateHit(2, tokens[i], 0.85, (i,))
        for firsts, seconds in lx.LAST_WEEK:
            if w in firsts and nxt in seconds:
                return DateHit(7, " ".join(tokens[i:i + 2]), 0.6, (i, i + 1))
        if w in lx.WEEKDAYS:
            wd = lx.WEEKDAYS[w]
            return DateHit((today.weekday() - wd) % 7, tokens[i], 0.8, (i,))
    return DateHit(0, None, 0.9, ())


def _num(word: str) -> float | None:
    if word.isdigit():
        return float(word)
    return lx.NUMBER_WORDS.get(word)
