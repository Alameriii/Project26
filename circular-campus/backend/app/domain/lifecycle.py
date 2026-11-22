"""State machines for assets, requests and transfers (Phase 3 §2.4, FR-AST-6, C6).

Every status change in the application goes through one of these classes, so a
move that is not in the life-cycle tables is rejected in one place.
"""
from __future__ import annotations

from .enums import AssetStatus as A
from .enums import RequestStatus as R
from .enums import TransferStatus as T


class InvalidTransition(ValueError):
    """Raised when a requested status change is not allowed."""


class StateMachine:
    name = "item"
    transitions: dict = {}

    @classmethod
    def allowed_next(cls, current) -> set:
        return set(cls.transitions.get(current, set()))

    @classmethod
    def can_move(cls, current, target) -> bool:
        return target in cls.transitions.get(current, set())

    @classmethod
    def check(cls, current, target) -> None:
        if not cls.can_move(current, target):
            allowed = ", ".join(sorted(s.value for s in cls.allowed_next(current))) or "none (final state)"
            raise InvalidTransition(
                f"A {cls.name} cannot move from '{current.value}' to '{target.value}'. "
                f"Allowed next states: {allowed}."
            )


class AssetLifecycle(StateMachine):
    """Asset states table, Phase 3 §2.4."""

    name = "asset"
    transitions = {
        A.REGISTERED: {A.IN_USE, A.AVAILABLE},
        A.IN_USE: {A.AVAILABLE, A.UNDER_MAINTENANCE, A.PENDING_DISPOSITION},
        A.AVAILABLE: {A.RESERVED, A.IN_USE, A.UNDER_MAINTENANCE, A.PENDING_DISPOSITION},
        A.RESERVED: {A.IN_TRANSFER, A.AVAILABLE},
        A.IN_TRANSFER: {A.IN_USE},
        A.UNDER_MAINTENANCE: {A.IN_USE, A.AVAILABLE, A.PENDING_DISPOSITION},
        A.PENDING_DISPOSITION: {A.DONATED, A.RECYCLED, A.DISPOSED, A.IN_USE},
        A.DONATED: set(),
        A.RECYCLED: set(),
        A.DISPOSED: set(),
    }

    # Moves a user may make directly from the asset page. Reserved and In
    # Transfer are driven only by the request/transfer workflow; disposition
    # needs the end-of-life workflow (sustainability officer, BR-5), which is
    # outside the Phase 6 scope.
    manual = {
        A.REGISTERED: {A.IN_USE, A.AVAILABLE},
        A.IN_USE: {A.AVAILABLE, A.UNDER_MAINTENANCE},
        A.AVAILABLE: {A.IN_USE, A.UNDER_MAINTENANCE},
        A.UNDER_MAINTENANCE: {A.IN_USE, A.AVAILABLE},
    }

    @classmethod
    def manual_next(cls, current) -> set:
        return set(cls.manual.get(current, set()))


class RequestLifecycle(StateMachine):
    """Request states, Phase 3 §2.4 plus 'Open' from UC-6 alt 3a."""

    name = "request"
    transitions = {
        R.OPEN: {R.SUBMITTED, R.CANCELLED},
        R.SUBMITTED: {R.UNDER_REVIEW, R.APPROVED, R.REJECTED, R.CANCELLED, R.EXPIRED, R.OPEN},
        R.UNDER_REVIEW: {R.APPROVED, R.REJECTED, R.CANCELLED, R.EXPIRED},
        R.APPROVED: {R.FULFILLED, R.CANCELLED},
        R.REJECTED: set(),
        R.FULFILLED: set(),
        R.CANCELLED: set(),
        R.EXPIRED: set(),
    }


class TransferLifecycle(StateMachine):
    """Transfer states, Phase 3 §2.4."""

    name = "transfer"
    transitions = {
        T.SCHEDULED: {T.DISPATCHED, T.CANCELLED},
        T.DISPATCHED: {T.RECEIVED, T.CANCELLED, T.DISPUTED},
        T.RECEIVED: {T.COMPLETED},
        T.COMPLETED: set(),
        T.CANCELLED: set(),
        T.DISPUTED: set(),
    }
