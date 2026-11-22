"""ORM models, following the Phase 4–5 ER design.

Core entities: Department, User, Asset, ResourceRequest, MatchRecommendation,
Transfer. Supporting records: HistoryEvent (life-cycle history, FR-AUD-1/2),
AuditLog (append-only, FR-AUD-3), AIRecommendationLog (FR-AUD-4),
Notification (FR-NOT-1) and UserSession (login sessions).
"""
from __future__ import annotations

from typing import Optional

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .domain.enums import (
    AssetStatus,
    Condition,
    RequestStatus,
    Role,
    TransferMethod,
    TransferStatus,
    Urgency,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _enum(cls):
    return SAEnum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e],
                  validate_strings=True)


TS = DateTime(timezone=True)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    campus: Mapped[str] = mapped_column(String(60))
    building: Mapped[str] = mapped_column(String(60))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    roles_csv: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    department: Mapped[Department] = relationship()

    @property
    def roles(self) -> set[Role]:
        return {Role(r) for r in self.roles_csv.split(",") if r}

    @roles.setter
    def roles(self, value) -> None:
        self.roles_csv = ",".join(sorted({Role(r).value for r in value}))

    def has(self, *roles: Role) -> bool:
        return bool(self.roles & set(roles))


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship()


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    material: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    campus: Mapped[str] = mapped_column(String(60))
    building: Mapped[str] = mapped_column(String(60))
    room: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    purchase_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    estimated_value: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    condition: Mapped[Condition] = mapped_column(_enum(Condition))
    status: Mapped[AssetStatus] = mapped_column(_enum(AssetStatus), index=True)
    availability_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    available_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    reserved_by_request_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("resource_requests.id", use_alter=True, name="fk_asset_reserved_request"), nullable=True)
    parent_asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id"), nullable=True)
    ai_log_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_logs.id"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    department: Mapped[Department] = relationship(foreign_keys=[department_id])
    custodian: Mapped[User] = relationship(foreign_keys=[custodian_id])

    @property
    def location_label(self) -> str:
        parts = [self.campus, self.building] + ([self.room] if self.room else [])
        return ", ".join(parts)


class ResourceRequest(Base):
    __tablename__ = "resource_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requester_department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(Text)
    specifications: Mapped[str] = mapped_column(Text, default="")
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    preferred_condition: Mapped[Condition] = mapped_column(_enum(Condition))
    urgency: Mapped[Urgency] = mapped_column(_enum(Urgency))
    delivery_campus: Mapped[str] = mapped_column(String(60))
    delivery_building: Mapped[str] = mapped_column(String(60))
    delivery_room: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    required_date: Mapped[date] = mapped_column(Date)
    status: Mapped[RequestStatus] = mapped_column(_enum(RequestStatus), index=True)
    queued: Mapped[bool] = mapped_column(Boolean, default=False)   # FR-REQ-3
    reserved_until: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    match_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_log_id: Mapped[Optional[int]] = mapped_column(ForeignKey("ai_logs.id"), nullable=True)
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    requester: Mapped[User] = relationship(foreign_keys=[requester_id])
    requester_department: Mapped[Department] = relationship(foreign_keys=[requester_department_id])
    asset: Mapped[Optional[Asset]] = relationship(foreign_keys=[asset_id])
    decided_by: Mapped[Optional[User]] = relationship(foreign_keys=[decided_by_id])


class MatchRecommendation(Base):
    """Resolves the many-to-many request–asset 'matches' link (Phase 4–5 ER)."""

    __tablename__ = "match_recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("resource_requests.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    explanation: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(80))
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)

    asset: Mapped[Asset] = relationship()


class Transfer(Base):
    __tablename__ = "transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    transfer_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("resource_requests.id"), unique=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    from_department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    to_department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    from_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    receiving_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    to_campus: Mapped[str] = mapped_column(String(60))
    to_building: Mapped[str] = mapped_column(String(60))
    to_room: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    method: Mapped[TransferMethod] = mapped_column(_enum(TransferMethod))
    scheduled_date: Mapped[date] = mapped_column(Date)
    status: Mapped[TransferStatus] = mapped_column(_enum(TransferStatus), index=True)
    approved_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    dispatched_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    handover_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    condition_on_arrival: Mapped[Optional[Condition]] = mapped_column(_enum(Condition), nullable=True)
    avoided_purchase: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)   # FR-SUS-1
    closing_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(TS, default=utcnow, onupdate=utcnow)

    request: Mapped[ResourceRequest] = relationship()
    asset: Mapped[Asset] = relationship()
    from_department: Mapped[Department] = relationship(foreign_keys=[from_department_id])
    to_department: Mapped[Department] = relationship(foreign_keys=[to_department_id])
    from_custodian: Mapped[User] = relationship(foreign_keys=[from_custodian_id])
    receiving_custodian: Mapped[User] = relationship(foreign_keys=[receiving_custodian_id])
    approved_by: Mapped[User] = relationship(foreign_keys=[approved_by_id])
    dispatched_by: Mapped[Optional[User]] = relationship(foreign_keys=[dispatched_by_id])
    received_by: Mapped[Optional[User]] = relationship(foreign_keys=[received_by_id])


class HistoryEvent(Base):
    """Life-cycle history for assets, requests and transfers. Never edited (FR-AUD-3)."""

    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)   # asset | request | transfer
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(60))
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)

    user: Mapped[Optional[User]] = relationship()


class AuditLog(Base):
    """Append-only audit trail (FR-AUD-1/3/5). The API exposes no update or delete."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    entity_ref: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)

    user: Mapped[Optional[User]] = relationship()


class AIRecommendationLog(Base):
    """Every AI suggestion with model, input summary, output, confidence and decision (FR-AUD-4)."""

    __tablename__ = "ai_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(String(20))            # classification | matching
    provider: Mapped[str] = mapped_column(String(30))           # gemini | local-fallback
    model_version: Mapped[str] = mapped_column(String(80))
    input_summary: Mapped[str] = mapped_column(Text)
    output: Mapped[dict] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[str] = mapped_column(String(20), default="pending")
    decision_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(TS, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    link: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(TS, default=utcnow, index=True)
