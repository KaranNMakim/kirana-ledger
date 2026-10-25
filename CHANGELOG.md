# Changelog

## Phase 0: scaffold
- Repo layout (`app/kg`, `app/core`, `app/api`, `web`, `data`, `docs`, `evals`), `PLAN.md`.
- `Makefile` → `scripts/tasks.py` (cross-platform task runner), ruff, pytest + coverage gate.
- Env-driven `Settings` (fixed demo clock `KIRANA_TODAY=2025-11-30`), JSON-lines structured logging.
- FastAPI skeleton with `/health`.
