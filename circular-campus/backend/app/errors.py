"""Application errors mapped to HTTP responses in main.py."""
from __future__ import annotations

from typing import Optional


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str, *, field: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.field = field


class ValidationFailed(AppError):
    status_code = 422


class NotAuthenticated(AppError):
    status_code = 401


class PermissionDenied(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409
