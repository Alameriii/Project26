"""AI feature 1 — asset classification and tagging (UC-3, FR-AI-1/2/3/12).

Suggests category, subcategory, up to 8 tags, material, a standard description,
a likely condition and missing details. The suggestion is advice only: nothing
is saved until the user accepts or edits it on the registration form.

Providers:
  * GeminiClassifier — used when GEMINI_API_KEY is set on the server.
  * RuleBasedClassifier — local keyword rules; used when no key is set, or when
    Gemini fails, times out or returns something invalid (FR-AI-9 style fallback).
"""
from __future__ import annotations

from typing import Optional

import json
import re
from dataclasses import asdict, dataclass, field

from .gemini import AIServiceUnavailable, GeminiClient
from .taxonomy import KNOWN_BRANDS, MATERIAL_WORDS, TAXONOMY, find_subcategory, taxonomy_as_dict

LOCAL_CLASSIFIER_VERSION = "local-rules-classifier v1.0"
LOW_CONFIDENCE = 0.6  # FR-AI-12


@dataclass
class ClassificationResult:
    category: str
    subcategory: str
    tags: list[str]
    material: str
    standard_description: str
    suggested_condition: Optional[str]
    missing_information: list[str]
    confidence: float
    reason: str
    provider: str = "local-fallback"
    model_version: str = LOCAL_CLASSIFIER_VERSION
    extras: dict = field(default_factory=dict)

    @property
    def low_confidence(self) -> bool:
        return self.confidence < LOW_CONFIDENCE

    def to_dict(self) -> dict:
        d = asdict(self)
        d["low_confidence"] = self.low_confidence
        return d


# --------------------------------------------------------------------------- helpers

def _has_phrase(text: str, phrase: str) -> bool:
    """Whole-word match that also accepts simple plurals ('monitor' matches 'monitors')."""
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?:s|es)?(?![a-z0-9])", text) is not None


def extract_specs(text: str) -> dict:
    """Pull simple, explainable facts out of free text."""
    low = text.lower()
    specs: dict = {}
    for brand in sorted(KNOWN_BRANDS, key=len, reverse=True):
        if _has_phrase(low, brand.lower()):
            specs["brand"] = brand
            break
    if m := re.search(r"(\d{2}(?:\.\d)?)\s*(?:-\s*|\s)?(?:inch(?:es)?|in\b|\")", low):
        specs["screen_size"] = f"{m.group(1)}-inch"
    if m := re.search(r"(\d{1,3})\s*gb\s*(?:of\s*)?(?:ram|memory|ddr\d?)", low):
        specs["ram"] = f"{m.group(1)}GB RAM"
    if m := re.search(r"(\d{3,4}|\d(?:\.\d)?)\s*(gb|tb)\s*(ssd|hdd|nvme|storage)", low):
        specs["storage"] = f"{m.group(1)}{m.group(2).upper()} {m.group(3).upper() if m.group(3) != 'storage' else ''}".strip()
    if m := re.search(r"(core\s*i[3579](?:-\d{4,5}[a-z]*)?|ryzen\s*\d(?:\s*\d{4}[a-z]*)?|xeon|apple\s*m[1-4]|\bm[1-4]\s*(?:pro|max)?\b)", low):
        specs["processor"] = m.group(1).replace("  ", " ").title().replace("I5", "i5").replace("I7", "i7").replace("I3", "i3").replace("I9", "i9")
    if m := re.search(r"(\d{3,5})\s*(?:ansi\s*)?lumens", low):
        specs["brightness"] = f"{m.group(1)} lumens"
    if m := re.search(r"(\d+(?:\.\d+)?)\s*(?:x|×|by)\s*(\d+(?:\.\d+)?)(?:\s*(?:x|×|by)\s*(\d+(?:\.\d+)?))?\s*(cm|mm|m)\b", low):
        specs["dimensions"] = m.group(0)
    if m := re.search(r"\b(\d{1,3})\s*(?:mhz|ghz)\b", low):
        specs["frequency"] = m.group(0)
    # Model numbers look like "P2422H", "E2420", "LaserJet M404" (letters + digits).
    if m := re.search(r"\b([A-Za-z]{1,4}(?:-[A-Za-z]{0,3})?\d{2,5}[A-Za-z]{0,3})\b", text):
        token = m.group(1)
        if not re.fullmatch(r"\d+(gb|tb|mhz|ghz|cm|mm)|x\d+", token.lower()) and not token.lower().startswith(("i3", "i5", "i7", "i9")):
            specs["model"] = token
    if re.search(r"calibrat", low):
        specs["calibration"] = True
    if re.search(r"\bedition\b|\b\d+(st|nd|rd|th)\s+ed\b", low):
        specs["edition"] = True
    if re.search(r"\b(black|white|grey|gray|blue|red|green|beige|brown|silver)\b", low):
        specs["colour"] = re.search(r"\b(black|white|grey|gray|blue|red|green|beige|brown|silver)\b", low).group(1)
    materials = [label for word, label in MATERIAL_WORDS.items() if _has_phrase(low, word)]
    if materials:
        specs["materials"] = sorted(set(materials))
    return specs


CONDITION_HINTS = (
    ("Not working", ("not working", "broken", "dead", "faulty", "does not turn on", "doesn't turn on",
                     "won't turn on", "no power", "fails to boot")),
    ("Poor", ("cracked", "damaged", "missing parts", "heavily worn", "torn", "needs repair", "bulb broken",
              "wobbly", "loose")),
    ("Fair", ("worn", "faded", "stained", "scuffed", "dent", "dented", "some wear", "old")),
    ("New", ("brand new", "unopened", "sealed", "unused", "never used", "in box")),
    ("Good", ("small scratch", "minor scratch", "scratch", "light wear", "minor wear", "good condition",
              "works well", "working", "lightly used", "excellent")),
)


def suggest_condition(text: str) -> tuple[Optional[str], Optional[str]]:
    """The longest matching phrase wins, so 'bulb broken' (Poor) beats 'broken' (Not working)."""
    low = text.lower()
    found = [(len(p), cond, p) for cond, phrases in CONDITION_HINTS for p in phrases if _has_phrase(low, p)]
    if not found:
        return None, None
    _, cond, phrase = max(found)
    return cond, phrase


DETAIL_PROMPTS = {
    "brand": ("brand", "Add the brand or manufacturer."),
    "model": ("model", "Add the model number."),
    "processor": ("processor", "Add the processor (e.g. Core i5)."),
    "ram": ("ram", "Add the amount of RAM."),
    "storage": ("storage", "Add the storage size (e.g. 512GB SSD)."),
    "screen size": ("screen_size", "Add the screen size in inches."),
    "dimensions": ("dimensions", "Add the dimensions (e.g. 120 x 60 cm)."),
    "material": ("materials", "Add the main material (wood, steel, fabric…)."),
    "colour": ("colour", "Add the colour."),
    "calibration date": ("calibration", "Add the last calibration date."),
    "title": ("__title__", "Add the full title."),
    "edition": ("edition", "Add the edition."),
    "safety notes": ("__safety__", "Add any safety notes or hazards."),
    "expiry date": ("__expiry__", "Add the expiry date."),
    "contents list": ("__contents__", "List what the kit contains."),
    "quantity per pack": ("__pack__", "Add how many items are in each pack."),
}


def missing_details(expected: tuple[str, ...], specs: dict, text: str) -> list[str]:
    low = text.lower()
    prompts = []
    for detail in expected:
        key, prompt = DETAIL_PROMPTS.get(detail, (detail, f"Add the {detail}."))
        if key == "__safety__" and re.search(r"safety|hazard|ppe", low):
            continue
        if key == "__expiry__" and re.search(r"expir", low):
            continue
        if key == "__contents__" and re.search(r"includes|contains|contents", low):
            continue
        if key == "__title__" and len(low.split()) > 4:
            continue
        if key == "__pack__" and re.search(r"pack of|per pack|\bbox of", low):
            continue
        if not key.startswith("__") and key in specs:
            continue
        prompts.append(prompt)
    return prompts


# --------------------------------------------------------------------------- providers

class RuleBasedClassifier:
    """Local keyword classifier. Transparent and deterministic; used as the fallback."""

    provider = "local-fallback"
    version = LOCAL_CLASSIFIER_VERSION

    def classify(self, name: str, description: str, specifications: str = "") -> ClassificationResult:
        name_l = (name or "").lower()
        body_l = f"{description or ''} {specifications or ''}".lower()
        full_text = f"{name} {description} {specifications}"

        scored = []
        for cat in TAXONOMY:
            for sub in cat.subcategories:
                score, hits_name, hits_body = 0.0, [], []
                for kw in sub.keywords:
                    if _has_phrase(name_l, kw):
                        score += 3.0 + 0.2 * len(kw.split())
                        hits_name.append(kw)
                    elif _has_phrase(body_l, kw):
                        score += 1.0
                        hits_body.append(kw)
                if score:
                    scored.append((score, cat.name, sub, hits_name, hits_body))
        scored.sort(key=lambda x: -x[0])

        specs = extract_specs(full_text)
        cond, cond_phrase = suggest_condition(full_text)

        if not scored:
            sub = TAXONOMY[-1].subcategories[0]
            return ClassificationResult(
                category="Other", subcategory=sub.name,
                tags=self._tags(specs, sub.name, []),
                material=", ".join(specs.get("materials", [])) or "Unknown",
                standard_description=self._standard_description(name, sub.name, specs, cond, cond_phrase),
                suggested_condition=cond, confidence=0.3,
                missing_information=["Describe what the item is and what it is used for."]
                + missing_details(("brand", "model"), specs, full_text),
                reason="No known keywords were found, so the item was placed in 'Other'. Please pick a category.",
            )

        top_score, cat_name, sub, hits_name, hits_body = scored[0]
        runner_up = next((s for s in scored[1:] if s[2].name != sub.name), None)
        second = runner_up[0] if runner_up else 0.0
        margin = (top_score - second) / top_score
        confidence = 0.5 + 0.33 * margin + min(0.12, 0.04 * top_score)
        if not hits_name:  # only the description mentioned it: weaker evidence
            confidence = min(confidence, 0.5 + 0.05 * len(hits_body), 0.72)
        confidence = round(max(0.3, min(0.95, confidence)), 2)

        hits = hits_name + hits_body
        reason = f"Matched '{', '.join(hits[:3])}' in the {'name' if hits_name else 'description'}"
        if runner_up and second:
            reason += f"; also considered {runner_up[2].name} ({runner_up[1]})"
        reason += "."

        materials = specs.get("materials")
        material = ", ".join(materials) if materials else f"{sub.material} (typical)"
        return ClassificationResult(
            category=cat_name, subcategory=sub.name,
            tags=self._tags(specs, sub.name.split(" / ")[0], hits),
            material=material,
            standard_description=self._standard_description(name, sub.name, specs, cond, cond_phrase),
            suggested_condition=cond, confidence=confidence,
            missing_information=missing_details(sub.expected_details, specs, full_text),
            reason=reason,
        )

    @staticmethod
    def _tags(specs: dict, sub_name: str, hits: list[str]) -> list[str]:
        tags: list[str] = [sub_name.lower()]
        if "brand" in specs:
            tags.append(specs["brand"].lower())
        for key in ("screen_size", "ram", "storage", "processor", "brightness"):
            if key in specs:
                tags.append(str(specs[key]).lower())
        for h in hits:
            if not any(h.lower() in t or t in h.lower() for t in tags):
                tags.append(h.lower())
        for m in specs.get("materials", []):
            tags.append(m.lower())
        seen, out = set(), []
        for t in tags:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out[:8]

    @staticmethod
    def _standard_description(name: str, sub_name: str, specs: dict, cond: Optional[str], cond_phrase: Optional[str]) -> str:
        brand = specs.get("brand")
        label = sub_name.split(" / ")[0].lower()
        materials = specs.get("materials") or []
        if brand:
            head = f"{brand} {label}"
        elif len(materials) == 1:
            head = f"{materials[0]} {label}"
        else:
            head = label
        if specs.get("model"):
            head += f", model {specs['model']}"
        details = [specs[k] for k in ("processor", "ram", "storage", "screen_size", "brightness", "dimensions") if k in specs]
        sentence = head + (f" ({', '.join(details)})" if details else "") + "."
        if cond:
            note = f" Reported condition: {cond}"
            if cond_phrase and cond_phrase not in ("good condition", "working", "works well"):
                note += f" ({cond_phrase})"
            sentence += note + "."
        return sentence[0].upper() + sentence[1:]


class GeminiClassifier:
    provider = "gemini"

    def __init__(self, client: GeminiClient):
        self.client = client
        self.version = f"gemini:{client.model}"

    def classify(self, name: str, description: str, specifications: str = "") -> ClassificationResult:
        prompt = (
            "You classify university campus assets. Use ONLY this category list (JSON):\n"
            f"{json.dumps(taxonomy_as_dict())}\n"
            "Condition must be one of: New, Good, Fair, Poor, Not working, or null if unclear.\n"
            "Return JSON with keys: category, subcategory, tags (max 8 short lowercase strings), material, "
            "standard_description (one or two plain sentences, no marketing), suggested_condition, "
            "missing_information (list of short prompts for details a buyer would need), "
            "confidence (0 to 1), reason (one sentence).\n"
            f"Asset name: {name}\nDescription: {description}\nSpecifications: {specifications}"
        )
        data = self.client.generate_json(prompt)
        sub = find_subcategory(data.get("category"), data.get("subcategory"))
        if sub is None:
            raise AIServiceUnavailable("AI service suggested a category outside the standard list.")
        try:
            confidence = float(data.get("confidence", 0))
        except (TypeError, ValueError) as exc:
            raise AIServiceUnavailable("AI service returned an invalid confidence value.") from exc
        cond = data.get("suggested_condition")
        if cond not in ("New", "Good", "Fair", "Poor", "Not working"):
            cond = None
        return ClassificationResult(
            category=data["category"], subcategory=sub.name,
            tags=[str(t).lower()[:30] for t in (data.get("tags") or [])][:8],
            material=str(data.get("material") or sub.material)[:80],
            standard_description=str(data.get("standard_description") or "")[:500],
            suggested_condition=cond,
            missing_information=[str(x)[:120] for x in (data.get("missing_information") or [])][:6],
            confidence=round(max(0.0, min(1.0, confidence)), 2),
            reason=str(data.get("reason") or "")[:300],
            provider=self.provider, model_version=self.version,
        )


class ClassificationService:
    """Chooses the provider and applies the fallback rule."""

    def __init__(self, client: Optional[GeminiClient] = None):
        self.client = client or GeminiClient()
        self.local = RuleBasedClassifier()

    def classify(self, name: str, description: str, specifications: str = "") -> tuple[ClassificationResult, Optional[str]]:
        """Returns (result, fallback_reason). fallback_reason is None when the AI service answered."""
        if self.client.configured:
            try:
                return GeminiClassifier(self.client).classify(name, description, specifications), None
            except AIServiceUnavailable as exc:
                return self.local.classify(name, description, specifications), str(exc)
        return self.local.classify(name, description, specifications), "No AI service key is configured on the server."
