"""Customer fuzzy matching: honorific stripping + phonetic/string similarity, gender hint, disambiguation."""

from __future__ import annotations

from collections.abc import Callable

from app.core.models import CustomerCandidate, CustomerResolution
from app.kg.graph_store import GraphStore, Node
from app.kg.names import phonetic_key, similarity, strip_honorifics, tokenize

MATCH_MIN = 0.80
AMBIGUITY_MARGIN = 0.06
PHONETIC_MISMATCH = 0.92  # multiplier when phonetic keys differ (Ramesh vs Rakesh)
GENDER_MISMATCH = 0.75


def _name_score(spoken: str, actual: str) -> float:
    s = similarity(spoken, actual)
    if phonetic_key(spoken) != phonetic_key(actual):
        s *= PHONETIC_MISMATCH
    return s


class CustomerMatcher:
    def __init__(self, store: GraphStore, balance_of: Callable[[str], float] | None = None):
        self.store = store
        self.balance_of = balance_of or (lambda _cid: 0.0)

    def customers(self) -> list[Node]:
        return self.store.nodes("Customer")

    def score(self, tokens: list[str], gender: str | None, cust: Node) -> float:
        p = cust.props
        given, surname = p.get("given_name", ""), p.get("surname") or ""
        nick = p.get("nickname") or ""
        first = tokens[0]
        s_given = max(_name_score(first, given), _name_score(first, nick) if nick else 0.0)
        if len(tokens) == 1:
            score = s_given
            if surname and _name_score(first, surname) > s_given:  # "Patel ji" → match on surname, weaker
                score = _name_score(first, surname) * 0.9
        else:
            rest = " ".join(tokens[1:])
            s_sur = _name_score(rest, surname) if surname else 0.5
            score = 0.6 * s_given + 0.4 * s_sur
        if gender and p.get("gender") and p["gender"] != gender:
            score *= GENDER_MISMATCH
        return round(score, 4)

    def match(self, text: str | None) -> CustomerResolution:
        if not text or not text.strip():
            return CustomerResolution(status="missing", query=text)
        tokens, gender = strip_honorifics(tokenize(text))
        tokens = [t for t in tokens if t]
        if not tokens:
            return CustomerResolution(status="missing", query=text, gender_hint=gender)
        scored = sorted(((self.score(tokens, gender, c), c) for c in self.customers()),
                        key=lambda sc: -sc[0])
        cands = [self._cand(c, s) for s, c in scored if s >= MATCH_MIN][:5]
        if not cands:
            return CustomerResolution(status="new", query=text, name=" ".join(tokens).title(),
                                      confidence=0.5, gender_hint=gender,
                                      candidates=[self._cand(c, s) for s, c in scored[:3] if s >= 0.6])
        top = cands[0]
        rivals = [c for c in cands[1:] if top.score - c.score < AMBIGUITY_MARGIN]
        if rivals:
            return CustomerResolution(status="ambiguous", query=text, confidence=0.4, gender_hint=gender,
                                      candidates=[top, *rivals])
        conf = min(0.97, top.score)
        return CustomerResolution(status="matched", query=text, customer_id=top.id, name=top.name,
                                  confidence=round(conf, 3), gender_hint=gender, candidates=cands[1:3])

    def _cand(self, c: Node, score: float) -> CustomerCandidate:
        return CustomerCandidate(id=c.id, name=c.props["name"], score=score,
                                 balance=round(self.balance_of(c.id), 2), locality=c.props.get("locality"))
