from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass(frozen=True)
class NormalizedSkill:
    canonical: str
    raw: str
    score: float


class SkillNormalizer:
    def __init__(
        self,
        canonical_skills: list[str],
        *,
        aliases: dict[str, str] | None = None,
        threshold: float = 0.85,
    ) -> None:
        self.canonical_skills = sorted({_normalize_token(skill) for skill in canonical_skills})
        self.aliases = {_normalize_token(key): value for key, value in (aliases or {}).items()}
        self.threshold = threshold

    def normalize_one(self, raw: str) -> NormalizedSkill | None:
        token = _normalize_token(raw)
        if not token:
            return None
        if token in self.aliases:
            canonical = self.aliases[token]
            return NormalizedSkill(canonical=canonical, raw=raw, score=1.0)
        if token in self.canonical_skills:
            return NormalizedSkill(canonical=token, raw=raw, score=1.0)
        best = max(
            (
                (skill, SequenceMatcher(None, token, skill).ratio())
                for skill in self.canonical_skills
            ),
            key=lambda item: item[1],
            default=("", 0.0),
        )
        if best[1] < self.threshold:
            return None
        return NormalizedSkill(canonical=best[0], raw=raw, score=round(best[1], 4))

    def normalize_many(self, raw_skills: list[str]) -> list[NormalizedSkill]:
        by_canonical: dict[str, NormalizedSkill] = {}
        for raw in raw_skills:
            normalized = self.normalize_one(raw)
            if normalized and normalized.score >= by_canonical.get(
                normalized.canonical,
                NormalizedSkill(normalized.canonical, raw, 0.0),
            ).score:
                by_canonical[normalized.canonical] = normalized
        return sorted(by_canonical.values(), key=lambda item: item.canonical)


DEFAULT_SKILLS = [
    "python",
    "fastapi",
    "django",
    "sql",
    "postgresql",
    "mysql",
    "redis",
    "kafka",
    "docker",
    "kubernetes",
    "react",
    "typescript",
    "javascript",
    "node",
    "java",
    "go",
    "machine learning",
    "nlp",
    "rag",
    "llm",
    "pytorch",
    "tensorflow",
    "data analysis",
    "elasticsearch",
    "qdrant",
    "milvus",
]

DEFAULT_ALIASES = {
    "nodejs": "node",
    "node.js": "node",
    "reactjs": "react",
    "react.js": "react",
    "postgres": "postgresql",
    "postgre sql": "postgresql",
    "js": "javascript",
    "ts": "typescript",
    "k8s": "kubernetes",
    "large language model": "llm",
    "retrieval augmented generation": "rag",
}


def normalize_skills(raw_skills: list[str]) -> list[str]:
    normalizer = SkillNormalizer(DEFAULT_SKILLS, aliases=DEFAULT_ALIASES)
    return [item.canonical for item in normalizer.normalize_many(raw_skills)]


def _normalize_token(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower().replace("_", " ")).strip()
