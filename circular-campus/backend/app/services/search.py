"""Classic search and filtering (C3, UC-5, FR-SRC-1..5).

Structured filters run in SQL. Keyword search looks in name, tags and
description, uses the same synonym table as the matcher (so "notebook" finds
laptops), requires every keyword to match, and ranks name hits above tag hits
above description hits. It is deterministic and needs no AI service.
"""
from __future__ import annotations

from typing import Optional

from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..ai.text import tokenize
from ..domain.enums import CONDITION_RANK, AssetStatus, Condition
from ..models import Asset, User
from ..security.permissions import PermissionPolicy as P
from ..timeutil import today


@dataclass
class SearchFilters:
    q: Optional[str] = None
    scope: str = "marketplace"            # marketplace | inventory
    category: Optional[str] = None
    condition: Optional[Condition] = None    # minimum condition
    department_id: Optional[int] = None
    campus: Optional[str] = None
    building: Optional[str] = None
    status: Optional[AssetStatus] = None
    min_quantity: Optional[int] = None
    max_age_years: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    sort: str = "relevance"               # relevance | newest | condition | nearest | name


class AssetSearchService:
    def __init__(self, db: Session):
        self.db = db

    def search(self, user: User, f: SearchFilters) -> list[tuple[Asset, float]]:
        stmt = select(Asset)
        if f.scope == "inventory":
            if not P.can_see_inventory_of_all(user):
                stmt = stmt.where(Asset.department_id == user.department_id)
            if f.status:
                stmt = stmt.where(Asset.status == f.status)
        else:
            stmt = stmt.where(Asset.status == AssetStatus.AVAILABLE)
            stmt = stmt.where(or_(Asset.available_until.is_(None), Asset.available_until >= today()))
        if f.category:
            stmt = stmt.where(Asset.category == f.category)
        if f.department_id:
            stmt = stmt.where(Asset.department_id == f.department_id)
        if f.campus:
            stmt = stmt.where(Asset.campus == f.campus)
        if f.building:
            stmt = stmt.where(Asset.building == f.building)
        if f.min_quantity:
            stmt = stmt.where(Asset.quantity >= f.min_quantity)
        if f.condition:
            ok = [c for c, r in CONDITION_RANK.items() if r >= CONDITION_RANK[f.condition]]
            stmt = stmt.where(Asset.condition.in_(ok))
        if f.max_age_years is not None:
            cutoff = today()
            try:
                cutoff = date(cutoff.year - int(f.max_age_years), cutoff.month, min(cutoff.day, 28))
            except ValueError:
                pass
            stmt = stmt.where(Asset.purchase_date.is_not(None), Asset.purchase_date >= cutoff)
        if P.can_see_value(user):  # FR-SRC-5: value filters only for roles that may see value
            if f.min_value is not None:
                stmt = stmt.where(Asset.estimated_value >= f.min_value)
            if f.max_value is not None:
                stmt = stmt.where(Asset.estimated_value <= f.max_value)

        assets = self.db.scalars(stmt).all()
        results = self._keyword(assets, f.q) if f.q and f.q.strip() else [(a, 0.0) for a in assets]
        return self._sort(results, f.sort, user)

    @staticmethod
    def _keyword(assets, q: str) -> list[tuple[Asset, float]]:
        terms = list(dict.fromkeys(tokenize(q)))
        raw_terms = [t for t in q.lower().split() if t]
        if not terms:
            return [(a, 0.0) for a in assets]
        out = []
        for a in assets:
            name_t = set(tokenize(a.name)) | set(tokenize(a.subcategory or "")) | set(tokenize(a.category))
            tag_t = set(tokenize(" ".join(a.tags or [])))
            desc_t = set(tokenize(a.description or ""))
            score, matched_all = 0.0, True
            for t in terms:
                if t in name_t:
                    score += 3
                elif t in tag_t:
                    score += 2
                elif t in desc_t:
                    score += 1
                else:
                    matched_all = False
                    break
            if not matched_all:  # fall back to plain substring on the code (e.g. "AST-0003")
                if any(r.upper() == a.asset_code for r in raw_terms):
                    out.append((a, 5.0))
                continue
            out.append((a, score))
        return out

    @staticmethod
    def _sort(results, sort: str, user: User):
        if sort == "newest":
            key = lambda r: -(r[0].published_at or r[0].created_at).timestamp()  # noqa: E731
        elif sort == "condition":
            key = lambda r: (-CONDITION_RANK[r[0].condition], r[0].name.lower())  # noqa: E731
        elif sort == "nearest":
            campus, building = user.department.campus, user.department.building
            key = lambda r: (0 if (r[0].campus == campus and r[0].building == building)  # noqa: E731
                             else 1 if r[0].campus == campus else 2, r[0].name.lower())
        elif sort == "name":
            key = lambda r: r[0].name.lower()  # noqa: E731
        else:
            key = lambda r: (-r[1], -(r[0].published_at or r[0].created_at).timestamp())  # noqa: E731
        return sorted(results, key=key)
