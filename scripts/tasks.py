"""Cross-platform task runner behind the Makefile.

    python scripts/tasks.py <setup|seed|test|lint|eval|web-build|web-test|demo|dev|clean>
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
IS_WIN = os.name == "nt"
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")  # Windows consoles default to cp1252; logs contain ₹
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def npm() -> str:
    exe = shutil.which("npm.cmd" if IS_WIN else "npm") or shutil.which("npm")
    if not exe:
        sys.exit("npm not found: install Node.js LTS (https://nodejs.org) and re-run.")
    return exe


def run(cmd: list[str], cwd: Path = ROOT, env: dict | None = None) -> None:
    print("+", " ".join(cmd), flush=True)
    full_env = {**os.environ, **(env or {})}
    rc = subprocess.call(cmd, cwd=cwd, env=full_env)
    if rc:
        sys.exit(rc)


def setup() -> None:
    if not VENV_PY.exists():
        run([sys.executable, "-m", "venv", ".venv"])
    run([py(), "-m", "pip", "install", "-q", "-r", "requirements.txt"])
    if (WEB / "package.json").exists():
        run([npm(), "install", "--no-audit", "--no-fund"], cwd=WEB)


def seed() -> None:
    run([py(), "-m", "data.generate"])


def test() -> None:
    run([py(), "-m", "pytest", "--cov=app", "--cov-report=term"])
    print("\ncore/ coverage gate (>= 80%):")
    run([py(), "-m", "coverage", "report", "--include=app/core/*", "--fail-under=80"])
    if (WEB / "out").exists():
        web_test()
    else:
        print("(web smoke test skipped: run `make web-build` first)")


def lint() -> None:
    run([py(), "-m", "ruff", "check", "app", "tests", "scripts", "data", "evals"])


def eval_() -> None:
    run([py(), "-m", "evals.run_eval"])


def web_build(force: bool = True) -> None:
    out = WEB / "out"
    if not force and out.exists():
        return
    if not (WEB / "node_modules").exists():
        run([npm(), "install", "--no-audit", "--no-fund"], cwd=WEB)
    run([npm(), "run", "build"], cwd=WEB)


def web_test() -> None:
    run(["node", "--test", "tests/smoke.test.mjs"], cwd=WEB)


def serve(reload: bool = False) -> None:
    port = os.environ.get("PORT", "8141")
    cmd = [py(), "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", port]
    if reload:
        cmd += ["--reload", "--reload-dir", "app"]
    print(f"\n  kirana-ledger running →  http://localhost:{port}/app/   (API docs: /docs)\n", flush=True)
    run(cmd)


def demo() -> None:
    seed()  # fresh, reproducible state every demo
    web_build(force=False)
    serve()


def dev() -> None:
    if not (ROOT / "data" / "kirana.db").exists():
        seed()
    serve(reload=True)


def clean() -> None:
    for p in [ROOT / "data" / "kirana.db", WEB / "out", WEB / ".next"]:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()


TASKS = {
    "setup": setup, "seed": seed, "test": test, "lint": lint, "eval": eval_,
    "web-build": web_build, "web-test": web_test, "demo": demo, "dev": dev, "clean": clean,
}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        sys.exit(f"usage: tasks.py <{'|'.join(TASKS)}>")
    TASKS[sys.argv[1]]()
