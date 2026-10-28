"""`make eval`: score the utterance pipeline against hand-labelled data and write docs/eval-report.md.

Metrics: intent accuracy, per-field extraction accuracy (customer, item, qty, amount), alias-resolution
accuracy (catalogue aliases, seeded noisy variants, hand-written hold-out), disambiguation trigger rate,
false-save rate (saved without confirmation but wrong), and unnecessary-confirmation rate.
"""

from __future__ import annotations

import datetime as dt
import json
import random
from collections import defaultdict
from pathlib import Path

from app.settings import Settings
from data.generate import generate

ROOT = Path(__file__).resolve().parent.parent
EVALS = ROOT / "evals"
REPORT = ROOT / "docs" / "eval-report.md"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}% ({n}/{d})" if d else "n/a"


# ---------------------------------------------------------------- utterances
def score_utterances(app, rows: list[dict]) -> dict:
    catalog = app.catalog
    out = []
    for r in rows:
        res = app.pipeline.handle(r["text"])
        it, parsed = res.interpretation, res.parsed
        cust = it.customer
        # customer
        want = r["customer"]
        if want == "AMBIGUOUS":
            cust_ok = cust.status == "ambiguous"
        elif want == "NEW":
            cust_ok = cust.status == "new"
        elif want is None:
            cust_ok = cust.status == "missing"
        else:
            cust_ok = cust.status == "matched" and cust.customer_id == want
        # items: match expected by sku
        got = [(i.sku or {"ambiguous": "AMBIGUOUS", "none": "UNKNOWN"}.get(i.match), i.qty,
                (catalog.unit_code(i.unit) or i.unit)) for i in it.items]
        item_hits, qty_hits = 0, 0
        remaining = list(got)
        for sku, qty, unit in r["items"]:
            m = next((g for g in remaining if g[0] == sku), None)
            if m:
                remaining.remove(m)
                item_hits += 1
                if abs(m[1] - qty) < 1e-6 and m[2] == unit:
                    qty_hits += 1
        extra_items = len([g for g in remaining if g[0]])
        # amount (only when the label states one)
        amount_ok = None
        if r["amount"] is not None:
            amount_ok = it.amount is not None and abs(it.amount - r["amount"]) < 0.5
        intent_ok = parsed.intent == r["intent"]
        needs = res.decision == "needs_confirmation"
        saved = res.decision == "saved"
        record_ok = intent_ok and cust_ok and item_hits == len(r["items"]) and qty_hits == len(r["items"]) \
            and extra_items == 0 and amount_ok is not False
        if saved and any(sku not in catalog.products for sku, _, _ in r["items"]):
            record_ok = False  # label says no real SKU exists, yet something was saved
        elif saved and r["intent"] != "query" and not r["amount"] and r["items"]:
            # amount from price list must equal the labelled items at catalogue price
            exp = sum(app.ledger.line_item(s, q, u).amount for s, q, u in r["items"])
            record_ok = record_ok and abs(res.event.amount - exp) < 0.5
        false_save = saved and not record_ok
        lucky_save = saved and record_ok and r["expect_confirm"]
        out.append({**r, "decision": res.decision, "pred_intent": parsed.intent, "intent_ok": intent_ok,
                    "cust_status": cust.status, "pred_customer": cust.customer_id or cust.query,
                    "cust_ok": cust_ok, "pred_items": got, "item_hits": item_hits, "qty_hits": qty_hits,
                    "extra_items": extra_items, "pred_amount": it.amount, "amount_ok": amount_ok,
                    "record_ok": record_ok, "false_save": false_save, "lucky_save": lucky_save, "needs_confirmation": needs,
                    "reasons": res.reasons, "parse_notes": parsed.notes})
        if saved:  # keep the eval DB stable: undo what was auto-saved
            app.ledger.undo(res.event.id, "eval cleanup")
    return {"rows": out}


def alias_eval(app) -> dict:
    cat = app.catalog
    rng = random.Random(7)
    exact_ok = exact_n = 0
    for p in cat.products.values():
        for _, a in p.all_aliases():
            exact_n += 1
            exact_ok += cat.resolve(a).sku == p.sku
    # seeded noisy variants of every alias (one per alias): vowel drop/dup, consonant double, w↔v, ee↔i
    def perturb(s: str) -> str:
        ops = [lambda t: t.replace("aa", "a", 1) if "aa" in t else t + "a",
               lambda t: t.replace("ee", "i", 1) if "ee" in t else t.replace("i", "ee", 1),
               lambda t: t.replace("w", "v", 1) if "w" in t else t.replace("v", "w", 1),
               lambda t: (lambda k: t[:k] + t[k] + t[k:])(rng.randrange(1, len(t))) if len(t) > 2 else t,
               lambda t: (lambda k: t[:k] + t[k + 1:])(rng.randrange(1, len(t) - 1)) if len(t) > 4 else t]
        return rng.choice(ops)(s)
    noisy = {"ok": 0, "wrong": 0, "abstain": 0, "n": 0, "fails": []}
    for p in cat.products.values():
        for _, a in p.all_aliases():
            v = perturb(a)
            if v == a:
                continue
            r = cat.resolve(v)
            noisy["n"] += 1
            if r.sku == p.sku:
                noisy["ok"] += 1
            elif r.sku is None:
                noisy["abstain"] += 1
            else:
                noisy["wrong"] += 1
                if len(noisy["fails"]) < 12:
                    noisy["fails"].append((v, p.sku, r.sku))
    hold = {"ok": 0, "wrong": 0, "abstain": 0, "n": 0, "fails": []}
    for row in load_jsonl(EVALS / "alias_holdout.jsonl"):
        r = cat.resolve(row["text"])
        hold["n"] += 1
        if r.sku == row["sku"]:
            hold["ok"] += 1
        else:
            hold["abstain" if r.sku is None else "wrong"] += 1
            hold["fails"].append((row["text"], row["sku"], r.sku or f"({r.match})"))
    return {"exact": (exact_ok, exact_n), "noisy": noisy, "holdout": hold}


# ---------------------------------------------------------------- report
def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    save_rows = [r for r in rows if r["intent"] != "query"]
    item_n = sum(len(r["items"]) for r in rows)
    amt = [r for r in rows if r["amount_ok"] is not None]
    amb = [r for r in rows if r["customer"] == "AMBIGUOUS"]
    non_amb = [r for r in rows if r["customer"] not in ("AMBIGUOUS", "NEW", None)]
    saved = [r for r in rows if r["decision"] == "saved"]
    should_confirm = [r for r in rows if r["expect_confirm"]]
    should_save = [r for r in save_rows if not r["expect_confirm"]]
    return {
        "n": n,
        "intent": (sum(r["intent_ok"] for r in rows), n),
        "customer": (sum(r["cust_ok"] for r in rows), n),
        "item": (sum(r["item_hits"] for r in rows), item_n),
        "qty": (sum(r["qty_hits"] for r in rows), item_n),
        "amount": (sum(r["amount_ok"] for r in amt), len(amt)),
        "record": (sum(r["record_ok"] for r in rows), n),
        "disambig_recall": (sum(r["cust_status"] == "ambiguous" for r in amb), len(amb)),
        "disambig_false": (sum(r["cust_status"] == "ambiguous" for r in non_amb), len(non_amb)),
        "false_save_all": (sum(r["false_save"] for r in save_rows), len(save_rows)),
        "false_save_of_saved": (sum(r["false_save"] for r in saved), len(saved)),
        "confirm_recall": (sum(r["needs_confirmation"] or r["decision"] == "answered" for r in should_confirm),
                           len(should_confirm)),
        "saved_though_label_asked": (sum(r["lucky_save"] for r in rows), len(should_confirm)),
        "auto_save_rate": (sum(r["decision"] == "saved" for r in should_save), len(should_save)),
        "unneeded_confirm": (sum(r["needs_confirmation"] for r in should_save), len(should_save)),
    }


def by_tag(rows: list[dict]) -> list[tuple[str, int, int]]:
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        for t in {r["lang"], *r["tags"]}:
            agg[t][0] += r["record_ok"]
            agg[t][1] += 1
    return sorted(((t, a, b) for t, (a, b) in agg.items()), key=lambda x: (x[1] / x[2], -x[2]))


def failure_lines(rows: list[dict]) -> list[str]:
    lines = []
    for r in rows:
        problems = []
        if not r["intent_ok"]:
            problems.append(f"intent {r['pred_intent']} ≠ {r['intent']}")
        if not r["cust_ok"]:
            problems.append(f"customer {r['cust_status']}:{r['pred_customer']} ≠ {r['customer']}")
        if r["item_hits"] < len(r["items"]) or r["extra_items"]:
            problems.append(f"items {[g[0] for g in r['pred_items']]} ≠ {[i[0] for i in r['items']]}")
        elif r["qty_hits"] < len(r["items"]):
            problems.append(f"qty {[(g[1], g[2]) for g in r['pred_items']]} ≠ {[(i[1], i[2]) for i in r['items']]}")
        if r["amount_ok"] is False:
            problems.append(f"amount {r['pred_amount']} ≠ {r['amount']}")
        if r["false_save"]:
            problems.append("**WRONG RECORD SAVED WITHOUT CONFIRMATION**")
        elif r["lucky_save"]:
            problems.append("saved without asking (record was right, label expected a question)")
        elif r["expect_confirm"] and not r["needs_confirmation"] and r["decision"] != "answered":
            problems.append("should have asked")
        elif not r["expect_confirm"] and r["needs_confirmation"]:
            problems.append(f"asked unnecessarily ({'; '.join(r['reasons'])[:90]})")
        if problems:
            text = r["text"].replace("|", "/")
            lines.append(f"| {r['id']} | {text} | {'; '.join(problems)} |")
    return lines


UNTUNED_FIRST = ("intent 100.0% (25/25) · customer 96.0% (24/25) · item 94.4% (17/18) · qty 88.9% (16/18) · "
                 "amount 100.0% (9/9) · record 84.0% (21/25) · disambiguation 100.0% (2/2) · "
                 "**false saves 4.3% (1/23)** · auto-save when safe 76.5% (13/17)")
FIRST_RUN = ("First run, before any tuning (same 114 labels): intent 99.1%, customer 93.0%, item 96.8%, qty 96.8%, "
             "amount 100%, whole record 89.5%, disambiguation trigger 100%, false saves 0 wrong records. "
             "Fixes made after it, all generic rather than per-utterance: weekday short forms (`ravi`, `som`) no "
             "longer swallow names; `paiket` (Devanagari पैकेट) added as a packet unit; give-verbs after a return cue "
             "count as return; speech fillers and festival purpose words (umm, haan, 'Diwali ke liye') are not "
             "read as names; English verbs and 'to/from/for <name>' are recognised.")


def headline(s: dict) -> str:
    return (f"intent {pct(*s['intent'])} · customer {pct(*s['customer'])} · item {pct(*s['item'])} · "
            f"qty {pct(*s['qty'])} · amount {pct(*s['amount'])} · record {pct(*s['record'])} · "
            f"disambiguation {pct(*s['disambig_recall'])} · false saves {pct(*s['false_save_all'])}")


def write_report(s: dict, rows: list[dict], alias: dict, u: dict, urows: list[dict]) -> str:
    ex_ok, ex_n = alias["exact"]
    nz, ho = alias["noisy"], alias["holdout"]
    langs = defaultdict(int)
    for r in rows:
        langs[r["lang"]] += 1
    tag_rows = "\n".join(f"| {t} | {pct(a, b)} |" for t, a, b in by_tag(rows) if b >= 3)
    fails = failure_lines(rows)
    md = f"""# Evaluation report

Generated by `make eval` on {dt.date.today().isoformat()} · mode: **mock (deterministic rule parser)** ·
demo clock {Settings.from_env().today().isoformat()} · confirm threshold 0.75.

Data: `evals/utterances.jsonl`, with **{s['n']} hand-labelled synthetic utterances** ({', '.join(f'{k} {v}' for k, v in sorted(langs.items()))}).
They include clean, noisy and ASR-style, ambiguous-customer, new-customer, ambiguous-product, balance-expression, mixed and fragment cases.
`evals/alias_holdout.jsonl` holds {ho['n']} spellings that are **not** in the catalogue.
The labels were written by hand with the parser's rules known (a white-box eval), so expect lower numbers on real shop audio. The failure table below is the honest part.

## Headline

| Metric | Result | What it means |
|---|---|---|
| Intent accuracy | **{pct(*s['intent'])}** | credit_sale / payment / return / query |
| Customer resolution | **{pct(*s['customer'])}** | right person, or correctly flagged as ambiguous / new / missing |
| Item (product) accuracy | **{pct(*s['item'])}** | labelled items resolved to the right SKU |
| Quantity + unit accuracy | **{pct(*s['qty'])}** | right SKU *and* right qty and unit |
| Amount accuracy (stated amounts) | **{pct(*s['amount'])}** | where the shopkeeper said a rupee amount |
| Whole record correct | {pct(*s['record'])} | every field above right for the utterance |
| Disambiguation trigger rate | **{pct(*s['disambig_recall'])}** | ambiguous customers that triggered a "Which one?" question |
| False disambiguation | {pct(*s['disambig_false'])} | unambiguous customers wrongly asked about |
| **False-save rate** | **{pct(*s['false_save_all'])}** of ledger utterances · {pct(*s['false_save_of_saved'])} of auto-saves | a *wrong* record saved without a confirmation card |
| Saved where label expected a question | {pct(*s['saved_though_label_asked'])} | record was correct, but the labeller expected the app to ask |
| Confirmation recall | {pct(*s['confirm_recall'])} | labelled "should ask" that did ask (or answered a query) |
| Auto-save rate (when safe) | {pct(*s['auto_save_rate'])} | clean entries saved with zero taps |
| Unnecessary confirmations | {pct(*s['unneeded_confirm'])} | clean entries that still asked (costs a tap, not data) |

### Alias resolution

| Set | Correct | Wrong SKU | Abstained (asked) |
|---|---|---|---|
| Catalogue aliases (sanity) | {pct(ex_ok, ex_n)} | | |
| Seeded noisy variants (1 per alias: vowel/consonant/w↔v edits) | {pct(nz['ok'], nz['n'])} | {pct(nz['wrong'], nz['n'])} | {pct(nz['abstain'], nz['n'])} |
| Hand-written hold-out spellings | {pct(ho['ok'], ho['n'])} | {pct(ho['wrong'], ho['n'])} | {pct(ho['abstain'], ho['n'])} |

"Abstained" means the resolver returned no single SKU, so the confirmation card asks. That is safe but costs a tap.
A wrong SKU is the dangerous case. Wrong-SKU fuzzy matches still go through per-field confidence, and they are the main source of any false saves listed below.

Hold-out misses: {', '.join(f'`{t}`→{got} (want {want})' for t, want, got in ho['fails']) or 'none'}.
Noisy wrong-SKU examples: {', '.join(f'`{t}`→{got} (want {want})' for t, want, got in nz['fails']) or 'none'}.

## Untuned set (honesty check)

`evals/utterances_untuned.jsonl`: {u['n']} utterances in new phrasings ("ke naam chadha do", "khate me daal do",
"lakhi nakho", "aapi gaya", an unknown product, unconnected item lists). They were written **after** tuning.

**First (untuned) score, before any change:** {UNTUNED_FIRST}

That run found **one wrong record saved silently**: "Joseph ka 1 kilo chicken" fuzzy-matched *chickpea* (Kabuli Chana) at confidence 0.79.
The only change made in response is a safety fix, not a fit to these sentences. Fuzzy product matches are now discounted ×0.85 instead of ×0.9, so near-misses go to a confirmation card. The current score on the same set:

> {headline(u)} · auto-save when safe {pct(*u['auto_save_rate'])} · unnecessary confirmations {pct(*u['unneeded_confirm'])}

| id | utterance | what went wrong |
|---|---|---|
{chr(10).join(failure_lines(urows)) or '| – | – | none |'}

## Iteration log

{FIRST_RUN}

## Record accuracy by language / tag (≥3 cases, worst first)

| Tag | Record correct |
|---|---|
{tag_rows}

## Failure cases ({len(fails)})

| id | utterance | what went wrong |
|---|---|---|
{chr(10).join(fails) or '| – | – | none |'}

## How to read this

- **The false-save rate is the safety metric.** A wrong entry saved silently is worse than an extra tap. The design trades auto-save rate for it: anything below 0.75 confidence on any field, any customer ambiguity, a new customer, an unknown product, or an amount inferred from the balance goes to a confirmation card.
- Every auto-saved entry can be undone with one tap, and the correction is recorded with `method: human` provenance.
- These are synthetic, typed utterances. Real speech-to-text adds recognition errors that this set only imitates (`noisy` and `asr` tags). The next step is an eval on recorded audio from consenting shopkeepers (see README, "Next steps").
- Re-run with `LLM_MODE=live` (and an API key) to compare the model parser on the same labels. Both modes return the same `ParsedUtterance` schema, so this script works unchanged.
"""
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(md, encoding="utf-8")
    return md


def main() -> None:
    app, _ = generate(Settings(db_path=":memory:"), verbose=False)
    rows = load_jsonl(EVALS / "utterances.jsonl")
    scored = score_utterances(app, rows)["rows"]
    s = summarize(scored)
    urows = score_utterances(app, load_jsonl(EVALS / "utterances_untuned.jsonl"))["rows"]
    u = summarize(urows)
    alias = alias_eval(app)
    write_report(s, scored, alias, u, urows)
    (EVALS / "results.json").write_text(json.dumps({"summary": s, "untuned": u, "alias": {
        "exact": alias["exact"], "noisy": {k: v for k, v in alias["noisy"].items() if k != "fails"},
        "holdout": {k: v for k, v in alias["holdout"].items() if k != "fails"}}}, indent=2), encoding="utf-8")
    for k, v in s.items():
        if isinstance(v, tuple):
            print(f"{k:22} {pct(*v)}")
    print("untuned:", headline(u))
    print(f"{'alias_holdout':22} {pct(alias['holdout']['ok'], alias['holdout']['n'])}")
    print(f"{'alias_noisy':22} {pct(alias['noisy']['ok'], alias['noisy']['n'])}")
    print(f"report → {REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
