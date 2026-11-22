"""Permission policy — Phase 3 §2.3 permission table and business rules BR-1..BR-4.

All checks run on the server for every action (FR-ACC-3, NFR-10). The interface
also hides controls, but that is only a convenience.
"""
from __future__ import annotations

from typing import Optional

from ..domain.enums import AssetStatus, Role
from ..errors import PermissionDenied
from ..models import Asset, ResourceRequest, Transfer, User

A = Role.ADMIN
REP = Role.DEPT_REP
CUS = Role.CUSTODIAN
REQ = Role.REQUESTER
SUS = Role.SUSTAINABILITY


class PermissionPolicy:
    """One place that answers 'may this user do this?'."""

    # ---- users and administration -------------------------------------------------
    @staticmethod
    def can_manage_users(user: User) -> bool:
        return user.has(A)

    @staticmethod
    def can_view_audit(user: User) -> bool:
        return user.has(A)

    # ---- assets -------------------------------------------------------------------
    @staticmethod
    def can_register_asset(user: User, department_id: Optional[int] = None) -> bool:
        if user.has(A):
            return True
        if user.has(REP, CUS):
            return department_id is None or department_id == user.department_id
        return False

    @staticmethod
    def can_manage_asset(user: User, asset: Asset) -> bool:
        """Edit, publish, withdraw, change status: admin, owning dept rep, or the asset's custodian."""
        if user.has(A):
            return True
        if user.has(REP) and asset.department_id == user.department_id:
            return True
        if user.has(CUS) and asset.custodian_id == user.id:
            return True
        return False

    @staticmethod
    def can_see_inventory_of_all(user: User) -> bool:
        return user.has(A, SUS)

    @staticmethod
    def can_view_asset(user: User, asset: Asset, involved: bool = False) -> bool:
        if asset.status == AssetStatus.AVAILABLE or involved:
            return True
        if user.has(A, SUS):
            return True
        return asset.department_id == user.department_id

    @staticmethod
    def can_see_value(user: User) -> bool:
        """FR-SRC-5: estimated value is hidden from users who are only Requesters."""
        return user.has(A, REP, CUS, SUS)

    # ---- requests -----------------------------------------------------------------
    @staticmethod
    def can_submit_request(user: User) -> bool:
        return user.has(A, REP, CUS, REQ)

    @staticmethod
    def can_view_request(user: User, req: ResourceRequest) -> bool:
        if user.has(A) or req.requester_id == user.id:
            return True
        if user.has(REP) and req.asset is not None and req.asset.department_id == user.department_id:
            return True
        if user.has(REP) and req.requester_department_id == user.department_id:
            return True
        return False

    @staticmethod
    def check_can_approve(user: User, req: ResourceRequest) -> None:
        """BR-3 (no self-approval) and BR-4 (owning department's representative or admin)."""
        if req.requester_id == user.id:
            raise PermissionDenied("You cannot approve or reject your own request (BR-3).")
        if user.has(A):
            return
        if user.has(REP) and req.asset is not None and req.asset.department_id == user.department_id:
            return
        raise PermissionDenied(
            "Only the owning department's representative or an administrator can decide on this request (BR-4).")

    @staticmethod
    def can_approve(user: User, req: ResourceRequest) -> bool:
        try:
            PermissionPolicy.check_can_approve(user, req)
            return True
        except PermissionDenied:
            return False

    # ---- transfers ----------------------------------------------------------------
    @staticmethod
    def can_dispatch(user: User, t: Transfer) -> bool:
        """Sending side: admin, sending dept rep, or the sending custodian."""
        if user.has(A):
            return True
        if user.has(REP) and t.from_department_id == user.department_id:
            return True
        return user.has(CUS) and t.from_custodian_id == user.id

    @staticmethod
    def can_confirm_receipt(user: User, t: Transfer) -> bool:
        """Receiving side: admin, receiving custodian, or receiving dept rep."""
        if user.has(A):
            return True
        if t.receiving_custodian_id == user.id:
            return True
        return user.has(REP) and t.to_department_id == user.department_id

    @staticmethod
    def can_view_transfer(user: User, t: Transfer) -> bool:
        if user.has(A, SUS):
            return True
        if user.department_id in (t.from_department_id, t.to_department_id):
            return True
        return user.id in (t.request.requester_id, t.receiving_custodian_id, t.from_custodian_id)

    @staticmethod
    def require(allowed: bool, message: str) -> None:
        if not allowed:
            raise PermissionDenied(message)
