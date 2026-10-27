"""Runtime settings, read from environment (and an optional .env file)."""

from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEMO_TODAY = dt.date(2025, 11, 30)


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


@dataclass(frozen=True)
class Settings:
    llm_mode: str = "mock"
    anthropic_model: str = "claude-opus-5-5"
    db_path: str = str(ROOT / "data" / "kirana.db")
    today_override: str = DEMO_TODAY.isoformat()
    confirm_threshold: float = 0.75
    log_level: str = "INFO"
    web_dir: Path = field(default=ROOT / "web" / "out")

    def today(self) -> dt.date:
        if self.today_override.lower() == "real":
            return dt.date.today()
        return dt.date.fromisoformat(self.today_override)

    @classmethod
    def from_env(cls) -> Settings:
        _load_dotenv(ROOT / ".env")
        db = os.environ.get("KIRANA_DB", "data/kirana.db")
        if db != ":memory:" and not Path(db).is_absolute():
            db = str(ROOT / db)
        return cls(
            llm_mode=os.environ.get("LLM_MODE", "mock").lower(),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5"),
            db_path=db,
            today_override=os.environ.get("KIRANA_TODAY", DEMO_TODAY.isoformat()),
            confirm_threshold=float(os.environ.get("CONFIRM_THRESHOLD", "0.75")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
