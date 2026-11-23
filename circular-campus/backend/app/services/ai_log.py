"""Recording AI suggestions and the user's final decision (FR-AUD-4, FR-AI-18)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..errors import NotFound, PermissionDenied
from ..models import AIRecommendationLog, User
from ..timeutil import now
from .audit import _jsonable


class AILogService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, user: User, feature: str, provider: str, model_version: str, input_summary: str,
               output: dict, confidence: Optional[float], fallback_reason: Optional[str]) -> AIRecommendationLog:
        log = AIRecommendationLog(feature=feature, provider=provider, model_version=model_version,
                                  input_summary=input_summary[:1000], output=_jsonable(output),
                                  confidence=confidence, fallback_reason=fallback_reason,
                                  requested_by_id=user.id)
        self.db.add(log)
        self.db.flush()
        return log

    def get_own(self, log_id: Optional[int], user: User, feature: str) -> Optional[AIRecommendationLog]:
        if not log_id:
            return None
        log = self.db.get(AIRecommendationLog, log_id)
        if log is None or log.feature != feature:
            raise NotFound("AI suggestion record not found.")
        if log.requested_by_id != user.id:
            raise PermissionDenied("This AI suggestion belongs to another user.")
        return log

    def decide(self, log: Optional[AIRecommendationLog], user: User, decision: str, detail: Optional[dict] = None) -> None:
        if log is None:
            return
        log.decision = decision
        log.decision_detail = _jsonable(detail or {})
        log.decided_by_id = user.id
        log.decided_at = now()
