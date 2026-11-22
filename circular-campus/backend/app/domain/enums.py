"""Domain vocabulary taken from the Phase 3 requirements document."""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """Actors from Phase 3 §2.2 that Phase 6 implements."""

    ADMIN = "admin"                        # System Administrator
    DEPT_REP = "dept_rep"                  # Department Representative (approver)
    CUSTODIAN = "custodian"                # Asset Custodian
    REQUESTER = "requester"                # Requester
    SUSTAINABILITY = "sustainability"      # Sustainability Officer (view-only in Phase 6)

    @property
    def label(self) -> str:
        return ROLE_LABELS[self]


ROLE_LABELS = {
    Role.ADMIN: "System Administrator",
    Role.DEPT_REP: "Department Representative",
    Role.CUSTODIAN: "Asset Custodian",
    Role.REQUESTER: "Requester",
    Role.SUSTAINABILITY: "Sustainability Officer",
}


class AssetStatus(str, Enum):
    REGISTERED = "Registered"
    IN_USE = "In Use"
    AVAILABLE = "Available"
    RESERVED = "Reserved"
    IN_TRANSFER = "In Transfer"
    UNDER_MAINTENANCE = "Under Maintenance"
    PENDING_DISPOSITION = "Pending Disposition"
    DONATED = "Donated"
    RECYCLED = "Recycled"
    DISPOSED = "Disposed"


class Condition(str, Enum):
    NEW = "New"
    GOOD = "Good"
    FAIR = "Fair"
    POOR = "Poor"
    NOT_WORKING = "Not working"

    @property
    def rank(self) -> int:
        return CONDITION_RANK[self]


CONDITION_RANK = {
    Condition.NOT_WORKING: 0,
    Condition.POOR: 1,
    Condition.FAIR: 2,
    Condition.GOOD: 3,
    Condition.NEW: 4,
}


class Urgency(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RequestStatus(str, Enum):
    OPEN = "Open"                  # UC-6 alt 3a: need saved without a selected asset
    SUBMITTED = "Submitted"
    UNDER_REVIEW = "Under Review"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    FULFILLED = "Fulfilled"
    CANCELLED = "Cancelled"
    EXPIRED = "Expired"


class TransferStatus(str, Enum):
    SCHEDULED = "Scheduled"
    DISPATCHED = "Dispatched"
    RECEIVED = "Received"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"
    DISPUTED = "Disputed"


class TransferMethod(str, Enum):
    COLLECTION = "Collection"
    DELIVERY = "Delivery"


FINAL_ASSET_STATES = {AssetStatus.DONATED, AssetStatus.RECYCLED, AssetStatus.DISPOSED}
