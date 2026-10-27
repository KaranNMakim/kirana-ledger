# Changelog

## Phase 0: scaffold
- Repo layout (`app/kg`, `app/core`, `app/api`, `web`, `data`, `docs`, `evals`), `PLAN.md`.
- `Makefile` → `scripts/tasks.py` (cross-platform task runner), ruff, pytest + coverage gate.
- Env-driven `Settings` (fixed demo clock `KIRANA_TODAY=2025-11-30`), JSON-lines structured logging.
- FastAPI skeleton with `/health`.

## Phase 1: ontology + alias data
- `app/kg/ontology.yaml`: 6 classes (Shop, Customer, Product, Alias, LedgerEvent, Reminder), 9 relations
  (`owes`, `bought`, `paid`, `alias_of`, `belongs_to_shop` + supporting), unit vocabulary (kg/g/ser/paav/l/ml/pcs/dozen/packet/...).
- `data/products.yaml`: 162 products with 828 aliases in English and Hindi/Gujarati/Marathi transliteration, plus 17 generic terms (tel, dal, chai, sabun ...).
- Loader validates the schema (domain/range, required props), categories, units, prices, alias languages, and alias uniqueness. Exports to JSON-LD and Turtle via rdflib. `GET /ontology?format=json|jsonld|turtle`.
- `GraphStore` protocol with an implementation backed by a NetworkX MultiDiGraph and SQLite write-through. Writes are ontology-validated and every node and edge carries provenance.
- `names.py`: Devanagari and Gujarati romaniser, canonical folding, phonetic keys, Jaro-Winkler, honorific stripping.

## Phase 2: utterance parser + matching
- `app/core/parser.py`: deterministic rule parser (mock LLM). It tags each token's role (date, product span, number, unit, currency, cue, postposition, honorific, filler), then derives customer, intent, items, amount and relative date. Covers Hinglish, transliterated Gujarati, and Devanagari/Gujarati script via the romaniser.
- Handles number words (do sau, dedh, dhai, paav, aadha), `aadha/pura hisaab` balance expressions, line amounts (`50 rupaye ka tel`), post-positioned quantities, mixed payment+sale (forces confirmation), and names that collide with products.
- `app/core/products.py`: alias resolution as a ladder: exact → generic default (`tel` → sunflower oil, conf 0.8) → generic ambiguous (`dal`) → fuzzy. Also unit conversion (g→kg, paav, dozen) and price-list line amounts.
- `app/core/customers.py`: honorific stripping, phonetic and string scoring, surname weighting and a gender hint. When two people tie it returns `ambiguous` with candidates instead of guessing.
- `app/kg/llm.py`: `LLMClient` protocol, `MockLLMClient`, factory. `llm_anthropic.py` is the live client and uses `messages.parse(output_format=ParsedUtterance)`, so both modes return the same schema. It falls back to the rules on any error.

## Phase 3: ledger graph + insights
- `ledger.py`: LedgerEvent nodes with `recorded_for`, `includes`, `bought`, `paid` and `owes` edges, and incrementally maintained balances. Undo and edit are append-only: the old event is `voided` with a human-provenance history entry, and an edit adds a new event that `corrects` the old one.
- `insights.py`: FIFO-allocated payment features (average days to pay, partial-payment share, oldest unpaid, payments per month, festive vs baseline lateness). The baseline excludes a 30-day spill-over after festivals and seasons that ended too recently to judge. Also the **Indicative payment pattern (demo heuristic)**: 0–100, banded, with every deduction listed as evidence and a not-a-credit-score disclaimer. Plus shop insights (top owed, late payers, monthly, seasons, top products) and Cytoscape graph elements.
- `reminders.py`: WhatsApp-style drafts in English, Hinglish and Gujarati transliteration, in gentle or firm tone, with Indian ₹ grouping. A live LLM may rewrite a draft only if the amount survives. Drafts are recorded as `Reminder` nodes with `sent: no`.
- `pipeline.py`: parse → resolve → per-field checks → auto-save, needs-confirmation (with disambiguation questions) or answered (balance queries). `confirm` supports customer, new customer, items, amount, intent, date and cancel.
- `data/generate.py`: seeded (42) Jun–Nov 2025 ledger with 60 customers and about 2,700 events. It has five personas, including chronic and festival-late payers, Diwali, Navratri and wedding boosts, and FIFO-consistent payment plans. `data/calendar.yaml` holds the seasons.

## Phase 4: API
- Endpoints: `POST /utterance`, `POST /utterance/confirm`, `GET /customers` (search, sort, owing_only), `GET /customers/{id}` (profile, pattern evidence, events incl. voided, reminder drafts), `GET /ledger`, `GET /ledger/{id}`, `POST /ledger/{id}/undo`, `POST /ledger/{id}/edit`, `GET /insights`, `GET /graph`, `POST /reminders/draft`, `GET /products/aliases`, `GET /health`, `GET /ontology`.
- Request logging middleware (JSON lines, `x-request-id`). Ledger errors map to 404/400. The web static export is served at `/app`.
- Contract tests (`tests/test_api.py`) run against a freshly generated demo DB.
