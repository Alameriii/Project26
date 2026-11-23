"""Authorised review: approve or reject a request (C5, UC-8, FR-APR-1..4, BR-3, BR-4).

AI scores are shown to the approver as information only (BR-6); the decision
is always this explicit human action.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.matcher import MatchingEngine
from ..api.schemas import ApproveIn
from ..domain.enums import AssetStatus, RequestStatus, Role, TransferStatus
from ..errors import Conflict
from ..models import Asset, ResourceRequest, Transfer, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import aware, now, today
from .assets import spec_from_request
from .audit import AuditService, HistoryRecorder, NotificationService
from .codes import assign_code, temp_code
from .requests import RequestService


class ApprovalService:
    def __init__(self, db: Session):
        self.db = db
        self.requests = RequestService(db)
        self.audit = AuditService(db)
        self.history = HistoryRecorder(db)
        self.notes = NotificationService(db)

    def _check_decidable(self, user: User, req: ResourceRequest) -> None:
        P.check_can_approve(user, req)
        if req.status not in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW):
            raise Conflict(f"This request is {req.status.value}; it can no longer be decided.")

    def start_review(self, user: User, req: ResourceRequest) -> ResourceRequest:
        self._check_decidable(user, req)
        if req.status == RequestStatus.SUBMITTED and not req.queued:
            self.requests.set_status(req, RequestStatus.UNDER_REVIEW, user, "Review started",
                                     f"{user.name} started the review")
            self.audit.log(user, "request_review_started", "request", req.request_code)
            self.db.commit()
        return req

    # ------------------------------------------------------------------ approve
    def approve(self, user: User, req: ResourceRequest, data: ApproveIn) -> Transfer:
        self.requests.expire_overdue()
        self.db.refresh(req)
        self._check_decidable(user, req)
        asset = self.requests.assets.get(req.asset_id, lock=True)
        if req.queued or asset.reserved_by_request_id != req.id or asset.status != AssetStatus.RESERVED:
            raise Conflict("Another request holds the reservation on this asset. "
                           "Decide on that request first; this one is waiting in the queue.")
        if req.reserved_until and aware(req.reserved_until) <= now():
            raise Conflict("The reservation has expired.")

        if req.quantity < asset.quantity:
            asset = self._split(user, req, asset)
        else:
            self._reopen_queue(asset, req)

        self.requests.set_status(req, RequestStatus.APPROVED, user, "Approved", f"Approved by {user.name}",
                                 {"note": data.note, "method": data.method,
                                  "scheduled_date": data.scheduled_date})
        req.decided_by_id = user.id
        req.decided_at = now()
        req.decision_note = data.note
        req.reserved_until = None

        receiver = self._receiving_custodian(req)
        transfer = Transfer(
            transfer_code=temp_code(), request_id=req.id, asset_id=asset.id, quantity=req.quantity,
            from_department_id=asset.department_id, to_department_id=req.requester_department_id,
            from_custodian_id=asset.custodian_id, receiving_custodian_id=receiver.id,
            to_campus=req.delivery_campus, to_building=req.delivery_building, to_room=req.delivery_room,
            method=data.method, scheduled_date=data.scheduled_date, status=TransferStatus.SCHEDULED,
            approved_by_id=user.id,
        )
        self.db.add(transfer)
        assign_code(self.db, transfer, "transfer_code", "TRF")
        self.history.record("transfer", transfer.id, "Scheduled",
                            f"Scheduled after {user.name} approved {req.request_code}", user, None,
                            TransferStatus.SCHEDULED, {"method": data.method, "date": data.scheduled_date})
        self.history.record("asset", asset.id, "Transfer approved",
                            f"{req.request_code} approved by {user.name}; {transfer.transfer_code} scheduled",
                            user, details={"to_department": req.requester_department.name})
        self.notes.notify([req.requester_id], f"{req.request_code} approved",
                          f"{user.name} approved your request for {asset.name}. Transfer {transfer.transfer_code} "
                          f"is scheduled for {data.scheduled_date.strftime('%d %b %Y')}.",
                          link=f"/transfers/{transfer.id}")
        self.notes.notify([receiver, asset.custodian], f"Transfer {transfer.transfer_code} scheduled",
                          f"{asset.name} ({asset.asset_code}) moves from {asset.department.name} to "
                          f"{req.requester_department.name}.", link=f"/transfers/{transfer.id}", exclude=user)
        self.audit.log(user, "request_approved", "request", req.request_code,
                       {"transfer": transfer.transfer_code, "asset": asset.asset_code})
        self.db.commit()
        return transfer

    def _split(self, user: User, req: ResourceRequest, parent: Asset) -> Asset:
        """Partial quantity: the approved units become their own asset record.

        The new record holds the reservation and follows the transfer; the
        remaining units go back on the marketplace (Reserved → Available).
        """
        child = Asset(
            asset_code=temp_code(), name=parent.name, description=parent.description, category=parent.category,
            subcategory=parent.subcategory, tags=list(parent.tags or []), material=parent.material,
            quantity=req.quantity, department_id=parent.department_id, custodian_id=parent.custodian_id,
            campus=parent.campus, building=parent.building, room=parent.room,
            purchase_date=parent.purchase_date,
            estimated_value=(round(float(parent.estimated_value) * req.quantity / parent.quantity, 2)
                             if parent.estimated_value is not None else None),
            condition=parent.condition, status=AssetStatus.RESERVED, availability_note=parent.availability_note,
            available_until=parent.available_until, published_at=parent.published_at,
            reserved_by_request_id=req.id, parent_asset_id=parent.id, created_by_id=user.id,
        )
        self.db.add(child)
        assign_code(self.db, child, "asset_code", "AST")
        remaining = parent.quantity - req.quantity
        if parent.estimated_value is not None and child.estimated_value is not None:
            parent.estimated_value = round(float(parent.estimated_value) - float(child.estimated_value), 2)
        parent.quantity = remaining
        parent.reserved_by_request_id = None
        self.history.record("asset", child.id, "Split from parent",
                            f"{req.quantity} unit(s) separated from {parent.asset_code} for {req.request_code}",
                            user, None, AssetStatus.RESERVED, {"parent": parent.asset_code})
        self.history.record("asset", parent.id, "Units split off",
                            f"{req.quantity} unit(s) moved to {child.asset_code} for {req.request_code}; "
                            f"{remaining} remain", user, details={"child": child.asset_code})
        req.asset = child
        self.requests.release(parent, user, f"{remaining} unit(s) remain available after the split")
        return child

    def _reopen_queue(self, asset: Asset, approved: ResourceRequest) -> None:
        """Whole lot approved: queued requests for it go back to Open for new matches."""
        waiting = self.db.scalars(select(ResourceRequest).where(
            ResourceRequest.asset_id == asset.id, ResourceRequest.queued.is_(True),
            ResourceRequest.status == RequestStatus.SUBMITTED, ResourceRequest.id != approved.id)).all()
        for w in waiting:
            w.queued = False
            w.asset = None
            self.requests.set_status(w, RequestStatus.OPEN, None, "Returned to open",
                                     f"{asset.asset_code} was allocated to another request; "
                                     "this request is open for new matches.")
            self.notes.notify([w.requester_id], f"{w.request_code} is open again",
                              f"{asset.name} was allocated to an earlier request. Your request stays open "
                              "and you will be told when a matching listing appears.", link=f"/requests/{w.id}")

    def _receiving_custodian(self, req: ResourceRequest) -> User:
        if req.requester.has(Role.CUSTODIAN):
            return req.requester
        for role in (Role.CUSTODIAN, Role.DEPT_REP):
            people = self.notes.department_users(req.requester_department_id, role)
            if people:
                return sorted(people, key=lambda u: u.id)[0]
        return req.requester

    # ------------------------------------------------------------------ reject
    def reject(self, user: User, req: ResourceRequest, reason: str) -> list[dict]:
        self._check_decidable(user, req)
        held = req.asset is not None and req.asset.reserved_by_request_id == req.id
        self.requests.set_status(req, RequestStatus.REJECTED, user, "Rejected", f"Rejected by {user.name}",
                                 {"reason": reason})
        req.decided_by_id = user.id
        req.decided_at = now()
        req.decision_note = reason
        req.queued = False
        req.reserved_until = None
        rejected_asset = req.asset
        if held:
            asset = self.requests.assets.get(req.asset_id, lock=True)
            self.requests.release(asset, user, f"{req.request_code} was rejected")

        alternatives = self._alternatives(req, exclude_id=rejected_asset.id if rejected_asset else None)
        alt_text = ""
        if alternatives:
            alt_text = " Other available options: " + "; ".join(
                f"{a['name']} ({a['asset_code']}, {a['score_percent']}%)" for a in alternatives) + "."
        self.notes.notify([req.requester_id], f"{req.request_code} rejected",
                          f"{user.name} rejected your request. Reason: {reason}.{alt_text}",
                          link=f"/requests/{req.id}")
        self.history.record("request", req.id, "Alternatives suggested",
                            f"{len(alternatives)} alternative asset(s) suggested to the requester", None,
                            details={"alternatives": alternatives})
        self.audit.log(user, "request_rejected", "request", req.request_code, {"reason": reason})
        self.db.commit()
        return alternatives

    def _alternatives(self, req: ResourceRequest, exclude_id: Optional[int]) -> list[dict]:
        """FR-APR-3: up to 3 other available assets for the requester."""
        pool = [a for a in self.db.scalars(select(Asset).where(Asset.status == AssetStatus.AVAILABLE)).all()
                if a.id != exclude_id]
        outcome = MatchingEngine().match(spec_from_request(req), pool, today(), top_n=3)
        by_id = {a.id: a for a in pool}
        return [{"asset_id": r.asset_id, "asset_code": by_id[r.asset_id].asset_code, "name": by_id[r.asset_id].name,
                 "score_percent": round(r.score * 100), "reason": r.reason} for r in outcome.results]
