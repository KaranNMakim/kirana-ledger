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
