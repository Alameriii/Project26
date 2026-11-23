"""Request bodies with validation (FR-AST-4, UC-6 5b). Errors come back per field."""
from __future__ import annotations

from typing import Optional

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator

from ..ai.taxonomy import find_category, find_subcategory
from ..domain.enums import AssetStatus, Condition, Role, TransferMethod, Urgency
from ..domain.locations import valid_location
from ..timeutil import today


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class _Base(BaseModel):
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}


class LoginIn(_Base):
    email: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=1, max_length=200)


class _AssetFields(_Base):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    category: str
    subcategory: Optional[str] = None
    tags: list[str] = Field(default_factory=list, max_length=8)
    material: Optional[str] = Field(default=None, max_length=80)
    quantity: int = Field(ge=1, le=10000)
    campus: str
    building: str
    room: Optional[str] = Field(default=None, max_length=30)
    purchase_date: Optional[date] = None
    estimated_value: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    condition: Condition

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if not find_category(v):
            raise ValueError("Choose a category from the list.")
        return find_category(v).name

    @field_validator("tags")
    @classmethod
    def _tags(cls, v):
        out = []
        for t in v:
            t = t.strip().lower()
            if not t:
                continue
            if len(t) > 30:
                raise ValueError("Each tag must be 30 characters or fewer.")
            if t not in out:
                out.append(t)
        return out

    @field_validator("purchase_date")
    @classmethod
    def _purchase(cls, v):
        if v and v > today():
            raise ValueError("Purchase date cannot be in the future.")
        return v

    @model_validator(mode="after")
    def _cross(self):
        if self.subcategory:
            sub = find_subcategory(self.category, self.subcategory)
            if not sub:
                raise ValueError(f"'{self.subcategory}' is not a subcategory of {self.category}.")
            self.subcategory = sub.name
        if not valid_location(self.campus, self.building):
            raise ValueError("Choose a campus and a building from the list.")
        return self


class AssetCreate(_AssetFields):
    department_id: Optional[int] = None
    custodian_id: Optional[int] = None
    publish_now: bool = False
    availability_note: Optional[str] = Field(default=None, max_length=500)
    available_until: Optional[date] = None
    ai_log_id: Optional[int] = None
    ai_decision: Optional[str] = Field(default=None, pattern="^(accepted|edited|dismissed)$")

    @field_validator("available_until")
    @classmethod
    def _until(cls, v):
        if v and v < today():
            raise ValueError("The listing end date must be today or later.")
        return v


class AssetUpdate(_AssetFields):
    custodian_id: Optional[int] = None


class StatusChangeIn(_Base):
    to_status: AssetStatus
    note: Optional[str] = Field(default=None, max_length=500)


class PublishIn(_Base):
    availability_note: Optional[str] = Field(default=None, max_length=500)
    available_until: Optional[date] = None

    @field_validator("available_until")
    @classmethod
    def _until(cls, v):
        if v and v < today():
            raise ValueError("The listing end date must be today or later.")
        return v


class ClassifyIn(_Base):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    specifications: str = Field(default="", max_length=1000)


class RequestFields(_Base):
    category: str
    purpose: str = Field(min_length=3, max_length=1000)
    specifications: str = Field(default="", max_length=1000)
    quantity: int = Field(ge=1, le=10000)
    preferred_condition: Condition = Condition.FAIR
    urgency: Urgency = Urgency.MEDIUM
    delivery_campus: str
    delivery_building: str
    delivery_room: Optional[str] = Field(default=None, max_length=30)
    required_date: date

    @field_validator("category")
    @classmethod
    def _category(cls, v):
        if not find_category(v):
            raise ValueError("Choose a category from the list.")
        return find_category(v).name

    @field_validator("required_date")
    @classmethod
    def _date(cls, v):
        if v < today():
            raise ValueError("The required date cannot be in the past.")
        return v

    @model_validator(mode="after")
    def _loc(self):
        if not valid_location(self.delivery_campus, self.delivery_building):
            raise ValueError("Choose a delivery campus and building from the list.")
        return self


class RequestCreate(RequestFields):
    asset_id: Optional[int] = None
    match_log_id: Optional[int] = None
    save_as_open: bool = False

    @model_validator(mode="after")
    def _target(self):
        if self.asset_id is None and not self.save_as_open:
            raise ValueError("Select an asset, or save the request as an open request.")
        return self


class SelectAssetIn(_Base):
    asset_id: int
    match_log_id: Optional[int] = None


class ApproveIn(_Base):
    method: TransferMethod = TransferMethod.DELIVERY
    scheduled_date: date
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("scheduled_date")
    @classmethod
    def _date(cls, v):
        if v < today():
            raise ValueError("The transfer date cannot be in the past.")
        return v


class RejectIn(_Base):
    reason: str = Field(min_length=5, max_length=500)


class DispatchIn(_Base):
    handover_note: Optional[str] = Field(default=None, max_length=500)


class ConfirmIn(_Base):
    condition_on_arrival: Condition
    avoided_purchase: bool
    note: Optional[str] = Field(default=None, max_length=500)


class DisputeIn(_Base):
    note: str = Field(min_length=5, max_length=500)


class CancelIn(_Base):
    reason: Optional[str] = Field(default=None, max_length=500)


class UserCreate(_Base):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=200)
    department_id: int
    roles: list[Role] = Field(min_length=1)


class UserUpdate(_Base):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    department_id: Optional[int] = None
    roles: Optional[list[Role]] = Field(default=None, min_length=1)
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)


class DepartmentCreate(_Base):
    code: str = Field(min_length=2, max_length=12, pattern=r"^[A-Za-z0-9-]+$")
    name: str = Field(min_length=2, max_length=120)
    campus: str
    building: str

    @model_validator(mode="after")
    def _loc(self):
        if not valid_location(self.campus, self.building):
            raise ValueError("Choose a campus and a building from the list.")
        self.code = self.code.upper()
        return self
