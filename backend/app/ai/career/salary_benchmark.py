"""Internal curated salary benchmark (VND million / month) — the single source.

Approximate Vietnam market ranges for 2024-2025. INTERNAL and static: never
AI-generated, never fetched from an external provider at request time. Shared by
the AI-assistant ``get_salary_benchmark`` tool and the offer-negotiation guidance
helper so both ground on the SAME numbers (no external data, no fabrication).

The lookup is fuzzy on the role string (substring / whole-word overlap) so
"Senior Backend Software Engineer" resolves to the ``software engineer`` band.
Returns ``None`` when the role is not in the benchmark — callers must degrade to a
"not in benchmark" state rather than invent a range.
"""

from __future__ import annotations

# role key -> {tiers: [{years, min, max}], currency}
SALARY_DB: dict[str, dict] = {
    "software engineer": {
        "tiers": [
            {"years": "0–1", "min": 12, "max": 20},
            {"years": "1–3", "min": 20, "max": 40},
            {"years": "3–6", "min": 35, "max": 70},
            {"years": "6+", "min": 60, "max": 120},
        ],
        "currency": "triệu VND/tháng",
    },
    "data scientist": {
        "tiers": [
            {"years": "0–1", "min": 15, "max": 25},
            {"years": "1–3", "min": 25, "max": 50},
            {"years": "3–6", "min": 45, "max": 80},
            {"years": "6+", "min": 70, "max": 140},
        ],
        "currency": "triệu VND/tháng",
    },
    "product manager": {
        "tiers": [
            {"years": "0–2", "min": 18, "max": 30},
            {"years": "2–5", "min": 30, "max": 65},
            {"years": "5+", "min": 60, "max": 150},
        ],
        "currency": "triệu VND/tháng",
    },
    "marketing manager": {
        "tiers": [
            {"years": "0–2", "min": 10, "max": 18},
            {"years": "2–5", "min": 18, "max": 40},
            {"years": "5+", "min": 35, "max": 80},
        ],
        "currency": "triệu VND/tháng",
    },
    "finance analyst": {
        "tiers": [
            {"years": "0–2", "min": 12, "max": 22},
            {"years": "2–5", "min": 22, "max": 50},
            {"years": "5+", "min": 45, "max": 100},
        ],
        "currency": "triệu VND/tháng",
    },
    "ui ux designer": {
        "tiers": [
            {"years": "0–1", "min": 10, "max": 18},
            {"years": "1–3", "min": 18, "max": 35},
            {"years": "3+", "min": 30, "max": 70},
        ],
        "currency": "triệu VND/tháng",
    },
    "devops engineer": {
        "tiers": [
            {"years": "0–2", "min": 18, "max": 30},
            {"years": "2–5", "min": 30, "max": 60},
            {"years": "5+", "min": 55, "max": 110},
        ],
        "currency": "triệu VND/tháng",
    },
}


def _normalize(role: str) -> str:
    return role.lower().replace("-", " ").replace("_", " ").strip()


def lookup(role: str) -> tuple[str, dict] | None:
    """Return ``(matched_key, benchmark)`` for *role*, or ``None`` if not found.

    Fuzzy match: the benchmark key is a substring of the role, the role is a
    substring of the key, or any whole word of the key appears in the role.
    Deterministic (dict iteration order is insertion order).
    """

    if not role:
        return None
    role_lower = _normalize(role)
    for key, val in SALARY_DB.items():
        if (
            key in role_lower
            or role_lower in key
            or any(word in role_lower for word in key.split())
        ):
            return key, val
    return None
