"""Audit log, life-cycle history and in-app notifications (FR-AUD-1..3, FR-NOT-1)."""
from __future__ import annotations

from typing import Optional, Union

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import Role
from ..models import AuditLog, HistoryEvent, Notification, User


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "value") and not isinstance(value, (str, int, float, bool)):
        return value.value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class AuditService:
    """Append-only: this class only ever inserts rows."""

    def __init__(self, db: Session):
        self.db = db

    def log(self, user: Optional[User], action: str, entity_type: Optional[str] = None,
            entity_ref: Optional[str] = None, details: Optional[dict] = None) -> None:
        self.db.add(AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type,
                             entity_ref=entity_ref, details=_jsonable(details or {})))


class HistoryRecorder:
    def __init__(self, db: Session):
        self.db = db

    def record(self, entity_type: str, entity_id: int, action: str, summary: str, user: Optional[User],
               from_status=None, to_status=None, details: Optional[dict] = None) -> None:
        self.db.add(HistoryEvent(
            entity_type=entity_type, entity_id=entity_id, action=action, summary=summary,
            from_status=_jsonable(from_status), to_status=_jsonable(to_status),
            details=_jsonable(details or {}), user_id=user.id if user else None,
        ))


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def notify(self, users: Iterable[Optional[Union[User, int]]], title: str, body: str, link: Optional[str] = None,
               exclude: Optional[User] = None) -> None:
        seen: set[int] = set()
        for u in users:
            if u is None:
                continue
            uid = u if isinstance(u, int) else u.id
            if uid in seen or (exclude is not None and uid == exclude.id):
                continue
            seen.add(uid)
            self.db.add(Notification(user_id=uid, title=title, body=body, link=link))

    def department_users(self, department_id: int, role: Role) -> list[User]:
        users = self.db.scalars(select(User).where(User.department_id == department_id, User.active.is_(True))).all()
        return [u for u in users if role in u.roles]

    def admins(self) -> list[User]:
        users = self.db.scalars(select(User).where(User.active.is_(True))).all()
        return [u for u in users if Role.ADMIN in u.roles]
