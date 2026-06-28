from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.extraction.schemas import JDExtraction
from app.shared.config import get_gemini_api_keys, settings


class GeminiJDExtractionError(RuntimeError):
    """Raised when Gemini cannot extract a usable structured JD."""


def extract_jd_from_text(text: str) -> JDExtraction:
    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise GeminiJDExtractionError("Gemini API key is not configured")
    if not text.strip():
        raise GeminiJDExtractionError("Job description text is empty")

    bodies = _request_bodies(text)
    last_error = "Unknown Gemini JD extraction error"
    for model in _candidate_models():
        for body in bodies:
            for api_key in api_keys:
                try:
                    data = _post_generate_content(api_key, model, body)
                    return _parse_extraction(data)
                except GeminiJDExtractionError as exc:
                    last_error = str(exc)
                    continue

    raise GeminiJDExtractionError(last_error)


def extract_jd_from_pdf(content: bytes) -> JDExtraction:
    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise GeminiJDExtractionError("Gemini API key is not configured")
    if not content:
        raise GeminiJDExtractionError("Job description PDF is empty")

    bodies = _pdf_request_bodies(content)
    last_error = "Unknown Gemini JD extraction error"
    for model in _candidate_models():
        for body in bodies:
            for api_key in api_keys:
                try:
                    data = _post_generate_content(api_key, model, body)
                    return _parse_extraction(data)
                except GeminiJDExtractionError as exc:
                    last_error = str(exc)
                    continue

    raise GeminiJDExtractionError(last_error)


def _request_bodies(text: str) -> list[dict[str, Any]]:
    prompt = (
        f"{_jd_extraction_prompt()}\n\nSOURCE TEXT:\n{text[:80_000]}"
    )
    base_body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    schema_body = {
        **base_body,
        "generationConfig": {
            **base_body["generationConfig"],
            "responseJsonSchema": JDExtraction.model_json_schema(),
        },
    }
    return [schema_body, base_body]


def _pdf_request_bodies(content: bytes) -> list[dict[str, Any]]:
    base_body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _jd_extraction_prompt()},
                    {
                        "inlineData": {
                            "mimeType": "application/pdf",
                            "data": base64.b64encode(content).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    schema_body = {
        **base_body,
        "generationConfig": {
            **base_body["generationConfig"],
            "responseJsonSchema": JDExtraction.model_json_schema(),
        },
    }
    return [schema_body, base_body]


def _jd_extraction_prompt() -> str:
    return (
        "Extract this job description into strict JSON matching this shape: "
        '{"document_type":"job_description","title":"","description":"","location":"","required_skills":[{"name":"","evidence":"","proficiency":"unknown"}],'
        '"nice_to_have_skills":[{"name":"","evidence":"","proficiency":"unknown"}],'
        '"responsibilities":[],"seniority":"unknown","employment_type":"","compliance_flags":[],"confidence":0.0}. '
        "Return only facts visible in the source text. Summarize the role and main scope in description. "
        "Extract the work location, city, country, remote/hybrid/on-site signal, or leave location empty. "
        "Do not invent requirements, seniority, employment type, benefits, or compliance issues. Put must-have skills in required_skills "
        "and optional/preferred skills in nice_to_have_skills. Use empty arrays or empty strings "
        "when a field is absent."
    )


def _candidate_models() -> list[str]:
    seen: set[str] = set()
    models = []
    for model in [settings.gemini_model, settings.vision_extraction_model]:
        normalized = (model or "").strip()
        if normalized and normalized not in seen:
            models.append(normalized)
            seen.add(normalized)
    return models


def _post_generate_content(api_key: str, model: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{settings.gemini_base_url.rstrip('/')}/models/{model}:generateContent"
    with httpx.Client(timeout=settings.llm_timeout_seconds) as client:
        for attempt in range(settings.llm_max_retries + 1):
            try:
                if attempt:
                    time.sleep(settings.llm_retry_backoff_seconds * (2 ** (attempt - 1)))
                response = client.post(
                    url,
                    params={"key": api_key},
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code in {500, 502, 503, 504, 429} and attempt < settings.llm_max_retries:
                    continue
                raise GeminiJDExtractionError(
                    f"Gemini {model} HTTP {status_code}: {exc.response.text[:500]}"
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < settings.llm_max_retries:
                    continue
                raise GeminiJDExtractionError(f"Gemini {model} request failed: {exc}") from exc

    raise GeminiJDExtractionError(f"Gemini {model} request failed")


def _parse_extraction(data: dict[str, Any]) -> JDExtraction:
    try:
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiJDExtractionError("Unexpected Gemini response shape") from exc
    try:
        return JDExtraction.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiJDExtractionError("Gemini returned invalid JD JSON") from exc
