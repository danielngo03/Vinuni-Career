"""Deterministic role-family + token derivation for organic ranking (pure).

Used by the ranker for two deterministic signals:

- ``role_family_of(title)`` — a coarse role family from a job title, for the
  ``popular_roles`` real aggregate and the similar-jobs ``role-family overlap``.
  A title that matches no known family is ``None`` (it is simply excluded from the
  aggregate — never bucketed into a fabricated catch-all).
- ``tokens_of(title, skills)`` — the normalized token set used for similar-jobs
  skill/title overlap and search-term matching.

No I/O, no model calls — same inputs always yield the same output, so rankings are
reproducible and explainable. The family keyword map is intentionally small and
honest; extending it is a config follow-up, not a correctness risk.
"""

from __future__ import annotations

import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")

# Short, common English stopwords + recruiting filler that add no ranking signal.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "you",
        "our",
        "are",
        "job",
        "role",
        "team",
        "we",
        "to",
        "of",
        "in",
        "at",
        "on",
        "a",
        "an",
        "is",
        "be",
        "as",
        "or",
        "intern",
        "internship",
        "senior",
        "junior",
        "lead",
        "staff",
        "remote",
        "onsite",
        "hybrid",
        "fulltime",
        "parttime",
        "vietnam",
        "hanoi",
    }
)

# Role family -> substring keywords (normalized, matched against the title token
# stream). Order matters only for the first-match winner; families are disjoint
# enough in practice.
_ROLE_FAMILIES: dict[str, tuple[str, ...]] = {
    "software_engineering": (
        "software",
        "developer",
        "engineer",
        "backend",
        "frontend",
        "fullstack",
        "devops",
        "mobile",
        "android",
        "ios",
        "programmer",
    ),
    "data_ai": (
        "data",
        "analyst",
        "analytics",
        "scientist",
        "machine",
        "learning",
        "ai",
        "ml",
        "bi",
    ),
    "product": ("product", "scrum", "agile"),
    "design": ("design", "designer", "ux", "ui", "graphic"),
    "marketing": ("marketing", "seo", "content", "brand", "social", "growth"),
    "sales_bizdev": ("sales", "business", "account", "partnership", "revenue"),
    "finance": ("finance", "financial", "accountant", "accounting", "audit", "tax"),
    "operations": ("operations", "logistics", "supply", "procurement"),
    "hr_people": ("recruiter", "talent", "human", "people", "hr"),
    "customer": ("customer", "support", "success", "service"),
}


def normalize(text: str | None) -> str:
    """Lowercase + non-alphanumeric -> single spaces (accent-insensitive enough)."""

    if not text:
        return ""
    return _NON_ALNUM.sub(" ", text.lower()).strip()


def _words(text: str | None) -> list[str]:
    return [w for w in normalize(text).split() if w]


def role_family_of(title: str | None) -> str | None:
    """Coarse role family for ``title``; ``None`` if it matches no known family."""

    words = set(_words(title))
    if not words:
        return None
    for family, keywords in _ROLE_FAMILIES.items():
        if any(kw in words for kw in keywords):
            return family
    return None


def tokens_of(title: str | None, skills: list[str] | None) -> set[str]:
    """Normalized, stopword-filtered token set for title + skills overlap."""

    tokens: set[str] = set()
    for w in _words(title):
        if len(w) >= 3 and w not in _STOPWORDS:
            tokens.add(w)
    for skill in skills or []:
        for w in _words(skill):
            if len(w) >= 2 and w not in _STOPWORDS:
                tokens.add(w)
    return tokens


def term_matches(term: str, haystack_tokens: set[str], haystack_text: str) -> bool:
    """Whether a (possibly multi-word) search ``term`` matches a candidate."""

    norm = normalize(term)
    if not norm:
        return False
    if " " in norm:
        return norm in haystack_text  # multi-word phrase -> substring
    return norm in haystack_tokens or norm in haystack_text
