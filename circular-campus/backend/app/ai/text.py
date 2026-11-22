"""Small text tools for the local fallback: tokenising, synonyms and TF-IDF cosine.

This is the same approach as the Phase 2 smoke test (TF-IDF cosine standing in
for embeddings), with a synonym table so that, for example, "notebook" and
"laptop" or "seat" and "chair" count as the same word.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOPWORDS = frozenset("""
a an the and or of for to in on at by with from into is are be been was were it its this that these those
we our us i my me you your need needs needed want looking require required requires please some any per
can could would should will about as up out new use used using one two three four five six seven eight
nine ten very good also more less than only just each other them they their for has have had not no do
""".split())

# Canonical form for common synonyms (left side → right side).
SYNONYMS = {
    "notebook": "laptop", "notebooks": "laptop", "laptops": "laptop", "ultrabook": "laptop",
    "macbook": "laptop", "thinkpad": "laptop", "chromebook": "laptop",
    "seat": "chair", "seats": "chair", "seating": "chair", "chairs": "chair", "stool": "chair", "stools": "chair",
    "screen": "monitor", "screens": "monitor", "display": "monitor", "displays": "monitor", "monitors": "monitor",
    "pc": "desktop", "computer": "desktop", "computers": "desktop", "workstation": "desktop",
    "beamer": "projector", "projectors": "projector",
    "table": "desk", "tables": "desk", "desks": "desk", "workbench": "desk",
    "cupboard": "cabinet", "locker": "cabinet", "lockers": "cabinet", "cabinets": "cabinet",
    "bookcase": "shelf", "shelves": "shelf", "shelving": "shelf",
    "scope": "oscilloscope", "oscilloscopes": "oscilloscope",
    "textbook": "book", "textbooks": "book", "books": "book",
    "lab": "laboratory", "labs": "laboratory",
    "classroom": "teaching", "lecture": "teaching", "class": "teaching", "training": "teaching",
    "printers": "printer", "laserjet": "printer",
    "speakers": "speaker", "mic": "microphone", "microphones": "microphone",
    "whiteboards": "whiteboard", "fridge": "refrigerator",
    "ergonomics": "ergonomic", "adjustable": "ergonomic",
}

_TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")


def normalise(token: str) -> str:
    t = SYNONYMS.get(token, token)
    if len(t) > 4 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        t = SYNONYMS.get(t[:-1], t[:-1])
    return t


def tokenize(text: str) -> list[str]:
    tokens = []
    for raw in _TOKEN.findall((text or "").lower()):
        if raw in STOPWORDS or len(raw) < 2:
            continue
        tokens.append(normalise(raw))
    return tokens


class TfidfSimilarity:
    """Cosine similarity between one query and a list of documents, with IDF from that list."""

    def __init__(self, documents: list[str]):
        self.doc_tokens = [tokenize(d) for d in documents]
        n = max(1, len(self.doc_tokens))
        df: Counter = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        self.idf = {t: math.log((1 + n) / (1 + c)) + 1.0 for t, c in df.items()}
        self.doc_vecs = [self._vec(t) for t in self.doc_tokens]

    def _vec(self, tokens: list[str]) -> dict[str, float]:
        tf = Counter(tokens)
        vec = {t: (1 + math.log(c)) * self.idf.get(t, 1.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def scores(self, query: str) -> list[tuple[float, list[str]]]:
        q = self._vec(tokenize(query))
        results = []
        for vec in self.doc_vecs:
            shared = [t for t in q if t in vec]
            sim = sum(q[t] * vec[t] for t in shared)
            shared.sort(key=lambda t: -(q[t] * vec[t]))
            results.append((min(1.0, sim), shared))
        return results


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)
