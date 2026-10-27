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
