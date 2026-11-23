"""Resource requests, reservations, the waiting queue and expiry (C4, UC-6/7/18, FR-REQ-1..6, BR-7).

Concurrency rule ("the last item cannot go to two people"): an asset row is
locked while a request reserves it, a reservation belongs to exactly one
request (Asset.reserved_by_request_id), and later requests for the same asset
wait in a first-come queue instead of reserving it too.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.matcher import MatchingEngine, MatchOutcome, MatchSpec
from ..api.schemas import RequestCreate, RequestFields
from ..config import settings
from ..domain.enums import AssetStatus, RequestStatus, Role
from ..domain.lifecycle import InvalidTransition, RequestLifecycle
from ..errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from ..models import Asset, MatchRecommendation, ResourceRequest, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import add_working_days, aware, now, today
from .ai_log import AILogService
from .assets import AssetService
from .audit import AuditService, HistoryRecorder, NotificationService
from .codes import assign_code, temp_code


def spec_from_fields(fields: RequestFields, user: User) -> MatchSpec:
    return MatchSpec(category=fields.category, purpose=fields.purpose, specifications=fields.specifications,
                     quantity=fields.quantity, preferred_condition=fields.preferred_condition,
                     urgency=fields.urgency, delivery_campus=fields.delivery_campus,
                     delivery_building=fields.delivery_building, required_date=fields.required_date,
                     requester_department_id=user.department_id)


class MatchService:
    """Runs the matching engine for a user and logs the result (UC-7, FR-AUD-4)."""

    def __init__(self, db: Session, engine: Optional[MatchingEngine] = None):
        self.db = db
        self.engine = engine or MatchingEngine()

    def find(self, user: User, fields: RequestFields) -> tuple[MatchOutcome, int, dict[int, Asset]]:
        if not P.can_submit_request(user):
            raise PermissionDenied("Your role cannot submit resource requests.")
        spec = spec_from_fields(fields, user)
        pool = self.db.scalars(select(Asset).where(Asset.status == AssetStatus.AVAILABLE)).all()
        outcome = self.engine.match(spec, pool, today())
        log = AILogService(self.db).create(
            user, "matching", outcome.provider, outcome.model_version, spec.summary(),
            {"results": [r.to_dict() for r in outcome.results], "considered": outcome.considered,
             "excluded": outcome.excluded},
            outcome.results[0].confidence if outcome.results else None, outcome.fallback_reason)
        self.db.commit()
        return outcome, log.id, {a.id: a for a in pool}


class RequestService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.history = HistoryRecorder(db)
        self.notes = NotificationService(db)
        self.assets = AssetService(db)

    # ------------------------------------------------------------------ helpers
    def get(self, request_id: int, *, lock: bool = False) -> ResourceRequest:
        stmt = select(ResourceRequest).where(ResourceRequest.id == request_id)
        if lock:
            stmt = stmt.with_for_update()
        req = self.db.scalar(stmt)
        if req is None:
            raise NotFound("Request not found.")
        return req

    def get_visible(self, request_id: int, user: User) -> ResourceRequest:
        req = self.get(request_id)
        if not P.can_view_request(user, req):
            raise PermissionDenied("You do not have access to this request.")
        return req

    def set_status(self, req: ResourceRequest, target: RequestStatus, user: Optional[User], action: str,
                   summary: str, details: Optional[dict] = None) -> None:
        try:
            RequestLifecycle.check(req.status, target)
        except InvalidTransition as exc:
            raise Conflict(str(exc)) from exc
        previous = req.status
        req.status = target
        self.history.record("request", req.id, action, summary, user, previous, target, details)

    def owning_reps(self, asset: Asset) -> list[User]:
        return self.notes.department_users(asset.department_id, Role.DEPT_REP)

    # ------------------------------------------------------------------ reservation core
    def _reserve(self, req: ResourceRequest, asset: Asset, user: Optional[User]) -> None:
        req.queued = False
        req.reserved_until = add_working_days(now(), settings.reservation_working_days)
        asset.reserved_by_request_id = req.id
        self.assets.set_status(asset, AssetStatus.RESERVED, user, "Reserved",
                               f"Reserved for {req.request_code} until "
                               f"{aware(req.reserved_until).strftime('%a %d %b %Y')}",
                               {"request": req.request_code, "requester": req.requester.name})

    def _attach_asset(self, user: User, req: ResourceRequest, asset_id: int) -> None:
        asset = self.assets.get(asset_id, lock=True)
        if asset.department_id == user.department_id:
            raise ValidationFailed("You cannot request an asset that already belongs to your department.",
                                   field="asset_id")
        if asset.quantity < req.quantity:
            raise ValidationFailed(f"Only {asset.quantity} unit(s) are listed; you asked for {req.quantity}.",
                                   field="quantity")
        if asset.status == AssetStatus.AVAILABLE:
            req.asset = asset
            self.db.flush()
            self._reserve(req, asset, user)
        elif asset.status == AssetStatus.RESERVED:
            req.asset = asset
            req.queued = True  # FR-REQ-3: waits behind the current reservation
            req.reserved_until = None
            self.history.record("asset", asset.id, "Request queued",
                                f"{req.request_code} joined the waiting queue", user,
                                details={"request": req.request_code})
        else:
            raise Conflict(f"This asset is {asset.status.value} and cannot be requested.")

    def release(self, asset: Asset, user: Optional[User], why: str) -> None:
        """Return a reserved asset to the marketplace and give it to the next in the queue."""
        if asset.status == AssetStatus.RESERVED:
            asset.reserved_by_request_id = None
            self.assets.set_status(asset, AssetStatus.AVAILABLE, user, "Reservation released", why)
        self.promote_queue(asset)

    def promote_queue(self, asset: Asset) -> None:
        if asset.status != AssetStatus.AVAILABLE:
            return
        nxt = self.db.scalar(select(ResourceRequest).where(
            ResourceRequest.asset_id == asset.id, ResourceRequest.queued.is_(True),
            ResourceRequest.status == RequestStatus.SUBMITTED).order_by(ResourceRequest.created_at,
                                                                        ResourceRequest.id))
        if nxt is None:
            return
        if nxt.quantity > asset.quantity:
            nxt.queued = False
            nxt.asset = None
            self.set_status(nxt, RequestStatus.OPEN, None, "Returned to open",
                            "Not enough units left for this request; it is open for new matches.")
            self.notes.notify([nxt.requester_id], f"{nxt.request_code} is open again",
                              f"{asset.name} no longer has enough units for your request.",
                              link=f"/requests/{nxt.id}")
            self.promote_queue(asset)
            return
        self._reserve(nxt, asset, None)
        self.history.record("request", nxt.id, "Moved from queue", f"Now holds the reservation for "
                            f"{asset.asset_code}", None)
        self.notes.notify([nxt.requester_id], f"{nxt.request_code} is now first in line",
                          f"{asset.name} ({asset.asset_code}) is reserved for you pending approval.",
                          link=f"/requests/{nxt.id}")
        self.notes.notify(self.owning_reps(asset), f"Request {nxt.request_code} needs review",
                          f"{nxt.requester.name} is next in line for {asset.name} ({asset.asset_code}).",
                          link="/approvals")

    # ------------------------------------------------------------------ expiry (FR-REQ-6, BR-7)
    def expire_overdue(self) -> int:
        overdue = self.db.scalars(select(ResourceRequest).where(
            ResourceRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW]),
            ResourceRequest.queued.is_(False), ResourceRequest.reserved_until.is_not(None))).all()
        count = 0
        for req in overdue:
            if aware(req.reserved_until) > now():
                continue
            self.set_status(req, RequestStatus.EXPIRED, None, "Expired",
                            "No decision within 3 working days; the reservation was released.")
            req.reserved_until = None
            if req.asset and req.asset.reserved_by_request_id == req.id:
                self.release(req.asset, None, f"Reservation for {req.request_code} expired")
            self.notes.notify([req.requester_id], f"{req.request_code} expired",
                              "Your reservation passed 3 working days without a decision.",
                              link=f"/requests/{req.id}")
            if req.asset:
                self.notes.notify(self.owning_reps(req.asset), f"{req.request_code} expired",
                                  f"The reservation on {req.asset.asset_code} expired without a decision.")
            self.audit.log(None, "request_expired", "request", req.request_code)
            count += 1
        if count:
            self.db.commit()
        return count

    # ------------------------------------------------------------------ submit (UC-6)
    def create(self, user: User, data: RequestCreate) -> ResourceRequest:
        if not P.can_submit_request(user):
            raise PermissionDenied("Your role cannot submit resource requests.")
        ai_logs = AILogService(self.db)
        log = ai_logs.get_own(data.match_log_id, user, "matching")

        req = ResourceRequest(
            request_code=temp_code(), requester_id=user.id, requester_department_id=user.department_id,
            category=data.category, purpose=data.purpose, specifications=data.specifications,
            quantity=data.quantity, preferred_condition=data.preferred_condition, urgency=data.urgency,
            delivery_campus=data.delivery_campus, delivery_building=data.delivery_building,
            delivery_room=data.delivery_room, required_date=data.required_date,
            status=RequestStatus.OPEN if data.asset_id is None else RequestStatus.SUBMITTED,
            match_log_id=log.id if log else None,
        )
        self.db.add(req)
        assign_code(self.db, req, "request_code", "REQ")
        self.history.record("request", req.id, "Created",
                            f"Created by {user.name}" + (" as an open request" if data.asset_id is None else ""),
                            user, None, req.status)

        if data.asset_id is not None:
            self._attach_asset(user, req, data.asset_id)
        self._store_recommendations(user, req, log, data.asset_id)

        if req.asset:
            asset = req.asset
            if req.queued:
                self.history.record("request", req.id, "Queued",
                                    f"{asset.asset_code} is already reserved; waiting in the queue", user)
            self.notes.notify(self.owning_reps(asset) + [asset.custodian],
                              f"New request {req.request_code}",
                              f"{user.name} ({user.department.name}) requested {req.quantity} × {asset.name} "
                              f"({asset.asset_code})." + (" It is waiting in the queue." if req.queued else ""),
                              link="/approvals", exclude=user)
        self.audit.log(user, "request_submitted", "request", req.request_code,
                       {"asset_id": data.asset_id, "queued": req.queued, "status": req.status})
        self.db.commit()
        return req

    def _store_recommendations(self, user: User, req: ResourceRequest, log, chosen_asset_id: Optional[int]) -> None:
        if log is None:
            return
        results = (log.output or {}).get("results", [])
        chosen_rank = None
        for r in results:
            selected = r["asset_id"] == chosen_asset_id
            if selected:
                chosen_rank = r["rank"]
                req.match_score = r["score"]
                req.match_reason = r["reason"]
            self.db.add(MatchRecommendation(request_id=req.id, asset_id=r["asset_id"], rank=r["rank"],
                                            score=r["score"], confidence=r["confidence"],
                                            explanation=r["reason"], model_version=log.model_version,
                                            selected=selected))
        if chosen_asset_id is None:
            decision = "none_selected"
        elif chosen_rank is not None:
            decision = "selected"
        else:
            decision = "override"  # user picked an asset the AI did not recommend (FR-AI-18)
        AILogService(self.db).decide(log, user, decision, {"request": req.request_code,
                                                           "asset_id": chosen_asset_id, "rank": chosen_rank})

    def select_asset(self, user: User, req: ResourceRequest, asset_id: int, match_log_id: Optional[int]) -> ResourceRequest:
        """Attach an asset to an Open request (UC-6 alt 3a, later)."""
        if req.requester_id != user.id:
            raise PermissionDenied("Only the requester can choose an asset for this request.")
        if req.status != RequestStatus.OPEN:
            raise Conflict("Only open requests can have an asset selected.")
        log = AILogService(self.db).get_own(match_log_id, user, "matching")
        self.set_status(req, RequestStatus.SUBMITTED, user, "Asset selected", f"Asset selected by {user.name}")
        self._attach_asset(user, req, asset_id)
        if log:
            req.match_log_id = log.id
            self._store_recommendations(user, req, log, asset_id)
        asset = req.asset
        self.notes.notify(self.owning_reps(asset) + [asset.custodian], f"New request {req.request_code}",
                          f"{user.name} requested {req.quantity} × {asset.name} ({asset.asset_code}).",
                          link="/approvals", exclude=user)
        self.audit.log(user, "request_asset_selected", "request", req.request_code, {"asset_id": asset_id})
        self.db.commit()
        return req

    # ------------------------------------------------------------------ cancel (UC-18, FR-REQ-5)
    def cancel(self, user: User, req: ResourceRequest, reason: Optional[str]) -> ResourceRequest:
        if req.requester_id != user.id and not user.has(Role.ADMIN):
            raise PermissionDenied("Only the requester can cancel this request.")
        if req.status not in (RequestStatus.OPEN, RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW):
            raise Conflict(f"A request that is {req.status.value} can no longer be cancelled.")
        held = req.asset is not None and req.asset.reserved_by_request_id == req.id
        self.set_status(req, RequestStatus.CANCELLED, user, "Cancelled", f"Cancelled by {user.name}",
                        {"reason": reason})
        req.queued = False
        req.reserved_until = None
        if held:
            asset = self.assets.get(req.asset_id, lock=True)
            self.release(asset, user, f"{req.request_code} was cancelled")
            self.notes.notify(self.owning_reps(asset), f"{req.request_code} cancelled",
                              f"{user.name} cancelled the request for {asset.asset_code}.", exclude=user)
        self.audit.log(user, "request_cancelled", "request", req.request_code, {"reason": reason})
        self.db.commit()
        return req
