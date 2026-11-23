"""Human-readable IDs (FR-AST-2): AST-0001, REQ-0001, TRF-0001."""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session


def temp_code() -> str:
    return "TMP-" + uuid.uuid4().hex[:10]


def assign_code(db: Session, obj, attr: str, prefix: str) -> None:
    """Flush to get the database id, then derive a unique code from it."""
    db.flush()
    setattr(obj, attr, f"{prefix}-{obj.id:04d}")
