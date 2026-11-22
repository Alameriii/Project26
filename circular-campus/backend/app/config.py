"""Application settings, read from environment variables (or backend/.env).

Secrets such as GEMINI_API_KEY live only on the server (NFR-11) and are never
sent to the browser.
"""
from __future__ import annotations

from typing import Optional

import os
from dataclasses import dataclass
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the project needs no extra dependency."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str
    gemini_api_key: Optional[str]
    gemini_model: str
    gemini_embedding_model: str
    ai_timeout_seconds: float
    session_idle_minutes: int
    max_failed_logins: int
    lockout_minutes: int
    reservation_working_days: int
    cookie_secure: bool
    frontend_dist: Path

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)


def get_settings() -> Settings:
    default_db = f"sqlite:///{(BACKEND_DIR / 'circular_campus.db').as_posix()}"
    return Settings(
        database_url=os.getenv("DATABASE_URL", default_db),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        gemini_embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "10")),  # FR-AI-9
        session_idle_minutes=int(os.getenv("SESSION_IDLE_MINUTES", "30")),  # FR-ACC-6
        max_failed_logins=int(os.getenv("MAX_FAILED_LOGINS", "5")),  # FR-ACC-4
        lockout_minutes=int(os.getenv("LOCKOUT_MINUTES", "15")),
        reservation_working_days=int(os.getenv("RESERVATION_WORKING_DAYS", "3")),  # BR-7
        cookie_secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        frontend_dist=Path(os.getenv("FRONTEND_DIST", str(PROJECT_DIR / "frontend" / "dist"))),
    )


settings = get_settings()
