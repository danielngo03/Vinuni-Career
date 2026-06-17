from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai_engines.guardrails import detect_prompt_injection
from app.core.config import settings
from app.infra.cache import get_cache
from app.infra.database.models import AIUsageLog
from app.infra.llm_gateway import ChatMessage, ChatRequest, get_llm_gateway
from app.infra.llm_gateway.errors import LLMGatewayError
from app.infra.search import SearchDocument, get_search_client
from app.schemas.ai import MatchResponse

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[\s.-]?\d){8,10}(?!\d)")
LINKEDIN_RE = re.compile(r"\b(?:https?://)?(?:www\.)?linkedin\.com/[^\s,;]+", re.IGNORECASE)

SKILLS = {
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
}

BANNED_JOB_TERMS = {
    "unpaid internship": "Unpaid internship is not allowed without explicit university approval.",
    "no salary": "Compensation must be transparent.",
    "gambling": "Gambling-related jobs require manual compliance review.",
    "adult": "Adult content is outside platform policy.",
    "crypto trading": "High-risk financial roles require manual compliance review.",
}


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def mask_pii(text: str) -> tuple[str, list[dict[str, str]]]:
    entities: list[dict[str, str]] = []

    def replace(pattern: re.Pattern[str], label: str, value: str) -> str:
        nonlocal text
        for match in pattern.finditer(text):
            entities.append({"type": label, "value": match.group(0)})
        return pattern.sub(value, text)

    text = replace(EMAIL_RE, "EMAIL", "[REDACTED_EMAIL]")
    text = replace(PHONE_RE, "PHONE", "[REDACTED_PHONE]")
    text = replace(LINKEDIN_RE, "PROFILE_URL", "[REDACTED_PROFILE_URL]")

    lines = text.splitlines()
    if lines:
        first = lines[0].strip()
        if 2 <= len(first.split()) <= 5 and not any(char.isdigit() for char in first):
            entities.append({"type": "POSSIBLE_NAME", "value": first})
            lines[0] = "[REDACTED_NAME]"
            text = "\n".join(lines)

    return text, entities


def extract_skills(text: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9+#.\s-]", " ", text.lower())
    found = {skill for skill in SKILLS if _contains_skill(normalized, skill)}
    if "node.js" in normalized:
        found.add("node")
    if "postgres" in normalized:
        found.add("postgresql")
    return sorted(found)


def _contains_skill(text: str, skill: str) -> bool:
    pattern = r"(?<![a-z0-9+#.])" + re.escape(skill) + r"(?![a-z0-9+#.])"
    return re.search(pattern, text) is not None


def embed_text(text: str, dimensions: int = 32) -> list[float]:
    try:
        return get_llm_gateway().embed(text).embedding
    except LLMGatewayError:
        pass

    buckets = [0.0] * dimensions
    words = re.findall(r"[a-zA-Z0-9+#.]+", text.lower())
    for word, count in Counter(words).items():
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        bucket = digest[0] % dimensions
        weight = 1.0 + math.log(count)
        buckets[bucket] += weight
    norm = math.sqrt(sum(value * value for value in buckets)) or 1.0
    return [round(value / norm, 6) for value in buckets]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def match_cv_to_job(cv_text: str, job_description: str) -> MatchResponse:
    cache_key = _cache_key("match", cv_text, job_description)
    cache = get_cache()
    cached = cache.get(cache_key)
    if cached:
        return MatchResponse(**json.loads(cached))

    cv_skills = set(extract_skills(cv_text))
    job_skills = set(extract_skills(job_description))
    matched = sorted(cv_skills & job_skills)
    missing = sorted(job_skills - cv_skills)

    skill_score = len(matched) / max(1, len(job_skills))
    semantic_score = cosine_similarity(embed_text(cv_text), embed_text(job_description))
    score = round((0.72 * skill_score + 0.28 * semantic_score) * 100, 2)

    response = MatchResponse(
        score=score,
        matched_skills=matched,
        missing_skills=missing,
        reasoning={
            "skill_score": round(skill_score * 100, 2),
            "semantic_score": round(semantic_score * 100, 2),
            "privacy_note": "PII is excluded from scoring; matching uses skills and content only.",
        },
    )
    cache.set(cache_key, json.dumps(response.model_dump()), settings.cache_default_ttl_seconds)
    return response


def chat_with_gateway(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    request = ChatRequest(
        messages=[
            ChatMessage(role=message["role"], content=message["content"]) for message in messages
        ],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    response = get_llm_gateway().chat(request)
    return {
        "content": response.content,
        "provider": response.provider,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
    }


def embed_with_gateway(text: str, *, model: str | None = None) -> dict[str, Any]:
    response = get_llm_gateway().embed(text, model=model)
    return {
        "embedding": response.embedding,
        "provider": response.provider,
        "model": response.model,
        "input_tokens": response.input_tokens,
    }


def parse_job_requirements(description: str) -> dict[str, Any]:
    skills = extract_skills(description)
    seniority = "intern" if "intern" in description.lower() else "junior"
    if any(term in description.lower() for term in ("senior", "lead", "principal")):
        seniority = "senior"
    return {
        "skills": skills,
        "seniority": seniority,
        "estimated_tokens": estimate_tokens(description),
    }


def evaluate_job_policy(description: str) -> tuple[bool, list[str], dict[str, Any]]:
    lowered = description.lower()
    reasons = [reason for term, reason in BANNED_JOB_TERMS.items() if term in lowered]
    injection_hits = detect_prompt_injection(description)
    if injection_hits:
        reasons.append("Potential prompt-injection content requires manual review.")
    if len(description.strip()) < 80:
        reasons.append("Job description is too short for automatic approval.")
    approved = not reasons
    return (
        approved,
        reasons or ["Passed deterministic policy checks."],
        {"checks": "offline_policy_v1", "prompt_injection_hits": injection_hits},
    )


def log_ai_usage(
    db: Session,
    *,
    org_id: str,
    user_id: str | None,
    feature_name: str,
    input_text: str,
    output_text: str = "",
) -> AIUsageLog:
    input_tokens = estimate_tokens(input_text)
    output_tokens = estimate_tokens(output_text)
    usage = AIUsageLog(
        org_id=org_id,
        user_id=user_id,
        feature_name=feature_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=round((input_tokens + output_tokens) * 0.0000002, 6),
    )
    db.add(usage)
    return usage


def index_document(
    *,
    document_id: str,
    entity_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    get_search_client().index(
        SearchDocument(
            id=document_id,
            entity_type=entity_type,
            title=title,
            body=body,
            metadata=metadata or {},
            embedding=embed_text(body),
        )
    )


def usage_summary(db: Session, org_id: str) -> dict[str, Any]:
    row = db.execute(
        select(
            func.coalesce(func.sum(AIUsageLog.input_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.output_tokens), 0),
            func.coalesce(func.sum(AIUsageLog.cost_usd), 0),
        ).where(AIUsageLog.org_id == org_id)
    ).one()
    return {
        "org_id": org_id,
        "total_input_tokens": int(row[0]),
        "total_output_tokens": int(row[1]),
        "estimated_cost_usd": float(row[2]),
    }


def provider_status() -> dict[str, list[str]]:
    return {
        "chat_chain": settings.llm_provider_chain or [settings.llm_provider],
        "embedding_chain": settings.embedding_provider_chain,
    }


def _cache_key(*parts: str) -> str:
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"ai:{digest}"
