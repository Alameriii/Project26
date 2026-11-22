"""Login, sessions and the current-user dependency (UC-1, FR-ACC-2/4/6).

Sessions are random tokens kept in an httpOnly cookie; only a SHA-256 hash of
the token is stored. A session idle for longer than SESSION_IDLE_MINUTES is
rejected, and five wrong passwords lock the account for 15 minutes.
"""
from __future__ import annotations

from typing import Optional

import hashlib
import secrets
from datetime import timedelta

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..errors import NotAuthenticated, PermissionDenied
from ..models import User, UserSession
from ..timeutil import aware, now
from .passwords import verify_password

COOKIE_NAME = "cc_session"


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def login(self, email: str, password: str) -> tuple[User, str]:
        from ..services.audit import AuditService

        audit = AuditService(self.db)
        user = self.db.scalar(select(User).where(User.email == email.strip().lower()))
        generic = "Email or password is incorrect."
        if user is None:
            audit.log(None, "login_failed", details={"email": email.strip().lower()})
            self.db.commit()
            raise NotAuthenticated(generic)
        if not user.active:
            audit.log(user, "login_refused_inactive")
            self.db.commit()
            raise NotAuthenticated("This account is deactivated. Please contact the system administrator.")
        locked = aware(user.locked_until)
        if locked and locked > now():
            minutes = max(1, int((locked - now()).total_seconds() // 60) + 1)
            raise NotAuthenticated(f"Too many failed attempts. The account is locked for {minutes} more minute(s).")
        if not verify_password(password, user.password_hash):
            user.failed_logins = (user.failed_logins or 0) + 1
            if user.failed_logins >= settings.max_failed_logins:
                user.locked_until = now() + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
                audit.log(user, "account_locked")
                self.db.commit()
                raise NotAuthenticated(
                    f"Too many failed attempts. The account is locked for {settings.lockout_minutes} minutes.")
            audit.log(user, "login_failed")
            self.db.commit()
            raise NotAuthenticated(generic)

        user.failed_logins = 0
        user.locked_until = None
        token = secrets.token_urlsafe(32)
        self.db.add(UserSession(token_hash=_hash_token(token), user_id=user.id))
        audit.log(user, "login")
        self.db.commit()
        return user, token

    def logout(self, token: Optional[str]) -> None:
        if not token:
            return
        sess = self.db.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
        if sess:
            sess.revoked = True
            self.db.commit()

    def resolve(self, token: Optional[str]) -> User:
        if not token:
            raise NotAuthenticated("Please sign in to continue.")
        sess = self.db.scalar(select(UserSession).where(UserSession.token_hash == _hash_token(token)))
        if sess is None or sess.revoked:
            raise NotAuthenticated("Your session has ended. Please sign in again.")
        idle_limit = timedelta(minutes=settings.session_idle_minutes)
        if now() - aware(sess.last_seen_at) > idle_limit:
            sess.revoked = True
            self.db.commit()
            raise NotAuthenticated("You were signed out after 30 minutes of inactivity.")
        user = sess.user
        if not user.active:
            raise NotAuthenticated("This account is deactivated.")
        sess.last_seen_at = now()
        self.db.commit()
        return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """FastAPI dependency: every protected endpoint resolves the user server-side (FR-ACC-3)."""
    # Simple CSRF guard for cookie auth: state-changing calls must carry a custom header
    # that a cross-site HTML form cannot add.
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-Requested-With") != "fetch":
        raise PermissionDenied("Missing request header.")
    return AuthService(db).resolve(request.cookies.get(COOKIE_NAME))
