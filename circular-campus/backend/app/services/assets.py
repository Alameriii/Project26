"""Asset registration, editing, publication and status management (C2, UC-2/4/16/17)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.matcher import NOTIFY_THRESHOLD, MatchingEngine, MatchSpec
from ..api.schemas import AssetCreate, AssetUpdate, PublishIn
from ..domain.enums import FINAL_ASSET_STATES, AssetStatus, RequestStatus, Role
from ..domain.lifecycle import AssetLifecycle, InvalidTransition
from ..errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from ..models import Asset, Department, ResourceRequest, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import now, today
from .ai_log import AILogService
from .audit import AuditService, HistoryRecorder, NotificationService
from .codes import assign_code, temp_code

EDITABLE_FIELDS = ("name", "description", "category", "subcategory", "tags", "material", "quantity",
                   "campus", "building", "room", "purchase_date", "estimated_value", "condition")


class AssetService:
    def __init__(self, db: Session):
        self.db = db
        self.audit = AuditService(db)
        self.history = HistoryRecorder(db)
        self.notes = NotificationService(db)

    # ------------------------------------------------------------------ lookups
    def get(self, asset_id: int, *, lock: bool = False) -> Asset:
        stmt = select(Asset).where(Asset.id == asset_id)
        if lock:
            stmt = stmt.with_for_update()
        asset = self.db.scalar(stmt)
        if asset is None:
            raise NotFound("Asset not found.")
        return asset

    def get_visible(self, asset_id: int, user: User) -> Asset:
        asset = self.get(asset_id)
        involved = self.db.scalar(select(ResourceRequest.id).where(
            ResourceRequest.asset_id == asset.id, ResourceRequest.requester_id == user.id)) is not None
        if not P.can_view_asset(user, asset, involved=involved):
            raise PermissionDenied("You do not have access to this asset.")
        return asset

    # ------------------------------------------------------------------ status core
    def set_status(self, asset: Asset, target: AssetStatus, user: Optional[User], action: str, summary: str,
                   details: Optional[dict] = None) -> None:
        """The only place an asset's status changes (FR-AST-6, C6)."""
        try:
            AssetLifecycle.check(asset.status, target)
        except InvalidTransition as exc:
            raise Conflict(str(exc)) from exc
        previous = asset.status
        asset.status = target
        self.history.record("asset", asset.id, action, summary, user, previous, target, details)

    # ------------------------------------------------------------------ register (UC-2)
    def _resolve_custodian(self, user: User, department: Department, custodian_id: Optional[int]) -> User:
        if custodian_id is not None:
            cust = self.db.get(User, custodian_id)
            if cust is None or not cust.active or cust.department_id != department.id:
                raise ValidationFailed("The custodian must be an active user in the owning department.",
                                       field="custodian_id")
            if not cust.has(Role.CUSTODIAN, Role.DEPT_REP):
                raise ValidationFailed("The custodian must hold the Asset Custodian or Department "
                                       "Representative role.", field="custodian_id")
            if user.has(Role.CUSTODIAN) and not user.has(Role.ADMIN, Role.DEPT_REP) and cust.id != user.id:
                raise PermissionDenied("Custodians can only register assets in their own custody.")
            return cust
        if user.has(Role.CUSTODIAN) and user.department_id == department.id:
            return user
        candidates = self.notes.department_users(department.id, Role.CUSTODIAN)
        if candidates:
            return sorted(candidates, key=lambda u: u.id)[0]
        if user.department_id == department.id:
            return user
        raise ValidationFailed("Choose a custodian for this asset.", field="custodian_id")

    def register(self, user: User, data: AssetCreate) -> Asset:
        department_id = data.department_id or user.department_id
        if not P.can_register_asset(user, department_id):
            raise PermissionDenied("You can only register assets for your own department.")
        department = self.db.get(Department, department_id)
        if department is None or not department.active:
            raise ValidationFailed("Choose an active department.", field="department_id")
        custodian = self._resolve_custodian(user, department, data.custodian_id)

        asset = Asset(
            asset_code=temp_code(), name=data.name, description=data.description, category=data.category,
            subcategory=data.subcategory, tags=data.tags, material=data.material, quantity=data.quantity,
            department_id=department.id, custodian_id=custodian.id, campus=data.campus, building=data.building,
            room=data.room, purchase_date=data.purchase_date, estimated_value=data.estimated_value,
            condition=data.condition, status=AssetStatus.REGISTERED, created_by_id=user.id,
        )
        self.db.add(asset)
        assign_code(self.db, asset, "asset_code", "AST")

        ai_logs = AILogService(self.db)
        log = ai_logs.get_own(data.ai_log_id, user, "classification")
        if log is not None:
            asset.ai_log_id = log.id
            ai_logs.decide(log, user, data.ai_decision or "edited", {
                "asset_code": asset.asset_code, "final_category": data.category,
                "final_subcategory": data.subcategory, "final_tags": data.tags,
                "final_condition": data.condition.value})

        self.history.record("asset", asset.id, "Registered",
                            f"Registered by {user.name} in {department.name}", user, None,
                            AssetStatus.REGISTERED, {"quantity": data.quantity, "condition": data.condition,
                                                     "custodian": custodian.name,
                                                     "ai_suggestion": data.ai_decision or "not used"})
        self.audit.log(user, "asset_registered", "asset", asset.asset_code,
                       {"category": data.category, "ai_log_id": data.ai_log_id, "ai_decision": data.ai_decision})
        if data.publish_now:
            self._publish(user, asset, data.availability_note, data.available_until)
        self.db.commit()
        return asset

    # ------------------------------------------------------------------ edit (UC-16)
    def update(self, user: User, asset: Asset, data: AssetUpdate) -> Asset:
        if not P.can_manage_asset(user, asset):
            raise PermissionDenied("You can only edit assets of your own department or in your custody.")
        if asset.status in FINAL_ASSET_STATES:
            raise Conflict("This asset is in a final state and is read-only (BR-8).")
        changes = {}
        for f in EDITABLE_FIELDS:
            new = getattr(data, f)
            old = getattr(asset, f)
            if f == "estimated_value" and old is not None:
                old = float(old)
            if new != old:
                changes[f] = {"old": old, "new": new}
                setattr(asset, f, new)
        if "quantity" in changes and asset.status in (AssetStatus.RESERVED, AssetStatus.IN_TRANSFER):
            raise Conflict("Quantity cannot change while the asset is reserved or in transfer.")
        if data.custodian_id is not None and data.custodian_id != asset.custodian_id:
            if not user.has(Role.ADMIN, Role.DEPT_REP):
                raise PermissionDenied("Only the department representative can change the custodian.")
            cust = self._resolve_custodian(user, asset.department, data.custodian_id)
            changes["custodian"] = {"old": asset.custodian.name, "new": cust.name}
            asset.custodian_id = cust.id
        if not changes:
            return asset
        self.history.record("asset", asset.id, "Edited", f"Details edited by {user.name}", user,
                            details={"changes": changes})
        self.audit.log(user, "asset_edited", "asset", asset.asset_code, {"fields": sorted(changes)})
        self.db.commit()
        return asset

    # ------------------------------------------------------------------ manual status change
    def change_status(self, user: User, asset: Asset, target: AssetStatus, note: Optional[str]) -> Asset:
        if not P.can_manage_asset(user, asset):
            raise PermissionDenied("You can only change the status of assets you manage.")
        if target == AssetStatus.AVAILABLE and asset.status in (AssetStatus.REGISTERED, AssetStatus.IN_USE):
            return self.publish(user, asset, PublishIn(availability_note=note))
        if asset.status == AssetStatus.AVAILABLE and target == AssetStatus.IN_USE:
            return self.withdraw(user, asset)
        if target not in AssetLifecycle.manual_next(asset.status):
            if AssetLifecycle.can_move(asset.status, target):
                raise Conflict(f"'{asset.status.value}' → '{target.value}' happens only through the request, "
                               "transfer or end-of-life workflow.")
            try:
                AssetLifecycle.check(asset.status, target)
            except InvalidTransition as exc:
                raise Conflict(str(exc)) from exc
        self.set_status(asset, target, user, "Status changed",
                        f"{asset.status.value} → {target.value} by {user.name}", {"note": note})
        self.audit.log(user, "asset_status_changed", "asset", asset.asset_code, {"to": target, "note": note})
        self.db.commit()
        return asset

    # ------------------------------------------------------------------ publish / withdraw (UC-4, UC-17)
    def publish(self, user: User, asset: Asset, data: PublishIn) -> Asset:
        if not P.can_manage_asset(user, asset):
            raise PermissionDenied("You can only publish assets of your own department or in your custody.")
        self._publish(user, asset, data.availability_note, data.available_until)
        self.db.commit()
        return asset

    def _publish(self, user: User, asset: Asset, note: Optional[str], until) -> None:
        if asset.status in (AssetStatus.UNDER_MAINTENANCE, AssetStatus.PENDING_DISPOSITION):
            raise Conflict(f"An asset that is {asset.status.value} cannot be published.")
        if asset.status not in (AssetStatus.REGISTERED, AssetStatus.IN_USE):
            raise Conflict(f"Only Registered or In Use assets can be published (this one is {asset.status.value}).")
        self.set_status(asset, AssetStatus.AVAILABLE, user, "Published as surplus",
                        f"Published to the marketplace by {user.name}",
                        {"availability_note": note, "available_until": until})
        asset.availability_note = note
        asset.available_until = until
        asset.published_at = now()
        self.audit.log(user, "asset_published", "asset", asset.asset_code)
        self.db.flush()
        self._notify_open_requests(asset)

    def _notify_open_requests(self, asset: Asset) -> None:
        """FR-NOT-3: tell requesters with an open request when a new listing scores 0.75 or more."""
        open_reqs = self.db.scalars(select(ResourceRequest).where(ResourceRequest.status == RequestStatus.OPEN)).all()
        if not open_reqs:
            return
        engine = MatchingEngine()
        pool = self.db.scalars(select(Asset).where(Asset.status == AssetStatus.AVAILABLE)).all()
        for req in open_reqs:
            outcome = engine.match(spec_from_request(req), pool, today(), top_n=len(pool))
            hit = next((r for r in outcome.results if r.asset_id == asset.id), None)
            if hit and hit.score >= NOTIFY_THRESHOLD:
                self.notes.notify([req.requester_id], f"New listing may suit {req.request_code}",
                                  f"{asset.name} ({asset.asset_code}) scored {round(hit.score * 100)}% for your "
                                  f"open request. {hit.reason}", link=f"/requests/{req.id}")

    def withdraw(self, user: User, asset: Asset) -> Asset:
        if not P.can_manage_asset(user, asset):
            raise PermissionDenied("You can only withdraw listings you manage.")
        if asset.status == AssetStatus.RESERVED:
            raise Conflict("This listing has an active request. Decide on the request before withdrawing it.")
        if asset.status != AssetStatus.AVAILABLE:
            raise Conflict("Only Available listings can be withdrawn.")
        self.set_status(asset, AssetStatus.IN_USE, user, "Listing withdrawn",
                        f"Withdrawn from the marketplace by {user.name}")
        asset.published_at = None
        self.audit.log(user, "asset_withdrawn", "asset", asset.asset_code)
        self.db.commit()
        return asset


def spec_from_request(req: ResourceRequest) -> MatchSpec:
    return MatchSpec(category=req.category, purpose=req.purpose, specifications=req.specifications or "",
                     quantity=req.quantity, preferred_condition=req.preferred_condition, urgency=req.urgency,
                     delivery_campus=req.delivery_campus, delivery_building=req.delivery_building,
                     required_date=req.required_date, requester_department_id=req.requester_department_id)
