"""Structuring adapters: deterministic (default) + optional LLM-on-text.

The deterministic adapter reuses ``cv_structuring`` to group extracted text into
sections + contact and emit field-level ``review_fields`` — no AI, fully offline
(``docs/CV_INGESTION_EXTRACTION_SPEC.md`` §3.6).

The LLM structuring adapter is a TEXT-ONLY fallback that is DISABLED by default
and gated on ``cv_llm_structuring_enabled`` + a provider alias. It receives ONLY
extracted/redacted text — never raw PDF/image bytes (``docs/SECURITY_PRIVACY.md``
AI Safety). Tests inject a fake provider via :func:`set_llm_structuring_adapter`.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

import httpx

from app.ai.extraction import cv_structuring
from app.ai.extraction.adapters.base import redact_secrets
from app.ai.gateway import runtime_config
from app.ai.gateway.factory import _get_api_key, real_provider_active
from app.ai.gateway.output_guard import scrub_text
from app.core.config import get_settings

_JSON_OBJECT_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_MAX_TEXT_CHARS = 18_000

_SYSTEM_PROMPT = """You structure CV/resume text into clean JSON for a career platform.
Rules:
- Use only facts present in the provided CV text.
- Never invent employers, schools, dates, awards, skills, or contact data.
- Normalize noisy PDF/OCR text into concise fields that can be matched against job descriptions.
- Preserve language where possible; detected_language must be "vi" or "en".
- Return ONLY a JSON object with keys: extracted_data, review_fields, detected_language.
- extracted_data.contact may contain name, email, phone, location, links.
- For sections use {"items":[{"text":"..."}]} objects.
- Supported sections include summary, education, experience, projects, skills,
  certifications, awards, languages, activities.
- review_fields is a short list of only uncertain or missing fields, each {path,value,needs_review}.
"""


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = _JSON_OBJECT_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _clean_item_text(value: object, *, limit: int = 1200) -> str:
    text = value if isinstance(value, str) else str(value or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()[:limit]


def _merge_refinement(base_result: dict, candidate: dict) -> dict | None:
    """Accept only the public CV shape and merge with deterministic fallback."""

    base_extracted = base_result.get("extracted_data")
    extracted: dict = dict(base_extracted) if isinstance(base_extracted, dict) else {}
    candidate_extracted = candidate.get("extracted_data")
    if not isinstance(candidate_extracted, dict):
        return None

    contact = candidate_extracted.get("contact")
    if isinstance(contact, dict):
        safe_contact = {
            key: _clean_item_text(contact.get(key), limit=300)
            for key in ("name", "email", "phone", "location", "links")
            if contact.get(key)
        }
        if safe_contact:
            extracted["contact"] = {**extracted.get("contact", {}), **safe_contact}

    for section_type in cv_structuring._HEADER_MAP.values():  # noqa: SLF001
        section = candidate_extracted.get(section_type)
        if not isinstance(section, dict):
            continue
        items = section.get("items")
        if not isinstance(items, list):
            continue
        safe_items: list[dict[str, str]] = []
        for item in items[:40]:
            if isinstance(item, dict):
                text = _clean_item_text(item.get("text"))
            else:
                text = _clean_item_text(item)
            if text:
                safe_items.append({"text": text})
        if safe_items:
            extracted[section_type] = {"items": safe_items}

    review_fields: list[dict] = []
    raw_review = candidate.get("review_fields")
    if isinstance(raw_review, list):
        for row in raw_review[:20]:
            if not isinstance(row, dict):
                continue
            path = _clean_item_text(row.get("path"), limit=120)
            if not path:
                continue
            review_fields.append(
                {
                    "path": path,
                    "value": _clean_item_text(row.get("value")),
                    "needs_review": bool(row.get("needs_review", True)),
                }
            )

    detected = candidate.get("detected_language")
    if detected not in {"vi", "en"}:
        detected = base_result.get("detected_language") or "en"

    return {
        "extracted_data": extracted,
        "review_fields": review_fields or base_result.get("review_fields", []),
        "detected_language": detected,
    }


class StructuringAdapter:
    """Deterministic, non-AI structuring of extracted text into review fields."""

    engine_family = "structuring_deterministic"
    engine_version = "v1"

    def structure(self, text: str) -> dict:
        return cv_structuring.structure_cv_text(text)


@runtime_checkable
class LlmStructuringEngine(Protocol):
    """An LLM structuring engine operating on extracted TEXT ONLY."""

    @property
    def available(self) -> bool: ...

    def refine(self, text: str, base_result: dict) -> dict | None: ...


class DisabledLlmStructuringAdapter:
    """Default adapter: LLM structuring is off; deterministic result is final."""

    engine_family = "structuring_llm"
    engine_version = "disabled"

    @property
    def available(self) -> bool:
        return False

    def refine(self, text: str, base_result: dict) -> dict | None:
        return None


class GatewayLlmStructuringAdapter:
    """Production LLM-on-text structuring through the configured AI gateway route.

    This adapter is synchronous because the ingestion cascade is synchronous and
    can run inside the lightweight local queue. It mirrors the OpenAI-compatible
    gateway contract without exposing provider/model details to callers.
    """

    engine_family = "structuring_llm_gateway"
    engine_version = "v1"

    @property
    def available(self) -> bool:
        cfg = runtime_config.current()
        alias = self._alias(cfg)
        route = cfg.provider_routes.get(alias)
        if not real_provider_active() or route is None:
            return False
        provider_name = route[0]
        if provider_name in {"ollama-local", "ollama"}:
            return True
        return bool(_get_api_key(provider_name))

    def _alias(self, cfg: runtime_config.EffectiveAiConfig) -> str:
        configured = get_settings().cv_llm_structuring_provider_alias
        return configured if configured in cfg.provider_routes else cfg.chat_model_alias

    def refine(self, text: str, base_result: dict) -> dict | None:
        cfg = runtime_config.current()
        alias = self._alias(cfg)
        route = cfg.provider_routes.get(alias)
        if route is None:
            return None

        provider_name, base_url, model_id = route
        api_key = _get_api_key(provider_name)
        if not api_key and provider_name not in {"ollama-local", "ollama"}:
            return None

        user_payload = {
            "cv_text": text[:_MAX_TEXT_CHARS],
            "deterministic_parse": base_result,
        }
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "temperature": 0.0,
            "max_tokens": 1800,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://career.vinuni.edu.vn",
            "X-Title": "VinUni Career Platform",
        }
        try:
            with httpx.Client(timeout=25.0) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError):
            return None

        choice = (data.get("choices") or [{}])[0]
        raw = (choice.get("message") or {}).get("content", "")
        parsed = _extract_json(scrub_text(raw))
        if parsed is None:
            return None
        return _merge_refinement(base_result, parsed)


_llm_adapter: LlmStructuringEngine | None = None


def get_llm_structuring_adapter() -> LlmStructuringEngine:
    global _llm_adapter
    if _llm_adapter is None:
        _llm_adapter = DisabledLlmStructuringAdapter()
    return _llm_adapter


def set_llm_structuring_adapter(adapter: LlmStructuringEngine | None) -> None:
    """Override the LLM structuring adapter (test seam / ai-engineer wiring)."""

    global _llm_adapter
    _llm_adapter = adapter


def run_llm_structuring(text: str, base_result: dict) -> dict | None:
    """Run the LLM structuring adapter on TEXT ONLY, with secret redaction.

    Hard guard: the input MUST be a ``str`` (extracted text/markdown). Passing
    bytes is a programming error and raises — raw document bytes never reach an
    LLM.
    """

    if not isinstance(text, str):
        raise TypeError("LLM structuring receives extracted text only, never raw bytes")
    # Defense in depth: even with an adapter wired, the resolved runtime flag is
    # the gate (ADR-0011 §2 — the admin/resolver-published snapshot decides
    # whether LLM-on-text structuring runs).
    if not runtime_config.current().cv_llm_structuring_enabled:
        return None
    adapter = get_llm_structuring_adapter()
    if not adapter.available:
        return None
    return adapter.refine(redact_secrets(text), base_result)


__all__ = [
    "StructuringAdapter",
    "LlmStructuringEngine",
    "DisabledLlmStructuringAdapter",
    "GatewayLlmStructuringAdapter",
    "get_llm_structuring_adapter",
    "set_llm_structuring_adapter",
    "run_llm_structuring",
]
