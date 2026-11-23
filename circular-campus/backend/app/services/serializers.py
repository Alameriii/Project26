"""Turning models into API responses. Fields are trimmed by role (FR-SRC-5, UC-20)."""
from __future__ import annotations

from typing import Optional

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.enums import AssetStatus, RequestStatus, Role, TransferStatus
from ..domain.lifecycle import AssetLifecycle
from ..models import Asset, HistoryEvent, MatchRecommendation, ResourceRequest, Transfer, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import aware, now


def _dt(value):
    value = aware(value) if hasattr(value, "tzinfo") else value
    return value.isoformat() if value else None


def user_brief(u: Optional[User]) -> Optional[dict]:
    if u is None:
        return None
    return {"id": u.id, "name": u.name, "department": u.department.name if u.department else None}


def user_full(u: User) -> dict:
    return {
        "id": u.id, "name": u.name, "email": u.email, "active": u.active,
        "department": {"id": u.department.id, "name": u.department.name, "code": u.department.code,
                       "campus": u.department.campus, "building": u.department.building},
        "roles": sorted(r.value for r in u.roles),
        "role_labels": [r.label for r in sorted(u.roles, key=lambda r: r.value)],
        "can": {
            "register_assets": P.can_register_asset(u),
            "submit_requests": P.can_submit_request(u),
            "approve_requests": u.has(Role.ADMIN, Role.DEPT_REP),
            "manage_users": P.can_manage_users(u),
            "view_audit": P.can_view_audit(u),
            "see_value": P.can_see_value(u),
            "see_all_inventory": P.can_see_inventory_of_all(u),
        },
    }


def asset_dict(a: Asset, user: User, *, detail: bool = False, db: Optional[Session] = None) -> dict:
    d = {
        "id": a.id, "asset_code": a.asset_code, "name": a.name, "description": a.description,
        "category": a.category, "subcategory": a.subcategory, "tags": a.tags or [], "material": a.material,
        "quantity": a.quantity, "condition": a.condition.value, "status": a.status.value,
        "department": {"id": a.department.id, "name": a.department.name, "code": a.department.code},
        "custodian": user_brief(a.custodian),
        "campus": a.campus, "building": a.building, "room": a.room, "location": a.location_label,
        "purchase_date": a.purchase_date.isoformat() if a.purchase_date else None,
        "availability_note": a.availability_note,
        "available_until": a.available_until.isoformat() if a.available_until else None,
        "published_at": _dt(a.published_at), "created_at": _dt(a.created_at), "updated_at": _dt(a.updated_at),
        "parent_asset_id": a.parent_asset_id,
    }
    if P.can_see_value(user):
        d["estimated_value"] = float(a.estimated_value) if a.estimated_value is not None else None
    if detail:
        manage = P.can_manage_asset(user, a)
        manual = sorted(s.value for s in AssetLifecycle.manual_next(a.status)) if manage else []
        own_dept = a.department_id == user.department_id
        d["actions"] = {
            "can_edit": manage and a.status not in (AssetStatus.DONATED, AssetStatus.RECYCLED, AssetStatus.DISPOSED),
            "can_publish": manage and a.status in (AssetStatus.REGISTERED, AssetStatus.IN_USE),
            "can_withdraw": manage and a.status == AssetStatus.AVAILABLE,
            "status_options": [s for s in manual if s != AssetStatus.AVAILABLE.value],
            "can_request": P.can_submit_request(user) and not own_dept
            and a.status in (AssetStatus.AVAILABLE, AssetStatus.RESERVED),
            "request_will_queue": a.status == AssetStatus.RESERVED,
            "allowed_next_states": sorted(s.value for s in AssetLifecycle.allowed_next(a.status)),
        }
        if db is not None:
            queued = db.scalar(select(ResourceRequest.id).where(
                ResourceRequest.asset_id == a.id, ResourceRequest.queued.is_(True),
                ResourceRequest.status.in_([RequestStatus.SUBMITTED]))) is not None
            d["has_queue"] = queued
            holder = db.get(ResourceRequest, a.reserved_by_request_id) if a.reserved_by_request_id else None
            d["reserved_for"] = ({"request_code": holder.request_code, "id": holder.id,
                                  "reserved_until": _dt(holder.reserved_until)}
                                 if holder and (manage or holder.requester_id == user.id) else None)
    return d


def request_dict(r: ResourceRequest, user: User, *, detail: bool = False, db: Optional[Session] = None) -> dict:
    d = {
        "id": r.id, "request_code": r.request_code, "status": r.status.value, "queued": r.queued,
        "category": r.category, "purpose": r.purpose, "specifications": r.specifications,
        "quantity": r.quantity, "preferred_condition": r.preferred_condition.value, "urgency": r.urgency.value,
        "delivery_campus": r.delivery_campus, "delivery_building": r.delivery_building,
        "delivery_room": r.delivery_room, "required_date": r.required_date.isoformat(),
        "requester": user_brief(r.requester),
        "requester_department": {"id": r.requester_department.id, "name": r.requester_department.name},
        "asset": ({"id": r.asset.id, "asset_code": r.asset.asset_code, "name": r.asset.name,
                   "status": r.asset.status.value, "condition": r.asset.condition.value,
                   "quantity": r.asset.quantity,
                   "department": {"id": r.asset.department.id, "name": r.asset.department.name},
                   "location": r.asset.location_label}
                  if r.asset else None),
        "reserved_until": _dt(r.reserved_until), "match_score": r.match_score, "match_reason": r.match_reason,
        "decided_by": user_brief(r.decided_by), "decided_at": _dt(r.decided_at), "decision_note": r.decision_note,
        "created_at": _dt(r.created_at), "updated_at": _dt(r.updated_at),
    }
    mine = r.requester_id == user.id
    active = r.status in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW)
    holder = bool(r.asset and r.asset.reserved_by_request_id == r.id)
    d["actions"] = {
        "can_cancel": (mine or user.has(Role.ADMIN)) and r.status in (
            RequestStatus.OPEN, RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW),
        "can_decide": active and P.can_approve(user, r),
        "can_approve": active and holder and not r.queued and P.can_approve(user, r),
        "can_start_review": r.status == RequestStatus.SUBMITTED and holder and not r.queued and P.can_approve(user, r),
        "can_select_asset": mine and r.status == RequestStatus.OPEN,
        "self_request": mine,
    }
    if detail and db is not None:
        transfer = db.scalar(select(Transfer).where(Transfer.request_id == r.id))
        d["transfer"] = {"id": transfer.id, "transfer_code": transfer.transfer_code,
                         "status": transfer.status.value} if transfer else None
        d["history"] = history(db, "request", r.id)
        recs = db.scalars(select(MatchRecommendation).where(MatchRecommendation.request_id == r.id)
                          .order_by(MatchRecommendation.rank)).all()
        d["recommendations"] = [{"rank": m.rank, "score": m.score, "score_percent": round(m.score * 100),
                                 "confidence": m.confidence, "explanation": m.explanation,
                                 "model_version": m.model_version, "selected": m.selected,
                                 "asset": {"id": m.asset.id, "asset_code": m.asset.asset_code,
                                           "name": m.asset.name}} for m in recs]
        if r.queued and r.asset_id:
            ahead = db.scalars(select(ResourceRequest).where(
                ResourceRequest.asset_id == r.asset_id, ResourceRequest.queued.is_(True),
                ResourceRequest.status == RequestStatus.SUBMITTED,
                ResourceRequest.created_at < r.created_at)).all()
            d["queue_position"] = len(ahead) + 1
    return d


def transfer_dict(t: Transfer, user: User, *, detail: bool = False, db: Optional[Session] = None) -> dict:
    d = {
        "id": t.id, "transfer_code": t.transfer_code, "status": t.status.value, "quantity": t.quantity,
        "request": {"id": t.request.id, "request_code": t.request.request_code,
                    "requester": user_brief(t.request.requester)},
        "asset": {"id": t.asset.id, "asset_code": t.asset.asset_code, "name": t.asset.name,
                  "status": t.asset.status.value},
        "from_department": {"id": t.from_department.id, "name": t.from_department.name},
        "to_department": {"id": t.to_department.id, "name": t.to_department.name},
        "from_custodian": user_brief(t.from_custodian),
        "receiving_custodian": user_brief(t.receiving_custodian),
        "destination": ", ".join(x for x in (t.to_campus, t.to_building, t.to_room) if x),
        "method": t.method.value, "scheduled_date": t.scheduled_date.isoformat(),
        "approved_by": user_brief(t.approved_by), "approved_at": _dt(t.approved_at),
        "dispatched_by": user_brief(t.dispatched_by), "dispatched_at": _dt(t.dispatched_at),
        "handover_note": t.handover_note,
        "received_by": user_brief(t.received_by), "received_at": _dt(t.received_at),
        "condition_on_arrival": t.condition_on_arrival.value if t.condition_on_arrival else None,
        "avoided_purchase": t.avoided_purchase, "closing_note": t.closing_note,
        "created_at": _dt(t.created_at),
    }
    d["actions"] = {
        "can_dispatch": t.status == TransferStatus.SCHEDULED and P.can_dispatch(user, t),
        "can_cancel": t.status == TransferStatus.SCHEDULED and P.can_dispatch(user, t),
        "can_confirm": t.status == TransferStatus.DISPATCHED and P.can_confirm_receipt(user, t),
        "can_dispute": t.status == TransferStatus.DISPATCHED and P.can_confirm_receipt(user, t),
    }
    if detail and db is not None:
        d["history"] = history(db, "transfer", t.id)
    return d


def history(db: Session, entity_type: str, entity_id: int) -> list[dict]:
    """Timeline, newest first (FR-AUD-2)."""
    events = db.scalars(select(HistoryEvent).where(HistoryEvent.entity_type == entity_type,
                                                   HistoryEvent.entity_id == entity_id)
                        .order_by(HistoryEvent.created_at.desc(), HistoryEvent.id.desc())).all()
    return [{"id": e.id, "action": e.action, "summary": e.summary, "from_status": e.from_status,
             "to_status": e.to_status, "details": e.details, "user": user_brief(e.user),
             "at": _dt(e.created_at)} for e in events]


def asset_history(db: Session, asset: Asset, user: User) -> list[dict]:
    items = history(db, "asset", asset.id)
    # A record split off for a partial transfer inherits its parent's earlier story (C6).
    parent_id, cutoff = asset.parent_asset_id, aware(asset.created_at)
    while parent_id:
        parent = db.get(Asset, parent_id)
        if parent is None:
            break
        for e in history(db, "asset", parent.id):
            at = datetime.fromisoformat(e["at"]) if e["at"] else None
            if at and cutoff and at <= cutoff:
                e["summary"] = f"{e['summary']} (recorded on {parent.asset_code})"
                items.append(e)
        parent_id, cutoff = parent.parent_asset_id, aware(parent.created_at)
    if not P.can_see_value(user):  # UC-20: requesters don't see cost or value fields
        for item in items:
            changes = item.get("details", {}).get("changes")
            if isinstance(changes, dict):
                changes.pop("estimated_value", None)
            item.get("details", {}).pop("estimated_value", None)
    return items


def now_iso() -> str:
    return now().isoformat()
