"""REST API (JSON over /api). Every route resolves the user server-side and the
services enforce permissions, so hiding a button is never the only protection."""
from __future__ import annotations

from typing import Optional

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..ai.classifier import ClassificationService
from ..ai.taxonomy import taxonomy_as_dict
from ..config import settings
from ..database import get_db
from ..domain.enums import (
    ROLE_LABELS,
    AssetStatus,
    Condition,
    RequestStatus,
    Role,
    TransferMethod,
    TransferStatus,
    Urgency,
)
from ..domain.locations import LOCATIONS
from ..errors import NotFound, PermissionDenied, ValidationFailed
from ..models import Asset, AuditLog, Department, Notification, ResourceRequest, Transfer, User
from ..security.auth import COOKIE_NAME, AuthService, current_user
from ..security.passwords import hash_password
from ..security.permissions import PermissionPolicy as P
from ..services.ai_log import AILogService
from ..services.approvals import ApprovalService
from ..services.assets import AssetService
from ..services.audit import AuditService
from ..services.requests import MatchService, RequestService
from ..services.search import AssetSearchService, SearchFilters
from ..services.serializers import (
    asset_dict,
    asset_history,
    request_dict,
    transfer_dict,
    user_brief,
    user_full,
)
from ..services.transfers import TransferService
from . import schemas as S

router = APIRouter(prefix="/api")


def sweep(db: Session = Depends(get_db)) -> None:
    """Expire overdue reservations before serving request-related data (FR-REQ-6)."""
    RequestService(db).expire_overdue()


# ============================================================== auth (UC-1)
@router.post("/auth/login")
def login(body: S.LoginIn, response: Response, db: Session = Depends(get_db)):
    user, token = AuthService(db).login(body.email, body.password)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
                        path="/")
    return {"user": user_full(user)}


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    AuthService(db).logout(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: User = Depends(current_user)):
    return {"user": user_full(user)}


# ============================================================== reference data
@router.get("/meta")
def meta(user: User = Depends(current_user), db: Session = Depends(get_db)):
    departments = db.scalars(select(Department).where(Department.active.is_(True)).order_by(Department.name)).all()
    custodians = []
    for u in db.scalars(select(User).where(User.active.is_(True)).order_by(User.name)).all():
        if u.has(Role.CUSTODIAN, Role.DEPT_REP):
            custodians.append({"id": u.id, "name": u.name, "department_id": u.department_id})
    return {
        "categories": taxonomy_as_dict(),
        "conditions": [c.value for c in Condition],
        "asset_statuses": [s.value for s in AssetStatus],
        "request_statuses": [s.value for s in RequestStatus],
        "transfer_statuses": [s.value for s in TransferStatus],
        "urgencies": [u.value for u in Urgency],
        "transfer_methods": [m.value for m in TransferMethod],
        "locations": LOCATIONS,
        "departments": [{"id": d.id, "name": d.name, "code": d.code, "campus": d.campus,
                         "building": d.building} for d in departments],
        "custodians": custodians,
        "roles": [{"value": r.value, "label": ROLE_LABELS[r]} for r in Role],
        "ai": ai_status_dict(),
    }


def ai_status_dict() -> dict:
    if settings.ai_configured:
        return {"configured": True, "provider": "Gemini API", "model": settings.gemini_model,
                "embedding_model": settings.gemini_embedding_model,
                "label": "Gemini configured (falls back to local rules on error or timeout)"}
    return {"configured": False, "provider": "Local rule-based fallback", "model": None,
            "label": "Local rule-based fallback — no AI service key configured"}


@router.get("/ai/status")
def ai_status(user: User = Depends(current_user)):
    return ai_status_dict()


# ============================================================== dashboard
@router.get("/dashboard", dependencies=[Depends(sweep)])
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    mine = db.scalars(select(ResourceRequest).where(ResourceRequest.requester_id == user.id)
                      .order_by(ResourceRequest.updated_at.desc()).limit(5)).all()
    approvals = _approval_queue(db, user) if user.has(Role.ADMIN, Role.DEPT_REP) else []
    transfers = _transfers_for(db, user, "action")
    available = db.scalar(select(func.count(Asset.id)).where(Asset.status == AssetStatus.AVAILABLE))
    dept_assets = db.scalar(select(func.count(Asset.id)).where(Asset.department_id == user.department_id))
    unread = db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id,
                                                                 Notification.read.is_(False)))
    return {
        "counts": {"available_listings": available, "department_assets": dept_assets,
                   "pending_approvals": len([r for r in approvals if not r.queued]),
                   "transfers_needing_action": len(transfers), "unread_notifications": unread,
                   "my_open_requests": db.scalar(select(func.count(ResourceRequest.id)).where(
                       ResourceRequest.requester_id == user.id,
                       ResourceRequest.status.in_([RequestStatus.OPEN, RequestStatus.SUBMITTED,
                                                   RequestStatus.UNDER_REVIEW, RequestStatus.APPROVED])))},
        "my_requests": [request_dict(r, user) for r in mine],
        "approvals": [request_dict(r, user) for r in approvals[:5]],
        "transfers": [transfer_dict(t, user) for t in transfers[:5]],
    }


# ============================================================== assets (C2, C3)
@router.get("/assets")
def list_assets(
    q: Optional[str] = None, scope: str = "marketplace", category: Optional[str] = None,
    condition: Optional[Condition] = None, department_id: Optional[int] = None, campus: Optional[str] = None,
    building: Optional[str] = None, status: Optional[AssetStatus] = None, min_quantity: Optional[int] = Query(None, ge=1),
    max_age_years: Optional[float] = Query(None, ge=0), min_value: Optional[float] = Query(None, ge=0),
    max_value: Optional[float] = Query(None, ge=0), sort: str = "relevance",
    user: User = Depends(current_user), db: Session = Depends(get_db),
):
    if scope not in ("marketplace", "inventory"):
        raise ValidationFailed("Unknown scope.", field="scope")
    f = SearchFilters(q=q, scope=scope, category=category, condition=condition, department_id=department_id,
                      campus=campus, building=building, status=status, min_quantity=min_quantity,
                      max_age_years=max_age_years, min_value=min_value, max_value=max_value, sort=sort)
    results = AssetSearchService(db).search(user, f)
    return {"total": len(results), "items": [dict(asset_dict(a, user), relevance=s) for a, s in results[:300]]}


@router.post("/assets", status_code=201)
def create_asset(body: S.AssetCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    asset = AssetService(db).register(user, body)
    return {"asset": asset_dict(asset, user, detail=True, db=db)}


@router.get("/assets/{asset_id}", dependencies=[Depends(sweep)])
def get_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc = AssetService(db)
    asset = svc.get_visible(asset_id, user)
    return {"asset": asset_dict(asset, user, detail=True, db=db), "history": asset_history(db, asset, user)}


@router.put("/assets/{asset_id}")
def update_asset(asset_id: int, body: S.AssetUpdate, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    svc = AssetService(db)
    asset = svc.update(user, svc.get(asset_id, lock=True), body)
    return {"asset": asset_dict(asset, user, detail=True, db=db)}


@router.post("/assets/{asset_id}/status")
def change_asset_status(asset_id: int, body: S.StatusChangeIn, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    svc = AssetService(db)
    asset = svc.change_status(user, svc.get(asset_id, lock=True), body.to_status, body.note)
    return {"asset": asset_dict(asset, user, detail=True, db=db)}


@router.post("/assets/{asset_id}/publish")
def publish_asset(asset_id: int, body: S.PublishIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    svc = AssetService(db)
    asset = svc.publish(user, svc.get(asset_id, lock=True), body)
    return {"asset": asset_dict(asset, user, detail=True, db=db)}


@router.post("/assets/{asset_id}/withdraw")
def withdraw_asset(asset_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc = AssetService(db)
    asset = svc.withdraw(user, svc.get(asset_id, lock=True))
    return {"asset": asset_dict(asset, user, detail=True, db=db)}


# ============================================================== AI (advice only)
@router.post("/ai/classify")
def classify(body: S.ClassifyIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not P.can_register_asset(user):
        raise PermissionDenied("Only users who can register assets can use classification.")
    result, fallback = ClassificationService().classify(body.name, body.description, body.specifications)
    log = AILogService(db).create(user, "classification", result.provider, result.model_version,
                                  f"name='{body.name}'; description='{body.description[:200]}'",
                                  result.to_dict(), result.confidence, fallback)
    db.commit()
    notice = None
    if result.provider != "gemini":
        notice = (f"AI service unavailable ({fallback.rstrip('.')}), so this suggestion was made by local "
                  "keyword rules." if settings.ai_configured and fallback else
                  "Suggestion made by local keyword rules (no AI service configured).")
    return {"suggestion": result.to_dict(), "log_id": log.id, "notice": notice}


@router.post("/ai/match")
def match(body: S.RequestFields, user: User = Depends(current_user), db: Session = Depends(get_db)):
    outcome, log_id, assets = MatchService(db).find(user, body)
    items = []
    for r in outcome.results:
        d = r.to_dict()
        d["asset"] = asset_dict(assets[r.asset_id], user)
        items.append(d)
    return {"log_id": log_id, "provider": outcome.provider, "model_version": outcome.model_version,
            "notice": outcome.notice, "considered": outcome.considered, "excluded": outcome.excluded,
            "matches": items}


# ============================================================== requests (C4)
@router.get("/requests", dependencies=[Depends(sweep)])
def list_requests(scope: str = "mine", status: Optional[RequestStatus] = None,
                  user: User = Depends(current_user), db: Session = Depends(get_db)):
    if scope == "mine":
        stmt = select(ResourceRequest).where(ResourceRequest.requester_id == user.id)
        if status:
            stmt = stmt.where(ResourceRequest.status == status)
        items = db.scalars(stmt.order_by(ResourceRequest.created_at.desc())).all()
    elif scope == "approvals":
        if not user.has(Role.ADMIN, Role.DEPT_REP):
            raise PermissionDenied("Only department representatives and administrators review requests.")
        items = _approval_queue(db, user, include_decided=status is not None)
        if status:
            items = [r for r in items if r.status == status]
    elif scope == "all":
        if not user.has(Role.ADMIN):
            raise PermissionDenied("Only administrators can list all requests.")
        stmt = select(ResourceRequest)
        if status:
            stmt = stmt.where(ResourceRequest.status == status)
        items = db.scalars(stmt.order_by(ResourceRequest.created_at.desc())).all()
    else:
        raise ValidationFailed("Unknown scope.", field="scope")
    return {"items": [request_dict(r, user) for r in items]}


def _approval_queue(db: Session, user: User, include_decided: bool = False) -> list[ResourceRequest]:
    statuses = [RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW]
    if include_decided:
        statuses += [RequestStatus.APPROVED, RequestStatus.REJECTED, RequestStatus.FULFILLED,
                     RequestStatus.EXPIRED, RequestStatus.CANCELLED]
    stmt = select(ResourceRequest).join(Asset, ResourceRequest.asset_id == Asset.id).where(
        ResourceRequest.status.in_(statuses))
    if not user.has(Role.ADMIN):
        stmt = stmt.where(Asset.department_id == user.department_id)
    items = db.scalars(stmt.order_by(ResourceRequest.queued, ResourceRequest.created_at)).all()
    return items


@router.post("/requests", status_code=201)
def create_request(body: S.RequestCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    req = RequestService(db).create(user, body)
    return {"request": request_dict(req, user, detail=True, db=db)}


@router.get("/requests/{request_id}", dependencies=[Depends(sweep)])
def get_request(request_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    req = RequestService(db).get_visible(request_id, user)
    return {"request": request_dict(req, user, detail=True, db=db)}


@router.post("/requests/{request_id}/cancel")
def cancel_request(request_id: int, body: S.CancelIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    svc = RequestService(db)
    req = svc.cancel(user, svc.get(request_id, lock=True), body.reason)
    return {"request": request_dict(req, user, detail=True, db=db)}


@router.post("/requests/{request_id}/select-asset")
def select_asset(request_id: int, body: S.SelectAssetIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    svc = RequestService(db)
    req = svc.select_asset(user, svc.get(request_id, lock=True), body.asset_id, body.match_log_id)
    return {"request": request_dict(req, user, detail=True, db=db)}


@router.post("/requests/{request_id}/start-review", dependencies=[Depends(sweep)])
def start_review(request_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    req = svc.start_review(user, svc.requests.get(request_id, lock=True))
    return {"request": request_dict(req, user, detail=True, db=db)}


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: int, body: S.ApproveIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    transfer = svc.approve(user, svc.requests.get(request_id, lock=True), body)
    return {"transfer": transfer_dict(transfer, user, detail=True, db=db),
            "request": request_dict(transfer.request, user)}


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: int, body: S.RejectIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    svc = ApprovalService(db)
    req = svc.requests.get(request_id, lock=True)
    alternatives = svc.reject(user, req, body.reason)
    return {"request": request_dict(req, user, detail=True, db=db), "alternatives": alternatives}


# ============================================================== transfers (C5, C6)
def _transfers_for(db: Session, user: User, scope: str) -> list[Transfer]:
    stmt = select(Transfer).order_by(Transfer.updated_at.desc())
    items = [t for t in db.scalars(stmt).all() if P.can_view_transfer(user, t)]
    if scope == "action":
        items = [t for t in items if (t.status == TransferStatus.SCHEDULED and P.can_dispatch(user, t))
                 or (t.status == TransferStatus.DISPATCHED and P.can_confirm_receipt(user, t))]
    return items


@router.get("/transfers", dependencies=[Depends(sweep)])
def list_transfers(scope: str = "all", user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"items": [transfer_dict(t, user) for t in _transfers_for(db, user, scope)]}


@router.get("/transfers/{transfer_id}")
def get_transfer(transfer_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = TransferService(db).get_visible(transfer_id, user)
    return {"transfer": transfer_dict(t, user, detail=True, db=db)}


@router.post("/transfers/{transfer_id}/dispatch")
def dispatch_transfer(transfer_id: int, body: S.DispatchIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    svc = TransferService(db)
    t = svc.dispatch(user, svc.get(transfer_id, lock=True), body.handover_note)
    return {"transfer": transfer_dict(t, user, detail=True, db=db)}


@router.post("/transfers/{transfer_id}/confirm")
def confirm_transfer(transfer_id: int, body: S.ConfirmIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    svc = TransferService(db)
    t = svc.confirm(user, svc.get(transfer_id, lock=True), body)
    return {"transfer": transfer_dict(t, user, detail=True, db=db)}


@router.post("/transfers/{transfer_id}/dispute")
def dispute_transfer(transfer_id: int, body: S.DisputeIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    svc = TransferService(db)
    t = svc.dispute(user, svc.get(transfer_id, lock=True), body.note)
    return {"transfer": transfer_dict(t, user, detail=True, db=db)}


@router.post("/transfers/{transfer_id}/cancel")
def cancel_transfer(transfer_id: int, body: S.CancelIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    svc = TransferService(db)
    t = svc.cancel(user, svc.get(transfer_id, lock=True), body.reason)
    return {"transfer": transfer_dict(t, user, detail=True, db=db)}


# ============================================================== notifications (C8, partial)
@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(40)).all()
    unread = sum(1 for n in items if not n.read)
    return {"unread": unread, "items": [{"id": n.id, "title": n.title, "body": n.body, "link": n.link,
                                         "read": n.read, "at": n.created_at.isoformat()} for n in items]}


@router.post("/notifications/read-all")
def read_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id,
                                                   Notification.read.is_(False))).all():
        n.read = True
    db.commit()
    return {"ok": True}


# ============================================================== administration (UC-15, UC-21)
def _require_admin(user: User) -> None:
    if not P.can_manage_users(user):
        raise PermissionDenied("Only system administrators can do this.")


@router.get("/admin/users")
def admin_users(user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    return {"items": [user_full(u) for u in db.scalars(select(User).order_by(User.name)).all()]}


@router.post("/admin/users", status_code=201)
def admin_create_user(body: S.UserCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _require_admin(user)
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise ValidationFailed("A user with this email already exists.", field="email")
    if db.get(Department, body.department_id) is None:
        raise ValidationFailed("Choose a department.", field="department_id")
    new = User(name=body.name, email=email, password_hash=hash_password(body.password),
               department_id=body.department_id, roles_csv="")
    new.roles = body.roles
    db.add(new)
    db.flush()
    AuditService(db).log(user, "user_created", "user", email, {"roles": body.roles})
    db.commit()
    db.refresh(new)
    return {"user": user_full(new)}


@router.patch("/admin/users/{user_id}")
def admin_update_user(user_id: int, body: S.UserUpdate, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    _require_admin(user)
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("User not found.")
    changes = {}
    if body.active is False and target.id == user.id:
        raise ValidationFailed("You cannot deactivate your own account.", field="active")
    if body.roles is not None and target.id == user.id and Role.ADMIN not in body.roles:
        raise ValidationFailed("You cannot remove your own administrator role.", field="roles")
    if body.name is not None:
        changes["name"] = body.name
        target.name = body.name
    if body.department_id is not None:
        if db.get(Department, body.department_id) is None:
            raise ValidationFailed("Choose a department.", field="department_id")
        changes["department_id"] = body.department_id
        target.department_id = body.department_id
    if body.roles is not None:
        changes["roles"] = [r.value for r in body.roles]
        target.roles = body.roles
    if body.active is not None:
        changes["active"] = body.active
        target.active = body.active
    if body.password:
        changes["password"] = "reset"
        target.password_hash = hash_password(body.password)
        target.failed_logins = 0
        target.locked_until = None
    AuditService(db).log(user, "user_updated", "user", target.email, changes)
    db.commit()
    db.refresh(target)
    return {"user": user_full(target)}


@router.post("/admin/departments", status_code=201)
def admin_create_department(body: S.DepartmentCreate, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    _require_admin(user)
    if db.scalar(select(Department).where(or_(Department.code == body.code, Department.name == body.name))):
        raise ValidationFailed("A department with this code or name already exists.", field="code")
    d = Department(code=body.code, name=body.name, campus=body.campus, building=body.building)
    db.add(d)
    AuditService(db).log(user, "department_created", "department", body.code)
    db.commit()
    return {"department": {"id": d.id, "code": d.code, "name": d.name, "campus": d.campus, "building": d.building}}


@router.get("/admin/audit")
def admin_audit(action: Optional[str] = None, user_id: Optional[int] = None, entity: Optional[str] = None,
                date_from: Optional[date] = None, date_to: Optional[date] = None,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not P.can_view_audit(user):
        raise PermissionDenied("Only system administrators can view the audit log.")
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if entity:
        stmt = stmt.where(AuditLog.entity_ref.ilike(f"%{entity}%"))
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    rows = db.scalars(stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(300)).all()
    AuditService(db).log(user, "audit_log_viewed")  # UC-21: opening the log is itself recorded
    db.commit()
    actions = sorted(a for (a,) in db.execute(select(AuditLog.action).distinct()).all())
    return {"actions": actions, "items": [{"id": r.id, "at": r.created_at.isoformat(), "user": user_brief(r.user),
                                           "action": r.action, "entity_type": r.entity_type,
                                           "entity_ref": r.entity_ref, "details": r.details} for r in rows]}
