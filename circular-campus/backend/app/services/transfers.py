"""Transfers: dispatch, receipt confirmation, disputes and cancellation (C5/C6, UC-9, FR-TRF-1..6, BR-2).

A transfer only exists for an Approved request (FR-APR-4): it is created
inside ApprovalService.approve. Ownership, custodian and location change only
when the receiving side confirms receipt.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api.schemas import ConfirmIn
from ..domain.enums import AssetStatus, RequestStatus, Role, TransferStatus
from ..domain.lifecycle import InvalidTransition, TransferLifecycle
from ..errors import Conflict, NotFound, PermissionDenied
from ..models import Transfer, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import now
from .audit import AuditService, HistoryRecorder, NotificationService
from .requests import RequestService


class TransferService:
    def __init__(self, db: Session):
        self.db = db
        self.requests = RequestService(db)
        self.assets = self.requests.assets
        self.audit = AuditService(db)
        self.history = HistoryRecorder(db)
        self.notes = NotificationService(db)

    def get(self, transfer_id: int, *, lock: bool = False) -> Transfer:
        stmt = select(Transfer).where(Transfer.id == transfer_id)
        if lock:
            stmt = stmt.with_for_update()
        t = self.db.scalar(stmt)
        if t is None:
            raise NotFound("Transfer not found.")
        return t

    def get_visible(self, transfer_id: int, user: User) -> Transfer:
        t = self.get(transfer_id)
        if not P.can_view_transfer(user, t):
            raise PermissionDenied("You do not have access to this transfer.")
        return t

    def _set(self, t: Transfer, target: TransferStatus, user: User, action: str, summary: str,
             details: Optional[dict] = None) -> None:
        try:
            TransferLifecycle.check(t.status, target)
        except InvalidTransition as exc:
            raise Conflict(str(exc)) from exc
        previous = t.status
        t.status = target
        self.history.record("transfer", t.id, action, summary, user, previous, target, details)

    def _require_approved(self, t: Transfer) -> None:
        if t.request.status != RequestStatus.APPROVED:  # FR-APR-4 / BR-2
            raise Conflict("A transfer can only proceed for an Approved request.")

    # ------------------------------------------------------------------ dispatch
    def dispatch(self, user: User, t: Transfer, handover_note: Optional[str]) -> Transfer:
        if not P.can_dispatch(user, t):
            raise PermissionDenied("Only the sending department or custodian can mark this transfer dispatched.")
        self._require_approved(t)
        asset = self.assets.get(t.asset_id, lock=True)
        self._set(t, TransferStatus.DISPATCHED, user, "Dispatched", f"Marked dispatched by {user.name}",
                  {"handover_note": handover_note})
        t.dispatched_by_id = user.id
        t.dispatched_at = now()
        t.handover_note = handover_note
        self.assets.set_status(asset, AssetStatus.IN_TRANSFER, user, "Dispatched",
                               f"Left {asset.department.name} under {t.transfer_code}",
                               {"transfer": t.transfer_code})
        self.notes.notify([t.receiving_custodian_id, t.request.requester_id], f"{t.transfer_code} is on its way",
                          f"{asset.name} ({asset.asset_code}) was dispatched by {user.name}. "
                          "Please confirm receipt when it arrives.", link=f"/transfers/{t.id}", exclude=user)
        self.audit.log(user, "transfer_dispatched", "transfer", t.transfer_code)
        self.db.commit()
        return t

    # ------------------------------------------------------------------ confirm receipt
    def confirm(self, user: User, t: Transfer, data: ConfirmIn) -> Transfer:
        if not P.can_confirm_receipt(user, t):
            raise PermissionDenied("Only the receiving custodian or department can confirm receipt.")
        self._require_approved(t)
        asset = self.assets.get(t.asset_id, lock=True)
        receiver = t.receiving_custodian
        before = {"department": asset.department.name, "custodian": asset.custodian.name,
                  "location": asset.location_label, "condition": asset.condition.value}

        self._set(t, TransferStatus.RECEIVED, user, "Received",
                  f"Receipt confirmed by {user.name}; condition on arrival {data.condition_on_arrival.value}",
                  {"note": data.note})
        t.received_by_id = user.id
        t.received_at = now()
        t.condition_on_arrival = data.condition_on_arrival
        t.avoided_purchase = data.avoided_purchase
        t.closing_note = data.note

        asset.department_id = t.to_department_id
        asset.custodian_id = receiver.id
        asset.campus, asset.building, asset.room = t.to_campus, t.to_building, t.to_room
        asset.condition = data.condition_on_arrival
        asset.availability_note = None
        asset.available_until = None
        asset.published_at = None
        asset.reserved_by_request_id = None
        self.db.flush()
        self.db.refresh(asset)
        after = {"department": asset.department.name, "custodian": receiver.name,
                 "location": asset.location_label, "condition": asset.condition.value}
        self.assets.set_status(asset, AssetStatus.IN_USE, user, "Ownership transferred",
                               f"Received by {asset.department.name} under {t.transfer_code}",
                               {"transfer": t.transfer_code,
                                "changes": {k: {"old": before[k], "new": after[k]}
                                            for k in before if before[k] != after[k]}})

        self._set(t, TransferStatus.COMPLETED, user, "Completed", "Transfer completed",
                  {"avoided_purchase": data.avoided_purchase})
        self.requests.set_status(t.request, RequestStatus.FULFILLED, user, "Fulfilled",
                                 f"Fulfilled by reuse via {t.transfer_code}",
                                 {"avoided_purchase": data.avoided_purchase})
        self.notes.notify([t.from_custodian_id, t.approved_by_id, t.request.requester_id],
                          f"{t.transfer_code} received",
                          f"{user.name} confirmed receipt of {asset.name} ({asset.asset_code}).",
                          link=f"/transfers/{t.id}", exclude=user)
        self.audit.log(user, "transfer_received", "transfer", t.transfer_code,
                       {"asset": asset.asset_code, "avoided_purchase": data.avoided_purchase})
        self.db.commit()
        return t

    # ------------------------------------------------------------------ dispute
    def dispute(self, user: User, t: Transfer, note: str) -> Transfer:
        if not P.can_confirm_receipt(user, t):
            raise PermissionDenied("Only the receiving side can report a problem with this transfer.")
        self._set(t, TransferStatus.DISPUTED, user, "Disputed", f"Damage or loss reported by {user.name}",
                  {"note": note})
        t.closing_note = note
        self.history.record("asset", t.asset_id, "Transfer disputed",
                            f"{t.transfer_code}: damage or loss reported on arrival", user, details={"note": note})
        reps = (self.notes.department_users(t.from_department_id, Role.DEPT_REP)
                + self.notes.department_users(t.to_department_id, Role.DEPT_REP) + self.notes.admins())
        self.notes.notify(reps + [t.from_custodian_id], f"{t.transfer_code} disputed",
                          f"{user.name} reported a problem on arrival: {note}", link=f"/transfers/{t.id}",
                          exclude=user)
        self.audit.log(user, "transfer_disputed", "transfer", t.transfer_code, {"note": note})
        self.db.commit()
        return t

    # ------------------------------------------------------------------ cancel (Scheduled only)
    def cancel(self, user: User, t: Transfer, reason: Optional[str]) -> Transfer:
        if not P.can_dispatch(user, t):
            raise PermissionDenied("Only the sending department can cancel this transfer.")
        if t.status != TransferStatus.SCHEDULED:
            raise Conflict("Only a Scheduled transfer can be cancelled. A dispatched item must be received "
                           "or reported as disputed.")
        asset = self.assets.get(t.asset_id, lock=True)
        self._set(t, TransferStatus.CANCELLED, user, "Cancelled", f"Cancelled by {user.name}", {"reason": reason})
        t.closing_note = reason
        self.requests.set_status(t.request, RequestStatus.CANCELLED, user, "Cancelled",
                                 f"Transfer {t.transfer_code} was cancelled by {user.name}", {"reason": reason})
        self.requests.release(asset, user, f"{t.transfer_code} was cancelled")
        self.notes.notify([t.request.requester_id, t.receiving_custodian_id], f"{t.transfer_code} cancelled",
                          f"{user.name} cancelled the transfer of {asset.name}. Reason: {reason or 'not given'}.",
                          link=f"/requests/{t.request.id}", exclude=user)
        self.audit.log(user, "transfer_cancelled", "transfer", t.transfer_code, {"reason": reason})
        self.db.commit()
        return t
