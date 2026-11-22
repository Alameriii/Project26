"""Campus locations used for sample data, forms and the matcher's location factor.

Sample values for the prototype; the administrator would maintain the real list (FR-ACC-5).
"""
from __future__ import annotations

LOCATIONS: dict[str, list[str]] = {
    "Main Campus": [
        "Engineering Building",
        "Science Building",
        "Library & Learning Commons",
        "Administration Building",
        "Student Centre",
    ],
    "SAN Campus": [
        "Research Complex",
        "Innovation Hub",
    ],
}


def valid_location(campus: str, building: str) -> bool:
    return campus in LOCATIONS and building in LOCATIONS[campus]
