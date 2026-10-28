# kirana-ledger: voice-first udhaar ledger (proof of value)

Small Indian shopkeepers keep **udhaar** (customer credit) in their heads or in paper notebooks, and they think in
Hinglish, Hindi or Gujarati, not in forms. kirana-ledger lets them **say** the entry:

> *"Ramesh bhai ko 2 kilo chawal udhaar"* · *"Meena ben ne 500 diye"* · *"Kishorbhai e aadhu chukvi didhu"*

It turns that into a structured, provenance-tracked entry in a **knowledge graph**, asks instead of guessing when
it is unsure, and answers the questions a shopkeeper actually has: *who owes most, who pays late, does that change at
Diwali, and how do I remind them politely?*

> **POV, not production.** All data is synthetic. Runs fully offline in mock mode. The payment-pattern view is a labelled demo
> heuristic, **not a credit score**.

<p align="center"><img src="docs/demo.gif" alt="Walkthrough: set up your own shop, add a customer, add a product with Gujarati local names, teach a new local name, speak a Gujarati entry that saves with zero taps, see your own knowledge graph; then on six months of demo data: customer disambiguation, the explainable payment pattern, a Gujarati reminder draft, seasonal insights, the udhaar graph and graph export" width="320"></p>

**5-minute walkthrough:** [`docs/demo-script.md`](docs/demo-script.md) · **Measured quality:** [`docs/eval-report.md`](docs/eval-report.md) · **Design:** [`PLAN.md`](PLAN.md)

## Quick start

```bash
make setup   # once: Python venv + pip, npm install (needs network once)
make demo    # demo shop: fresh synthetic data every run → http://localhost:8141/app/
make start   # YOUR shop: separate database (data/myshop.db), starts empty, real date, data is kept
make test    # pytest (+ coverage gates) and the web smoke test
make eval    # writes docs/eval-report.md
```

There's no `make` on Windows by default; every target is also `py scripts/tasks.py <target>`.
Requirements: Python ≥ 3.12 (tested on 3.14) and Node.js LTS (tested on 24). Open the app in Chrome or Edge at phone
width. Voice uses the browser's Web Speech API (`hi-IN`, `gu-IN`, `en-IN`), and there is always a typed fallback.

## Use it for your own shop

`make start` opens a setup screen on first launch (shop name, area, speaking language). The ledger then starts
**empty**, in its own database, so the demo never touches it. Everything below builds *your* knowledge graph, and
every fact you add is stored with `method: human` provenance.

| Screen | What you can do | Graph effect |
|---|---|---|
| **Shop → Edit shop details** | Name, area, default speech language (hi-IN / gu-IN / mr-IN / en-IN) | updates the `Shop` node |
| **Customers → + Add** | Name, bhai / ben, area, nickname. Warns before you add a duplicate ("Already on your ledger?") | new `Customer —belongs_to_shop→ Shop` |
| **Ledger** (voice or text) | Unknown names are offered as new customers on the confirmation card | `LedgerEvent`, `owes`, `bought`, `paid` |
| **Shop → Products & local names** | Add your own products (category, unit, price, Hindi / Gujarati / Marathi names); **teach** a new local name for any item (say "bhaat" → Rice); change prices | `Product`, `Alias —alias_of→ Product`. The parser uses them immediately |
| **Shop → Export your graph** | Download Turtle, JSON-LD or JSON: customers, entries, relations, and W3C PROV provenance for every fact (optionally with the full catalogue) | read-only |
| **Shop → Start empty** | Type DELETE to wipe customers, entries and reminders. Shop details, products and local names stay | removes instance nodes |

Example: add *Hapus Mango* (₹900/dozen, Gujarati "keri"), teach "bhaat" for rice, then say
*"Kiranben nu 1 dozen keri ane 2 kilo bhaat lakhi do"*. It saves *Kiran Shah · Hapus Mango + Rice · ₹1,020* without a single tap.

## Architecture

```mermaid
flowchart LR
  subgraph Phone["📱 Mobile PWA (Next.js static export, /app)"]
    MIC["🎙️ Web Speech<br/>hi-IN · gu-IN · en-IN"] --> TXT[typed / spoken text]
    CARD[Confirmation card<br/>one-tap fixes]
    VIEWS[Feed · Customers · Insights<br/>Cytoscape graph · Reminders]
  end
  TXT -->|POST /utterance| API
  CARD -->|POST /utterance/confirm| API
  VIEWS -->|GET /customers /ledger /insights /graph<br/>POST /reminders/draft| API

  subgraph Server["FastAPI (one process, port 8141)"]
    API[API + JSON logs] --> PIPE[pipeline:<br/>parse → resolve → decide]
    PIPE --> LLM{{"LLMClient<br/>mock: rule parser · live: Anthropic<br/>same ParsedUtterance schema"}}
    PIPE --> RES["resolution<br/>alias + unit · customer phonetic match<br/>relative dates"]
    PIPE -->|"all fields ≥ 0.75<br/>& 1 customer"| LEDGER[ledger service<br/>undo / edit = append-only]
    PIPE -->|otherwise| PEND[pending + questions]
    LEDGER --> KG
    INS[insights<br/>FIFO features · pattern heuristic<br/>seasons] --> KG
    REM[reminder drafts<br/>never sent] --> KG
  end

  subgraph KG["Knowledge graph (app/kg)"]
    ONTO[ontology.yaml<br/>+ 162 products / 828 aliases<br/>→ JSON-LD · Turtle] -.validates.-> STORE
    STORE[(GraphStore<br/>NetworkX + SQLite<br/>every fact has provenance)]
  end
```

**Graph model:** `Customer —owes→ Shop`, `Customer —bought→ Product`, `Customer —paid→ Shop`, `Alias —alias_of→ Product`,
`Customer —belongs_to_shop→ Shop`, plus `LedgerEvent —recorded_for→ Customer`, `—includes→ Product`, `—corrects→ LedgerEvent`,
and `Reminder —about→ Customer`. Every node and edge carries **provenance**: `source` (an utterance id, `seed:…` or
`correction:…`), `timestamp`, `confidence`, and `method` (rule, model or human).

| Path | What's there |
|---|---|
| `app/kg/` | `ontology.yaml` + loader and validator (JSON-LD and Turtle export via rdflib), `graph_store.py` (GraphStore protocol, NetworkX + SQLite), `provenance.py`, `llm.py` / `llm_anthropic.py` (LLMClient), `names.py` (Devanagari and Gujarati romaniser, phonetic keys, honorifics) |
| `app/core/` | `parser.py` (rule parser), `products.py` (alias and unit resolution), `customers.py` (fuzzy match and disambiguation), `dates.py`, `pipeline.py` (confirm-vs-save), `ledger.py` (balances, undo, edit), `insights.py` (features, pattern, seasons), `reminders.py` |
| `app/api/main.py` | All endpoints, request logging, static web mount |
| `web/` | Next.js 15 App Router + TypeScript + Tailwind 4 + Cytoscape.js PWA |
| `data/` | `products.yaml` (alias catalogue), `calendar.yaml` (festival and wedding windows), `generate.py` (seeded ledger) |
| `evals/` | 114 labelled + 25 untuned utterances, 65 alias hold-outs, `run_eval.py` |

**API:** `POST /utterance`, `POST /utterance/confirm`, `GET /customers`, `GET /customers/{id}`, `GET /ledger`,
`POST /ledger/{id}/undo`, `POST /ledger/{id}/edit`, `GET /insights`, `GET /graph`, `POST /reminders/draft`,
`GET /products/aliases`, `GET /health`, `GET /ontology?format=json|jsonld|turtle`.
Own-shop endpoints: `GET|PUT /shop`, `POST /shop/start-empty`, `POST /customers`, `GET /products/vocab`, `POST /products`,
`POST /products/{sku}/aliases`, `PATCH /products/{sku}`, `GET /export?format=turtle|jsonld|json&include_catalog=`.
OpenAPI is at `/docs`.

## Results (from `make eval`)

| | Tuned set (114, white-box) | Untuned set (25, written after tuning) |
|---|---|---|
| Intent accuracy | 99% | 100% |
| Customer resolution | 99% | 96% |
| Item / qty+unit accuracy | 99% / 99% | 94% / 89% |
| Whole record correct | 98% | 84% |
| Disambiguation trigger rate | 100% (9/9) | 100% (2/2) |
| **False-save rate** | **0%** | **0%** after one safety fix (the first untuned run found 1: *chicken → chickpea*) |

Alias resolution: 100% of catalogue aliases, 97.6% of seeded noisy variants, 96.9% of hand-written hold-out spellings.
Coverage is about 97% on `app/` (the gate is ≥ 80% on `app/core`). The failure cases are listed in the report.

## What's mocked vs real

| Area | In this POV | Notes |
|---|---|---|
| Utterance understanding | **Real (rules)** in `LLM_MODE=mock`, the default | A deterministic parser is the "mock LLM". Tests and demo need no key. |
| LLM parsing | **Real but optional**: `LLM_MODE=live` + `ANTHROPIC_API_KEY` | `messages.parse(output_format=ParsedUtterance)` with model `ANTHROPIC_MODEL` (default `claude-opus-5-5`). It falls back to rules on any error. Not exercised by tests. |
| Speech-to-text | **Browser** Web Speech API | Accuracy and availability depend on the browser and need network (Chrome). There is no on-device Indic ASR yet. |
| Knowledge graph | **Real**: NetworkX + SQLite, ontology-validated writes, RDF export | Single shop, single process. |
| Customer and ledger data | **Synthetic** in `make demo`: seeded (42), 60 customers, Jun–Nov 2025, fixed clock 30 Nov 2025 | **Your own data** in `make start`: empty start, real date, kept in `data/myshop.db` (git-ignored). |
| Product catalogue and prices | **Curated by hand**, approximate | 162 products, Hindi / Gujarati / Marathi transliterations. |
| Payment pattern | **Real computation, demo heuristic** | Transparent, evidence-listed, *not* a credit score, not for lending. |
| Reminders | **Drafts only** | Never sent; copy to clipboard. |
| Auth, multi-user, sync | **Not built** | One shop per database, no login: run it on your own device. See next steps. |

## Why a knowledge graph (and not just a table + an LLM)

- **Local language is a vocabulary problem before it is an AI problem.** *chawal / chokha / tandul*, *saakar / khand / cheeni* and *tel* (which oil?) are aliases of the same few products. The ontology makes these `Alias —alias_of→ Product` facts, with units (kilo, paav, ser, dozen) as first-class concepts. Adding a dialect means adding data, not retraining a model.
- **The graph is the guardrail.** The LLM (or rule parser) only extracts strings. Resolving them to a real customer and SKU is deterministic and validated against the ontology, so the system cannot invent a product, and two matching "Ramesh"es become a question rather than a guess.
- **Provenance makes it trustworthy.** Every fact records who or what asserted it (rule, model or human), from which utterance, and with what confidence. Corrections are new facts that `correct` old ones, which gives an audit trail a shopkeeper (and later a lender) can rely on.
- **Insights are graph queries.** Who owes what, bought what, and pays when, across festivals, is a traversal over `owes`, `bought` and `paid`, and the "why" behind each signal is the evidence path.
- **Interoperable by design.** The ontology exports to JSON-LD and Turtle, so the same model can map onto open-network schemas (ONDC catalogues, Account Aggregator data) instead of becoming another silo.

## Fit with Digital India: a commercialisation path

India has over 6 crore MSMEs and more than a crore kirana stores. Most informal credit lives in notebooks. The public digital stack already provides the rails; what is missing is a voice-first, local-language front end that turns everyday shop talk into structured, consented data. One path:

| Digital India building block | How kirana-ledger would plug in |
|---|---|
| **Bhashini** (national language AI mission) | Swap browser speech for Bhashini ASR and translation APIs across 22 scheduled languages. The ontology's alias layer absorbs dialect variation. |
| **UPI** | Shopkeeper-initiated collect links in reminder drafts. Incoming UPI credits auto-matched to open udhaar as `payment` events with `method: rule` provenance. |
| **Account Aggregator + DEPA consent** | Opt-in, purpose-bound, revocable sharing of *summarised* cash-flow and repayment patterns, never raw entries, to help shops (not their customers) access working capital. |
| **OCEN** (Open Credit Enablement Network) | The consented ledger summary becomes an input for small-ticket working-capital loans to the shop, through lender partners. |
| **ONDC** | The same product ontology maps a kirana's catalogue onto ONDC listings, a step from a credit ledger to digital selling. |
| **Udyam registration / MSME schemes** | Simple monthly books help shops formalise and qualify for schemes that need records. |
| **IndiaAI Mission** | A fit for compute or grant programmes that back Indic-language AI for underserved users. |

**Business model hypothesis (to be validated):** freemium. A free tier up to about 50 customers, then **₹199–299/month** for unlimited customers, reminders and multi-device sync. Distribution through FMCG distributors, banks' merchant networks and UPI/QR partners who already visit these shops. Future revenue from consented, regulated credit partnerships where the shop opts in, never from selling data. Pilot plan: 20–30 shops in Gujarat and North India for 8 weeks, measuring entries per day, taps per entry, and udhaar recovered.

*These are alignment opportunities, not existing partnerships or endorsements.*

## Next steps to productize

1. **Offline-first sync.** On-device store (SQLite/IndexedDB) with an append-only event log that already matches the provenance model. CRDT-style merge of events (events are immutable, corrections are new events), sync over flaky 2G/3G, and a WhatsApp-style "pending" indicator.
2. **Real voice models for Indian languages.** On-device or edge ASR fine-tuned on kirana vocabulary (for example IndicConformer / Whisper variants), with code-mixed Hinglish and Gujarati. Hot-word biasing from the shop's own customer names and catalogue. Evaluate on recorded audio from consenting shopkeepers, by dialect and noise level.
3. **Lender partnership and consent model.** The shop's ledger belongs to the shop and its customers. Any sharing with an NBFC or lender would be opt-in per customer, purpose-bound and revocable, via India's Account Aggregator / DEPA consent framework. It should share summaries, not raw entries, and come with a fairness review of any derived signal. Until then the pattern stays a private, shop-only helper and is never a credit score.
4. **Catalogue and pricing.** Shop-specific price lists, barcode or SKU import, distributor catalogues, and learning new aliases from confirmed corrections (the human-confirmed provenance is already there).
5. **Collections workflow.** Scheduled reminder suggestions, UPI collect links (sent by the shopkeeper), and part-payment plans.
6. **Pricing hypothesis: ₹199–299 / month per shop.** Free tier up to about 50 customers. The value case: recovering even one forgotten ₹1,000 udhaar a month pays for it. Validate with 20–30 pilot shops across Gujarat and North India, measuring entries per day, confirmation taps per entry, and collections before and after.
7. **Hardening.** Auth and roles (owner, helper), backups, PII handling (phone numbers are deliberately absent today), observability, and multi-shop tenancy (the ontology already has `belongs_to_shop`).

## Development

- `make dev`: API with reload on :8141, serving the last web build.
- For live UI work, run `cd web && NEXT_PUBLIC_API_URL=http://localhost:8141 npm run dev` (port 3141; CORS allowed).
- `make lint` (ruff) · `make web-build` · `make web-test`.
- Logs are JSON lines on stdout with `request_id`, `method`, `path`, `status` and `ms`, plus utterance decisions.
