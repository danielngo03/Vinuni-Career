"""
app/ai — AI subsystem.

Subpackages:
  gateway/     LLM provider chain, circuit breaker, model routing
  agents/      Multi-agent workforces (admin review, student, partner)
  ingestion/   Document ingestion gatekeeper
  extraction/  Structured CV/JD extraction, OCR/vision
  retrieval/   Chunking, hybrid search, cross-encoder rerank
  matching/    Skill normalization, candidate matching, scoring
  moderation/  Content safety and compliance checks
  safety/      PII detection, prompt injection guard, output validation
  evaluation/  Metrics, golden datasets, regression gates
  decisioning/ Agent decision orchestration logic

Import hierarchy (no circular deps):
  gateway ← extraction, retrieval, matching, moderation, safety
  agents ← gateway + all above (via application commands only)
"""
from __future__ import annotations
