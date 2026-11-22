"""AI feature 2 — resource matching and ranking (UC-7, FR-AI-4..9, NFR-24).

1. Hard rules remove ineligible assets first (FR-AI-5): not Available, not
   enough quantity, worse than the requested minimum condition, the
   requester's own department, or a listing that has already ended.
2. Each remaining asset gets a 0–1 compatibility score from six factors:

       relevance    = 0.70 × semantic + 0.30 × category
       practicality = 0.30 × condition + 0.30 × location + 0.20 × timing + 0.20 × repair
       score        = relevance × (0.6 + 0.4 × practicality)

       semantic   meaning of the request vs the asset text
       category   same standard category (1), not given (0.5), different (0)
       condition  better condition scores higher
       location   same building / campus — a proxy for transfer cost;
                  another campus counts against it more when urgency is High
       timing     listing still open on the required date
       repair     likely repair cost, from condition

   Relevance gates the score, so a nearby item in good condition cannot rank
   highly if it is not what was asked for. Scores below 0.40 are not shown.

   With Gemini configured, "semantic" is a hybrid: half Gemini embedding
   similarity, half the local keyword/synonym score. Embeddings alone can be
   pulled by incidental words (a request for "seating for a study room" sits
   close to "study tables"); the keyword half knows that seating means chairs.
   Without Gemini, or when it fails or takes more than 10 s, only the local
   TF-IDF keyword score is used, and the response says so (FR-AI-9).
3. Ties on score are broken in favour of more waste diverted (FR-AI-8).
4. The top 5 are returned, each with a score, a confidence and a reason that
   names its 2–3 main factors (FR-AI-7).

Matching never reserves, approves or transfers anything; it only ranks.
"""
from __future__ import annotations

from typing import Optional

import hashlib
from dataclasses import dataclass, field
from datetime import date

from ..domain.enums import CONDITION_RANK, AssetStatus, Condition, Urgency
from .gemini import AIServiceUnavailable, GeminiClient
from .taxonomy import find_subcategory, typical_weight
from .text import TfidfSimilarity, cosine, tokenize

LOCAL_MATCHER_VERSION = "local-tfidf-rules-matcher v1.1"
EMBEDDING_SHARE = 0.5  # share of the semantic factor taken from Gemini embeddings in hybrid mode
RELEVANCE_WEIGHTS = {"semantic": 0.70, "category": 0.30}
PRACTICAL_WEIGHTS = {"condition": 0.30, "location": 0.30, "timing": 0.20, "repair": 0.20}
# Share of the final score each factor can move; used only to order the explanation.
EXPLAIN_WEIGHTS = {"semantic": 0.42, "category": 0.18, "condition": 0.12, "location": 0.12, "timing": 0.08,
                   "repair": 0.08}
MIN_SCORE = 0.40
CONDITION_SCORE = {4: 1.0, 3: 0.9, 2: 0.7, 1: 0.45, 0: 0.1}
REPAIR_SCORE = {4: 1.0, 3: 1.0, 2: 0.75, 1: 0.4, 0: 0.1}
NOTIFY_THRESHOLD = 0.75  # FR-NOT-3


@dataclass
class MatchSpec:
    category: Optional[str]
    purpose: str
    specifications: str
    quantity: int
    preferred_condition: Condition
    urgency: Urgency
    delivery_campus: str
    delivery_building: str
    required_date: date
    requester_department_id: int

    @property
    def text(self) -> str:
        return f"{self.purpose}. {self.specifications}"

    def summary(self) -> str:
        return (f"category={self.category}; qty={self.quantity}; min condition={self.preferred_condition.value}; "
                f"urgency={self.urgency.value}; to={self.delivery_campus}/{self.delivery_building}; "
                f"by={self.required_date.isoformat()}; need='{(self.purpose + ' ' + self.specifications)[:160]}'")


@dataclass
class MatchResult:
    asset_id: int
    score: float
    confidence: float
    reason: str
    factors: dict
    waste_kg: float
    rank: int = 0

    @property
    def low_confidence(self) -> bool:
        return self.confidence < 0.6

    def to_dict(self) -> dict:
        return {"asset_id": self.asset_id, "rank": self.rank, "score": self.score,
                "score_percent": round(self.score * 100), "confidence": self.confidence,
                "low_confidence": self.low_confidence, "reason": self.reason,
                "factors": self.factors, "waste_kg_estimate": round(self.waste_kg, 1)}


@dataclass
class MatchOutcome:
    results: list[MatchResult]
    provider: str
    model_version: str
    fallback_reason: Optional[str]
    considered: int
    excluded: dict = field(default_factory=dict)

    @property
    def notice(self) -> Optional[str]:
        if self.provider == "gemini":
            return None
        if self.fallback_reason and "No AI service key" not in self.fallback_reason:
            return f"AI ranking is unavailable ({self.fallback_reason}) Showing rule-based keyword ranking instead."
        return "No AI service is configured, so these results use the local rule-based keyword ranking."


def _asset_text(asset) -> str:
    tags = " ".join(asset.tags or [])
    return f"{asset.name}. {asset.subcategory or ''}. {asset.description or ''}. {tags}"


class HardRuleFilter:
    """FR-AI-5: rule-based checks stay in charge of eligibility."""

    @staticmethod
    def check(asset, spec: MatchSpec, today: date) -> Optional[str]:
        if asset.status != AssetStatus.AVAILABLE:
            return "not available"
        if asset.department_id == spec.requester_department_id:
            return "your own department"
        if asset.quantity < spec.quantity:
            return "quantity too low"
        if CONDITION_RANK[asset.condition] < CONDITION_RANK[spec.preferred_condition]:
            return "condition below minimum"
        if asset.available_until and asset.available_until < today:
            return "listing ended"
        return None


class _EmbeddingCache:
    _store: dict[str, list[float]] = {}

    @classmethod
    def embed(cls, client: GeminiClient, texts: list[str]) -> list[list[float]]:
        keys = [hashlib.sha256(f"{client.embedding_model}|{t}".encode()).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in cls._store]
        if missing:
            vectors = client.embed([t for _, t in missing])
            for (k, _), v in zip(missing, vectors):
                cls._store[k] = v
        return [cls._store[k] for k in keys]


class MatchingEngine:
    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()

    # -- semantic similarity providers ---------------------------------------------
    def _semantic_gemini(self, spec: MatchSpec, assets) -> list[tuple[float, list[str]]]:
        vectors = _EmbeddingCache.embed(self.client, [spec.text] + [_asset_text(a) for a in assets])
        q, docs = vectors[0], vectors[1:]
        out = []
        for v in docs:
            sim = cosine(q, v)
            out.append((max(0.0, min(1.0, (sim - 0.45) / 0.4)), []))
        return out

    @staticmethod
    def _semantic_local(spec: MatchSpec, assets) -> list[tuple[float, list[str]]]:
        tfidf = TfidfSimilarity([_asset_text(a) for a in assets])
        raw = tfidf.scores(spec.text)
        req_tokens = set(tokenize(spec.text))
        out = []
        for asset, (sim, shared) in zip(assets, raw):
            sub = find_subcategory(asset.category, asset.subcategory)
            sub_hit = 0.0
            if sub:
                kw_tokens = {t for kw in sub.keywords for t in tokenize(kw)}
                if kw_tokens & req_tokens:
                    sub_hit = 1.0
            out.append((min(1.0, 0.6 * min(1.0, sim * 1.8) + 0.4 * sub_hit), shared))
        return out

    # -- scoring --------------------------------------------------------------------
    @staticmethod
    def _location(asset, spec: MatchSpec) -> tuple[float, str]:
        same_campus = asset.campus.strip().lower() == spec.delivery_campus.strip().lower()
        same_building = same_campus and asset.building.strip().lower() == spec.delivery_building.strip().lower()
        high = spec.urgency == Urgency.HIGH
        if same_building:
            return 1.0, "same building"
        if same_campus:
            return (0.65 if high else 0.75), "same campus"
        return (0.2 if high else 0.35), "on another campus"

    def _score(self, asset, spec: MatchSpec, sem: float, shared: list[str], provider: str) -> MatchResult:
        rank = CONDITION_RANK[asset.condition]
        category = 1.0 if spec.category and asset.category == spec.category else (0.5 if not spec.category else 0.0)
        location, loc_phrase = self._location(asset, spec)
        timing = 1.0 if (asset.available_until is None or asset.available_until >= spec.required_date) else 0.4
        factors = {
            "semantic": round(sem, 2),
            "category": category,
            "condition": CONDITION_SCORE[rank],
            "location": location,
            "timing": timing,
            "repair": REPAIR_SCORE[rank],
        }
        relevance = sum(w * factors[k] for k, w in RELEVANCE_WEIGHTS.items())
        practicality = sum(w * factors[k] for k, w in PRACTICAL_WEIGHTS.items())
        score = round(relevance * (0.6 + 0.4 * practicality), 3)
        factors["relevance"] = round(relevance, 2)
        factors["practicality"] = round(practicality, 2)

        if provider == "gemini":
            confidence = 0.55 + 0.4 * sem
            sem_phrase = (f"close in meaning to your request (\u201c{', '.join(shared[:2])}\u201d)" if shared
                          else "close in meaning to your request")
        else:
            confidence = 0.45 + 0.35 * sem + 0.15 * category
            sem_phrase = f"description matches “{', '.join(shared[:2])}”" if shared else "similar description"

        strengths = {
            "semantic": sem_phrase,
            "category": f"same category ({asset.category})",
            "condition": f"{asset.condition.value} condition",
            "location": loc_phrase,
            "timing": "available by your required date",
            "repair": "no repair expected",
        }
        weaknesses = {
            "semantic": "weak description match",
            "category": "different category",
            "location": loc_phrase,
            "timing": "listing ends before your required date",
            "repair": "may need repair",
        }
        ranked = sorted(EXPLAIN_WEIGHTS, key=lambda k: -(EXPLAIN_WEIGHTS[k] * factors[k]))
        main = [strengths[k] for k in ranked if factors[k] >= 0.7][:3]
        if not main:
            main = [strengths[ranked[0]]]
        weak = [weaknesses[k] for k in ("category", "semantic", "location", "timing", "repair")
                if k in weaknesses and factors[k] < 0.5]
        reason = ", ".join(main)
        reason = reason[0].upper() + reason[1:]
        if weak:
            reason += f"; but {weak[0]}"
        reason += "."
        waste = typical_weight(asset.category, asset.subcategory) * spec.quantity
        return MatchResult(asset_id=asset.id, score=score, confidence=round(min(0.95, confidence), 2),
                           reason=reason, factors=factors, waste_kg=waste)

    # -- public API -------------------------------------------------------------------
    def match(self, spec: MatchSpec, assets, today: date, top_n: int = 5) -> MatchOutcome:
        excluded: dict[str, int] = {}
        eligible = []
        for a in assets:
            why = HardRuleFilter.check(a, spec, today)
            if why:
                excluded[why] = excluded.get(why, 0) + 1
            else:
                eligible.append(a)

        provider, version, fallback = "local-fallback", LOCAL_MATCHER_VERSION, None
        if not eligible:
            if not self.client.configured:
                fallback = "No AI service key is configured on the server."
            return MatchOutcome([], provider if not self.client.configured else "gemini",
                                version if not self.client.configured else f"gemini:{self.client.embedding_model}",
                                fallback, 0, excluded)

        local = self._semantic_local(spec, eligible)
        sems = None
        if self.client.configured:
            try:
                emb = self._semantic_gemini(spec, eligible)
                sems = [(EMBEDDING_SHARE * e + (1 - EMBEDDING_SHARE) * l, shared)
                        for (e, _), (l, shared) in zip(emb, local)]
                provider = "gemini"
                version = f"gemini:{self.client.embedding_model} + keywords + rules v1.1"
            except AIServiceUnavailable as exc:
                fallback = str(exc)
        else:
            fallback = "No AI service key is configured on the server."
        if sems is None:
            sems = local

        results = [self._score(a, spec, s, shared, provider) for a, (s, shared) in zip(eligible, sems)]
        below = sum(1 for r in results if r.score < MIN_SCORE)
        if below:
            excluded["low relevance"] = below
        results = [r for r in results if r.score >= MIN_SCORE]
        results.sort(key=lambda r: (-round(r.score, 2), -r.waste_kg, r.asset_id))
        for i, r in enumerate(results, 1):
            r.rank = i
        return MatchOutcome(results[:top_n], provider, version, fallback, len(eligible), excluded)
