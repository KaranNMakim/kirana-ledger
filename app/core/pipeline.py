"""Utterance → parse → resolve → decide (save | confirm | answer), plus confirmation of pending entries."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from app.core.customers import CustomerMatcher
from app.core.ledger import LedgerError, LedgerService
from app.core.models import (
    ConfirmRequest,
    CustomerResolution,
    FieldCheck,
    Interpretation,
    LedgerItem,
    ParsedUtterance,
    Question,
    ResolvedItem,
    UtteranceResult,
)
from app.core.products import ProductCatalog
from app.core.reminders import rupees
from app.kg.llm import LLMClient
from app.kg.provenance import Provenance
from app.logging_config import get_logger

log = get_logger(__name__)
KIND_LABEL = {"credit_sale": "Udhaar (credit sale)", "payment": "Payment", "return": "Return", "query": "Question"}


@dataclass
class Pending:
    utterance_id: str
    parsed: ParsedUtterance
    interp: Interpretation


class UtterancePipeline:
    def __init__(self, llm: LLMClient, catalog: ProductCatalog, ledger: LedgerService,
                 matcher: CustomerMatcher, threshold: float = 0.75):
        self.llm, self.catalog, self.ledger, self.matcher = llm, catalog, ledger, matcher
        self.threshold = threshold
        self.pending: dict[str, Pending] = {}

    # ------------------------------------------------------------ resolution
    def interpret(self, parsed: ParsedUtterance) -> Interpretation:
        today = self.ledger.today()
        cust = self.matcher.match(parsed.customer_text)
        cust_conf = cust.confidence if parsed.customer_confidence >= self.threshold else min(
            cust.confidence, parsed.customer_confidence)
        items = [self.catalog.build_item(i.raw, i.product_text, i.qty, i.unit_text, i.amount, i.confidence)
                 for i in parsed.items] if parsed.intent in ("credit_sale", "return") else []

        amount, source = None, "unknown"
        if parsed.amount_expr in ("half_balance", "full_balance"):
            if cust.status == "matched":
                bal = self.ledger.balance(cust.customer_id)
                if bal > 0:
                    amount = round(bal / 2 if parsed.amount_expr == "half_balance" else bal, 2)
                    source = "balance_fraction"
        elif parsed.amount is not None:
            amount, source = parsed.amount, "stated"
        elif items and all(i.line_amount is not None for i in items):
            amount = round(sum(i.line_amount for i in items), 2)
            source = "price_list"

        date = today - dt.timedelta(days=parsed.days_ago)
        interp = Interpretation(intent=parsed.intent, customer=cust, items=items, amount=amount,
                                amount_source=source, date=date)
        interp.customer.confidence = round(cust_conf, 3)
        self._checks(interp, parsed)
        return interp

    def _checks(self, it: Interpretation, parsed: ParsedUtterance) -> None:
        th = self.threshold
        checks: list[FieldCheck] = []
        qs: list[Question] = []

        def chk(field, value, conf, reason=None):
            ok = conf >= th and reason is None
            checks.append(FieldCheck(field=field, value=value, confidence=round(conf, 3), ok=ok,
                                     reason=reason if not ok else None))

        chk("intent", it.intent, parsed.intent_confidence,
            None if parsed.intent_confidence >= th else f"not sure if this is a {KIND_LABEL[it.intent].lower()}")
        c = it.customer
        if c.status == "matched":
            chk("customer", c.name, c.confidence,
                None if c.confidence >= th else f"'{c.query}' matched to {c.name}, but not confidently")
        elif c.status == "ambiguous":
            chk("customer", c.query, c.confidence, f"'{c.query}' could be {len(c.candidates)} customers")
            qs.append(Question(field="customer", prompt=f"Which {self._given(c)}?",
                               options=[{"id": x.id, "label": x.name, "balance": x.balance,
                                         "locality": x.locality} for x in c.candidates]))
        elif c.status == "new":
            chk("customer", c.name, c.confidence, f"no customer called '{c.query}' yet")
            qs.append(Question(field="customer", prompt=f"Add '{c.name}' as a new customer, or pick someone?",
                               options=[{"id": None, "label": f"New: {c.name}", "new_customer_name": c.name}]
                               + [{"id": x.id, "label": x.name, "balance": x.balance} for x in c.candidates]))
        else:
            chk("customer", None, 0.0, "no customer name heard")
            qs.append(Question(field="customer", prompt="Whose account is this?"))

        if it.intent == "query":
            it.fields, it.questions = checks, qs
            it.confidence = min(x.confidence for x in checks)
            it.summary = f"Balance question for {c.name or c.query or '?'}"
            return

        for n, item in enumerate(it.items):
            label = f"{item.qty:g} {item.unit} {item.product_name or item.product_text}"
            reason = None
            if item.sku is None:
                reason = (f"'{item.product_text}' could be several products" if item.match == "ambiguous"
                          else f"don't know the product '{item.product_text}'")
                qs.append(Question(field=f"items[{n}]", prompt=f"Which '{item.product_text}'?",
                                   options=[{"sku": a.sku, "label": a.name} for a in item.alternatives]))
            elif item.confidence < th:
                reason = "; ".join(item.notes) or f"unsure about '{item.product_text}'"
            chk(f"items[{n}]", label, item.confidence, reason)

        need_amount = it.intent == "payment" or not it.items or any(i.line_amount is None for i in it.items)
        if it.amount is None and need_amount:
            why = "amount not heard"
            if parsed.amount_expr and c.status == "matched":
                why = "customer has no balance to settle"
            elif parsed.amount_expr:
                why = "need the customer first to work out the balance"
            chk("amount", None, 0.0, why)
            qs.append(Question(field="amount", prompt="How much (₹)?"))
        elif it.amount is not None:
            reason = None
            if it.amount_source == "balance_fraction":
                bal = self.ledger.balance(c.customer_id)
                frac = "half" if parsed.amount_expr == "half_balance" else "all"
                reason = f"{frac} of balance {rupees(bal)} = {rupees(it.amount)}; please confirm"
            chk("amount", rupees(it.amount), parsed.amount_confidence if it.amount_source != "price_list"
                else min([0.9] + [i.confidence for i in it.items]), reason)
        chk("date", it.date.isoformat(), parsed.date_confidence)

        it.fields, it.questions = checks, qs
        it.confidence = round(min(x.confidence for x in checks), 3)
        who = c.name or c.query or "?"
        what = ", ".join(f"{i.qty:g} {i.unit} {i.product_name or i.product_text}" for i in it.items)
        amt = rupees(it.amount) if it.amount is not None else "₹?"
        src = {"price_list": " (price list)", "balance_fraction": " (from balance)"}.get(it.amount_source, "")
        it.summary = f"{KIND_LABEL[it.intent]}: {who}" + (f", {what}" if what else "") + f", {amt}{src}"

    @staticmethod
    def _given(c: CustomerResolution) -> str:
        return (c.candidates[0].name.split()[0]) if c.candidates else (c.query or "customer")

    # ------------------------------------------------------------ entry points
    def handle(self, text: str) -> UtteranceResult:
        uid = f"utt-{uuid.uuid4().hex[:10]}"
        parsed = self.llm.parse_utterance(text, self.ledger.today())
        interp = self.interpret(parsed)
        log.info("utterance", extra={"utterance_id": uid, "intent": parsed.intent, "method": parsed.method,
                                     "confidence": interp.confidence})
        if parsed.intent == "query":
            c = interp.customer
            if c.status == "matched":
                bal = self.ledger.balance(c.customer_id)
                last = self.ledger.last_payment(c.customer_id)
                ans = f"{c.name} owes {rupees(bal)}."
                if last:
                    ans += f" Last payment {rupees(last.amount)} on {last.date.strftime('%d %b')}."
                return UtteranceResult(utterance_id=uid, decision="answered", parsed=parsed,
                                       interpretation=interp, answer=ans)
            return self._park(uid, parsed, interp)
        if all(f.ok for f in interp.fields) and interp.customer.status == "matched":
            event = self._save(uid, parsed, interp, method=parsed.method, confidence=interp.confidence)
            return UtteranceResult(utterance_id=uid, decision="saved", parsed=parsed, interpretation=interp,
                                   event=event)
        return self._park(uid, parsed, interp)

    def _park(self, uid: str, parsed: ParsedUtterance, interp: Interpretation) -> UtteranceResult:
        pid = f"pend-{uuid.uuid4().hex[:10]}"
        self.pending[pid] = Pending(uid, parsed, interp)
        reasons = [f.reason for f in interp.fields if f.reason]
        return UtteranceResult(utterance_id=uid, decision="needs_confirmation", parsed=parsed,
                               interpretation=interp, pending_id=pid, reasons=reasons)

    def _save(self, uid: str, parsed: ParsedUtterance, interp: Interpretation, method: str, confidence: float,
              customer_id: str | None = None):
        items = [LedgerItem(sku=i.sku, name=i.product_name, qty=i.qty, unit=i.unit, unit_price=i.unit_price,
                            amount=i.line_amount) for i in interp.items if i.sku]
        kind = interp.intent
        prov = Provenance(source=uid, method=method, confidence=round(confidence, 3))
        return self.ledger.record_event(kind, customer_id or interp.customer.customer_id, interp.amount,
                                        interp.date, items, prov, utterance=parsed.text,
                                        amount_source=interp.amount_source)

    def confirm(self, req: ConfirmRequest) -> UtteranceResult:
        pend = self.pending.get(req.pending_id)
        if pend is None:
            raise LedgerError(f"unknown or expired pending entry {req.pending_id}")
        parsed, interp = pend.parsed, pend.interp.model_copy(deep=True)
        if req.cancel:
            del self.pending[req.pending_id]
            return UtteranceResult(utterance_id=pend.utterance_id, decision="rejected", parsed=parsed,
                                   interpretation=interp)
        if req.intent:
            interp.intent = req.intent
        if interp.intent == "query":
            raise LedgerError("pick credit_sale, payment or return to save this entry")
        cid = req.customer_id
        if req.new_customer_name:
            node = self.ledger.add_customer(req.new_customer_name,
                                            Provenance(source=pend.utterance_id, method="human"),
                                            gender=interp.customer.gender_hint, created_from=pend.utterance_id)
            cid = node.id
        cid = cid or interp.customer.customer_id
        if not cid:
            raise LedgerError("choose a customer")
        self.ledger.customer(cid)
        if req.items is not None:
            interp.items = [self._item_from_override(o.sku, o.qty, o.unit, o.amount) for o in req.items]
        if interp.intent == "payment":
            interp.items = []
        if req.amount is not None:
            interp.amount, interp.amount_source = req.amount, "stated"
        elif req.items is not None and interp.items and req.intent != "payment":
            interp.amount = round(sum(i.line_amount or 0 for i in interp.items), 2)
            interp.amount_source = "price_list"
        elif (interp.amount_source == "balance_fraction" or interp.amount is None) and parsed.amount_expr:
            bal = self.ledger.balance(cid)
            interp.amount = round(bal / 2 if parsed.amount_expr == "half_balance" else bal, 2)
            interp.amount_source = "balance_fraction"
        if req.date:
            interp.date = req.date
        if any(i.sku is None for i in interp.items):
            raise LedgerError("choose a product for every item")
        if not interp.amount or interp.amount <= 0:
            raise LedgerError("amount is required")
        event = self._save(pend.utterance_id, parsed, interp, method="human", confidence=1.0, customer_id=cid)
        del self.pending[req.pending_id]
        interp.customer = CustomerResolution(status="matched", query=interp.customer.query, customer_id=cid,
                                             name=event.customer_name, confidence=1.0)
        return UtteranceResult(utterance_id=pend.utterance_id, decision="saved", parsed=parsed,
                               interpretation=interp, event=event)

    def _item_from_override(self, sku: str, qty: float, unit: str | None, amount: float | None) -> ResolvedItem:
        li = self.ledger.line_item(sku, qty, unit, amount)
        return ResolvedItem(raw="(confirmed)", product_text=li.name, sku=sku, product_name=li.name, qty=qty,
                            unit=li.unit, unit_price=li.unit_price, line_amount=li.amount,
                            amount_source="stated" if amount is not None else "price_list", confidence=1.0,
                            match="exact")
