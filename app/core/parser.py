"""Deterministic rule-based utterance parser (the 'mock' LLM).

Pipeline over tokens: romanise → tag roles (date, product span, number, unit, currency, cue, postposition,
conjunction, honorific, filler, word) → customer = name-like run before a postposition → intent from cue
scores + structure → items = product spans with adjacent quantity groups (+ orphan words for fuzzy match)
→ amount = unattached money/number groups, or "aadha/pura hisaab" balance expressions.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from app.core import lexicon as lx
from app.core.dates import parse_relative_date
from app.core.models import AmountExpr, Intent, ParsedItem, ParsedUtterance
from app.core.products import ProductCatalog
from app.kg.names import canon, is_honorific, romanize, tokenize

NAME_ROLES = {"word", "hon"}


@dataclass
class Group:
    """A run of number / unit / currency tokens."""
    start: int
    end: int  # exclusive
    value: float | None = None
    unit_text: str | None = None
    money: bool = False
    used: bool = False


@dataclass
class _State:
    toks: list[str]
    c: list[str]
    role: list[str | None]
    groups: list[Group] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class RuleParser:
    def __init__(self, catalog: ProductCatalog):
        self.catalog = catalog

    # ------------------------------------------------------------ public
    def parse(self, text: str, today: dt.date) -> ParsedUtterance:
        norm = romanize(text).lower().strip()
        toks = tokenize(norm)
        st = _State(toks, [canon(t) for t in toks], [None] * len(toks))
        date = parse_relative_date(toks, today)
        for p in date.positions:
            st.role[p] = "date"
        expr = self._tag(st)
        cust_idx, cust_conf, post = self._customer(st)
        spans = [s for s in self.catalog.find_spans(st.c) if all(st.role[i] == "span" for i in range(s.start, s.end))]
        items = self._items(st, spans)
        amount, amount_conf, expr_kind = self._amount(st, expr)
        intent, intent_conf = self._intent(st, bool(items), amount is not None or expr_kind is not None, post)

        if intent == "payment" and expr_kind is None and amount is None:
            # "Kishorbhai e aadhu chukvi didhu": half without 'hisaab'
            half = [g for g in st.groups if not g.used and g.value == 0.5 and g.unit_text is None]
            if half:
                half[0].used, expr_kind, amount_conf = True, "half_balance", 0.6
        if intent == "credit_sale" and items and amount is not None and post in {"ne", "e"} and amount_conf < 0.9:
            # "Kavita ben ne 1200 diye aur 2 kilo chawal liya": a payment and a sale in one breath
            intent_conf = min(intent_conf, 0.55)
            st.notes.append("sounds like both a payment and a purchase; please confirm")
        if intent == "payment" and items:
            st.notes.append("payment mentioned items; items ignored")
            items = []

        customer_text = " ".join(toks[i] for i in cust_idx) if cust_idx else None
        return ParsedUtterance(
            text=text, normalized=" ".join(toks), intent=intent, intent_confidence=intent_conf,
            customer_text=customer_text, customer_confidence=cust_conf if cust_idx else 0.0,
            items=items, amount=amount, amount_expr=expr_kind,
            amount_confidence=amount_conf if (amount is not None or expr_kind) else 0.0,
            date_text=date.text, days_ago=date.days_ago, date_confidence=date.confidence,
            method="rule", notes=st.notes,
        )

    # ------------------------------------------------------------ tagging
    def _tag(self, st: _State) -> AmountExpr | None:
        toks, c, role = st.toks, st.c, st.role
        n = len(toks)
        expr: AmountExpr | None = None
        # balance expressions: "aadha hisaab", "pura hisaab", "saara udhaar"
        for i in range(n - 1):
            if role[i] or role[i + 1]:
                continue
            if c[i + 1] in lx.BALANCE_WORDS and (c[i] in lx.HALF_WORDS or c[i] in lx.FULL_WORDS):
                expr = "half_balance" if c[i] in lx.HALF_WORDS else "full_balance"
                role[i] = role[i + 1] = "expr"
        lead = next((k for k in range(n) if role[k] is None and c[k] not in lx.FILLERS), None)
        for s in self.catalog.find_spans(c):
            # a single-word "product" opening the sentence and followed by ko/ne/ka is a name (Sooji ko ...)
            if s.start == lead and s.end - s.start == 1 and s.end < n and c[s.end] in lx.STRONG_POSTPOSITIONS:
                continue
            if all(role[i] is None for i in range(s.start, s.end)):
                for i in range(s.start, s.end):
                    role[i] = "span"
        # numbers
        i = 0
        while i < n:
            if role[i] is None:
                val, j = self._read_number(st, i)
                if val is not None:
                    for k in range(i, j):
                        role[k] = "num"
                    st.groups.append(Group(i, j, value=val))
                    i = j
                    continue
            i += 1
        # units, currency, everything else
        for i in range(n):
            if role[i] is not None:
                continue
            w = c[i]
            prev_num = i > 0 and role[i - 1] == "num"
            nxt_span = i + 1 < n and role[i + 1] == "span"
            unit = self.catalog.unit_code(toks[i])
            if unit and (prev_num or (len(w) > 2 and nxt_span) or unit in ("paav", "dozen")):
                role[i] = "unit"
            elif toks[i] == "₹" or w in lx.CURRENCY:
                role[i] = "cur"
            elif w in lx.ALL_CUES:
                role[i] = "cue"
            elif w in lx.POSTPOSITIONS:
                role[i] = "post"
            elif w in lx.CONJUNCTIONS:
                role[i] = "conj"
            elif is_honorific(toks[i]):
                role[i] = "hon"
            elif w in lx.FILLERS or w in lx.BALANCE_WORDS or len(w) < 2:
                role[i] = "filler"
            else:
                role[i] = "word"
        self._build_groups(st)
        return expr

    def _read_number(self, st: _State, i: int) -> tuple[float | None, int]:
        toks, c = st.toks, st.c
        n = len(toks)
        t = toks[i].replace(",", "")
        if t.replace(".", "", 1).isdigit():
            val, j = float(t), i + 1
            while j < n and c[j] in lx.MULTIPLIERS:  # "5 sau", "2 hazaar"
                val *= lx.MULTIPLIERS[c[j]]
                j += 1
            return val, j
        if c[i] not in lx.NUMBER_WORDS:
            return None, i
        j = i
        while j < n and c[j] in lx.NUMBER_WORDS and st.role[j] is None:
            j += 1
        words = c[i:j]
        if len(words) == 1 and words[0] in lx.WEAK_NUMBERS and not self._quantity_context(st, j):
            return None, i
        total, cur = 0.0, 0.0
        for w in words:
            if w in lx.MULTIPLIERS:
                m = lx.MULTIPLIERS[w]
                if m >= 1000:
                    total += (cur or 1) * m
                    cur = 0.0
                else:
                    cur = (cur or 1) * m
            else:
                cur += lx.NUMBER_WORDS[w]
        return total + cur, j

    def _quantity_context(self, st: _State, j: int) -> bool:
        if j >= len(st.toks):
            return False
        nxt = st.c[j]
        return bool(self.catalog.unit_code(st.toks[j]) or st.role[j] == "span" or nxt in lx.CURRENCY
                    or st.toks[j] == "₹" or nxt in lx.NUMBER_WORDS or st.toks[j][0].isdigit())

    def _build_groups(self, st: _State) -> None:
        """Attach units / currency to number groups; standalone units ('paav ghee', 'dozen ande') get qty 1."""
        role, toks = st.role, st.toks
        by_start = {g.start: g for g in st.groups}
        out: list[Group] = []
        i = 0
        n = len(toks)
        while i < n:
            if role[i] == "cur" and i + 1 < n and i + 1 in by_start:  # "₹500", "rs 500"
                g = by_start[i + 1]
                g.start, g.money = i, True
                i = g.end
                out.append(g)
                self._absorb_trailing(st, g)
                continue
            if role[i] == "num":
                g = by_start[i]
                k = g.end
                if k < n and role[k] == "unit":
                    g.unit_text = toks[k]
                    k += 1
                    if g.unit_text and self.catalog.unit_code(g.unit_text) == "paav" and k < n and role[k] == "unit":
                        k += 1  # "paav kilo"
                if k < n and role[k] == "cur":
                    g.money = True
                    k += 1
                g.end = k
                out.append(g)
                self._absorb_trailing(st, g)
                i = g.end
                continue
            if role[i] == "unit":
                g = Group(i, i + 1, value=1.0, unit_text=toks[i])
                if self.catalog.unit_code(toks[i]) == "paav" and i + 1 < n and role[i + 1] == "unit":
                    g.end = i + 2
                out.append(g)
                i = g.end
                continue
            i += 1
        st.groups = out

    @staticmethod
    def _absorb_trailing(st: _State, g: Group) -> None:
        """'500 ka' / '50 rupaye ka' → money for the following product (or the whole sale)."""
        if g.end < len(st.toks) and st.c[g.end] in {"ka", "ki", "ke", "nu", "na", "no"} and g.unit_text is None:
            g.money = True
            st.role[g.end] = "filler"
            g.end += 1

    # ------------------------------------------------------------ customer
    def _customer(self, st: _State) -> tuple[list[int], float, str | None]:
        role, c = st.role, st.c
        n = len(role)
        for p in range(n):
            if role[p] != "post":
                continue
            run: list[int] = []
            j = p - 1
            while j >= 0 and role[j] in NAME_ROLES and len(run) < 4:
                run.insert(0, j)
                j -= 1
            if any(role[k] == "word" for k in run):
                for k in run:
                    role[k] = "cust"
                return run, 0.9 if c[p] in lx.STRONG_POSTPOSITIONS else 0.78, c[p]
        # no postposition: leading name-like run ("Ramesh bhai 2 kilo chawal")
        k = 0
        while k < n and role[k] in ("date", "filler"):
            k += 1
        run = []
        while k < n and role[k] in NAME_ROLES and len(run) < 4:
            run.append(k)
            k += 1
        conf = 0.85 if any(role[r] == "hon" for r in run) else 0.72
        if run and k < n and role[k] == "cue" and c[k] not in lx.GIVE_CUES:
            conf = max(conf, 0.8)  # "Sachin paid 400", "Rohit took 3 maggi"
        if not any(role[r] == "word" for r in run):
            run, conf = [], 0.0
            for k in range(n):  # anywhere: "500 diye Meena ben", "add 2 kg rice to Prakash"
                if role[k] == "word":
                    intro = k > 0 and c[k - 1] in lx.NAME_INTRODUCERS
                    while k < n and role[k] in NAME_ROLES and len(run) < 4:
                        run.append(k)
                        k += 1
                    conf = 0.8 if intro else 0.65
                    break
        for r in run:
            role[r] = "cust"
        return run, conf, None

    # ------------------------------------------------------------ items
    def _items(self, st: _State, spans) -> list[ParsedItem]:
        role, toks = st.role, st.toks
        n = len(toks)
        group_end = {g.end: g for g in st.groups}
        group_start = {g.start: g for g in st.groups}
        items: list[ParsedItem] = []
        span_starts = {s.start for s in spans}

        def skip_fillers_back(i: int) -> int:
            while i > 0 and role[i - 1] == "filler":
                i -= 1
            return i

        def skip_fillers_fwd(i: int) -> int:
            while i < n and role[i] == "filler":
                i += 1
            return i

        def make(start: int, end: int, conf: float, pre: Group | None, post: Group | None) -> ParsedItem:
            qty_g = next((g for g in (pre, post) if g and not g.money), None)
            money_g = next((g for g in (pre, post) if g and g.money), None)
            for g in (qty_g, money_g):
                if g:
                    g.used = True
            lo = min([start] + [g.start for g in (qty_g, money_g) if g])
            hi = max([end] + [g.end for g in (qty_g, money_g) if g])
            return ParsedItem(raw=" ".join(toks[lo:hi]), product_text=" ".join(toks[start:end]),
                              qty=qty_g.value if qty_g else None,
                              unit_text=qty_g.unit_text if qty_g else None,
                              amount=money_g.value if money_g else None, confidence=conf)

        for s in spans:
            pre = group_end.get(s.start) or group_end.get(skip_fillers_back(s.start))
            if pre and pre.used:
                pre = None
            nxt = skip_fillers_fwd(s.end)
            post = group_start.get(nxt)
            if post and (post.used or skip_fillers_fwd(post.end) in span_starts):
                post = None  # that group belongs to the next product ("2 kilo chawal 1 kilo dal")
            if pre and post and not pre.money and not post.money:
                post = None
            items.append(make(s.start, s.end, 0.95, pre, post))

        # orphan words next to a quantity: likely a product we could not match exactly ("2 kilo chaawl")
        i = 0
        while i < n:
            if role[i] == "word":
                j = i
                while j < n and role[j] == "word":
                    j += 1
                pre = group_end.get(skip_fillers_back(i))
                post = group_start.get(skip_fillers_fwd(j))
                pre = pre if pre and not pre.used and not pre.money else None
                post = post if post and not post.used and not post.money else None
                if pre or post:
                    items.append(make(i, j, 0.75, pre, post))
                    for k in range(i, j):
                        role[k] = "span"
                i = j
            else:
                i += 1
        items.sort(key=lambda it: toks.index(it.product_text.split()[0]) if it.product_text else 0)
        return items

    # ------------------------------------------------------------ amount
    def _amount(self, st: _State, expr: AmountExpr | None) -> tuple[float | None, float, AmountExpr | None]:
        free = [g for g in st.groups if not g.used and g.unit_text is None]
        money = [g for g in free if g.money]
        if money:
            for g in money:
                g.used = True
            if len(money) > 1:
                st.notes.append("several amounts mentioned; using the largest")
            return max(g.value for g in money), 0.95 if len(money) == 1 else 0.6, None
        if expr:
            return None, 0.7 if expr == "half_balance" else 0.8, expr
        bare = [g for g in free if g.value is not None and g.value != 0.5]
        if not bare:
            return None, 0.0, None
        for g in bare:
            g.used = True
        if len(bare) > 1:
            st.notes.append("several numbers mentioned; using the largest as amount")
            return max(g.value for g in bare), 0.6, None
        return bare[0].value, 0.88, None

    # ------------------------------------------------------------ intent
    def _intent(self, st: _State, has_items: bool, has_amount: bool, post: str | None) -> tuple[Intent, float]:
        scores: dict[Intent, float] = {"credit_sale": 0.0, "payment": 0.0, "return": 0.0, "query": 0.0}
        give = 0
        for w, r in zip(st.c, st.role, strict=True):
            if r != "cue":
                continue
            if w in lx.QUERY_CUES:
                scores["query"] += 2
            if w in lx.SALE_CUES:
                scores["credit_sale"] += 1
            if w in lx.PAYMENT_CUES:
                scores["payment"] += 1
            if w in lx.RETURN_CUES:
                scores["return"] += 1.5
            if w in lx.GIVE_CUES:
                give += 1
        if "expr" in st.role:
            scores["payment"] += 1
        if give:
            if scores["return"]:
                scores["return"] += 1  # "wapas diya", "pachu aapyu", "lauta diya"
            else:
                scores["credit_sale" if has_items else "payment"] += 1
        if scores["return"] and not has_items and has_amount:
            scores["payment"] += scores["return"] / 2  # "200 wapas kiye" – money back, probably a payment
            scores["return"] = 0
            st.notes.append("'wapas' with only an amount read as a payment")
        if has_items and not scores["return"]:
            scores["credit_sale"] += 0.5
        if not has_items and has_amount and post in {"ne", "e"}:
            scores["payment"] += 0.5
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        (top, top_s), (_, second_s) = ranked[0], ranked[1]
        if top_s == 0:
            if has_items:
                return "credit_sale", 0.6
            return ("payment", 0.5) if has_amount else ("query", 0.5)
        conf = min(0.97, 0.6 + 0.4 * (top_s - second_s) / top_s)
        return top, round(conf, 3)
