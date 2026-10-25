# kirana-ledger: Plan

A voice-first udhaar (credit) ledger for small Indian shopkeepers, backed by a knowledge graph.
This is a **proof of value**. The aim is that a stakeholder sees the value in 5 minutes. It is not production software.

## 1. Architecture

```
 Browser (mobile PWA, Next.js static export served at /app)
   │  Web Speech API (hi-IN / gu-IN / en-IN) or typed text
   ▼
 FastAPI (/utterance, /customers, /ledger, /insights, /reminders/draft, ...)
   │
   ├── app/core/pipeline.py   utterance → parse → resolve → decide (save | confirm | answer)
   │     ├── LLMClient.parse()   mock: deterministic rule parser · live: Anthropic tool-use
   │     │                        (both return the same ParsedUtterance Pydantic schema)
   │     ├── products.py         alias + unit resolution against the seeded ontology
   │     ├── customers.py        honorific stripping + phonetic/string fuzzy match → disambiguation
   │     └── dates.py            aaj / kal / parso / "3 din pehle" / weekdays
   ├── app/core/ledger.py     events, balances, undo/edit with provenance
   ├── app/core/insights.py   payment-behaviour features + "indicative payment pattern" (labelled heuristic)
   ├── app/core/reminders.py  WhatsApp-style drafts (en / Hinglish / Gujarati-translit). Drafts only, never sent
   └── app/kg/
         ├── ontology.yaml + ontology.py   classes/relations, validated on load, export JSON-LD / Turtle (rdflib)
         ├── graph_store.py                GraphStore protocol → NetworkX MultiDiGraph + SQLite write-through
         ├── provenance.py                 source (utterance id) · timestamp · confidence · method(rule|model|human)
         ├── llm.py                        LLMClient protocol, MockLLMClient, AnthropicLLMClient
         └── names.py                      Indic-script romanisation, canonical folding, phonetic keys, similarity
```

The API and the web app are served from **one process on one port (8141)**. The API keeps the spec's paths at the root (`/customers`, `/ledger`, ...). The web app is a static export under `/app/`, so the two never collide. One server means one command and no CORS setup, and the page also loads quickly on a 3G phone.

## 2. Build order

| Phase | Deliverable | Gate |
|---|---|---|
| 0 | Repo scaffold, venv, Makefile + `scripts/tasks.py` (works on Windows and POSIX), ruff, pytest, settings, structured logging, `/health` | `make test` green |
| 1 | `ontology.yaml`, ~150-product alias catalogue (hi / gu / mr transliterations + units), loader with validation, JSON-LD/Turtle export, `/ontology` | ontology tests |
| 2 | Romaniser, number words, units, rule parser, product resolver, customer matcher, date parser, pipeline decision | parser tests on the spec examples |
| 3 | GraphStore (NetworkX + SQLite), ledger service with provenance + undo/edit, features, pattern score, insights, reminders, synthetic 6-month ledger generator | core coverage ≥ 80% |
| 4 | All endpoints + API contract tests | contract tests |
| 5 | Next.js PWA: mic, confirmation card, feed, customers, insights, Cytoscape graph, reminders | build + smoke test + manual check at 360 px |
| 6 | 100+ labelled utterances, `make eval` → `docs/eval-report.md`, demo script, README (mermaid, mocked vs real, productisation) | definition of done |

## 3. Key design decisions

- **Confirm, don't guess.** Every extracted field carries a confidence. A record is auto-saved only if every field it needs scores ≥ `CONFIRM_THRESHOLD` (0.75) and the customer resolves to exactly one person. Anything else returns a confirmation card that lists the reasons. Auto-saved entries can be undone with one tap.
- **The LLM extracts, the graph resolves.** In both modes the LLM (or the mock) only extracts surface strings: customer text, product text, qty, unit, amount, date phrase. Mapping those strings to graph entities is deterministic and runs against the catalogue and customer list. This keeps resolution testable and stops hallucinated SKUs.
- **Corrections are append-only.** An edit creates a new event that `corrects` the old one. The old event is marked `voided` with a history entry whose provenance method is `human`. Nothing is hard-deleted.
- **The pattern score is not a credit score.** It is labelled "Indicative payment pattern (demo heuristic)", every point deducted is shown as evidence, and the web app shows a disclaimer next to it.
- **Fixed demo clock.** `KIRANA_TODAY=2025-11-30` by default, so the synthetic 6-month ledger (Jun–Nov 2025) covers Raksha Bandhan, Navratri, Diwali (20 Oct 2025) and the post-Diwali wedding season, and so eval and demos are reproducible. `KIRANA_TODAY=real` uses the system date.

## 4. Assumptions

1. Python: the spec targets 3.12. This machine has 3.14, so the code requires `>=3.12` and is tested on 3.14.
2. Node.js LTS and GNU make were installed with winget for this build. `make` is a thin wrapper over `scripts/tasks.py`, so `py scripts/tasks.py demo` also works without make.
3. "Offline" means after one dependency install (`make setup`). There are no runtime network calls in mock mode.
4. Alias data is curated by hand, synthetic and approximate. Regional spellings are transliterations that a speaker would plausibly type or say, not a linguistic authority.
5. `Alias` is an ontology class, so `alias_of` (Alias → Product) is a real graph edge. The ontology adds a few supporting relations to the spec's five: `recorded_for`, `includes`, `corrects`, `about`.
6. One shop per deployment, with a single `Shop` node. The ontology still models `belongs_to_shop`, so multi-shop support is a data change, not a schema change.
7. `kal` in a ledger statement means *yesterday*. Ledger entries are past tense, so the forward meaning of kal (tomorrow) is ignored, at a lower confidence.
8. "aadha hisaab" means half of the current balance. It always asks for confirmation, because the amount is inferred.
9. Prices come from a seeded price list. When the shopkeeper states no amount, the line amount is estimated and labelled as estimated.
10. All names, localities and ledger data are synthetic. There are no phone numbers or real PII.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The browser speech engine returns Devanagari or Gujarati script, not Latin | A romaniser maps both scripts to Latin before parsing. Matching uses folded phonetic keys, so `चावल` → `chaaval` still matches `chawal`. |
| Hindi `ne` (ergative) vs Gujarati `ne` (dative) mean opposite things | Intent comes from verb and keyword cues first. Postpositions only break ties. |
| The rule parser overfits to its own test phrasing | The labelled set is hand-written, with noisy, ambiguous and code-mixed cases, and failure cases are published in the eval report. |
| Next.js static export vs dynamic routes | Detail pages use query strings (`/app/customer/?id=`). |
| The score is read as creditworthiness | Labelling, an evidence list, the disclaimer, and no lender-facing output. |
| `make` is not installed by default on Windows | All logic lives in `scripts/tasks.py`. The Makefile only calls it. |
