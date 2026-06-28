from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
from pydantic import ValidationError

from app.ai.extraction.schemas import CVExtraction
from app.shared.config import get_gemini_api_keys, settings


class GeminiCVExtractionError(RuntimeError):
    """Raised when Gemini cannot extract a usable structured CV."""


def extract_cv_from_pdf(content: bytes) -> CVExtraction:
    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise GeminiCVExtractionError("Gemini API key is not configured")

    bodies = _request_bodies(content)
    return _extract_with_bodies(api_keys, bodies, raw_text_quality="vision_extracted")


def extract_cv_from_text(text: str) -> CVExtraction:
    api_keys = get_gemini_api_keys()
    if not api_keys:
        raise GeminiCVExtractionError("Gemini API key is not configured")
    if not text.strip():
        raise GeminiCVExtractionError("CV text is empty")

    bodies = _text_request_bodies(text)
    return _extract_with_bodies(api_keys, bodies, raw_text_quality="native_text")


def _extract_with_bodies(
    api_keys: list[str],
    bodies: list[dict[str, Any]],
    *,
    raw_text_quality: str,
) -> CVExtraction:
    last_error = "Unknown Gemini extraction error"
    for model in _candidate_models():
        for body in bodies:
            for api_key in api_keys:
                try:
                    data = _post_generate_content(api_key, model, body)
                    extraction = _parse_extraction(data)
                    extraction.raw_text_quality = raw_text_quality  # type: ignore[assignment]
                    return extraction
                except GeminiCVExtractionError as exc:
                    last_error = str(exc)
                    continue

    raise GeminiCVExtractionError(last_error)


def _request_bodies(content: bytes) -> list[dict[str, Any]]:
    prompt = _cv_extraction_prompt("vision_extracted")
    base_body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
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
            "responseJsonSchema": CVExtraction.model_json_schema(),
        },
    }
    return [schema_body, base_body]


def _text_request_bodies(text: str) -> list[dict[str, Any]]:
    prompt = f"{_cv_extraction_prompt('native_text')}\n\nSOURCE TEXT:\n{text[:80_000]}"
    base_body: dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
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
            "responseJsonSchema": CVExtraction.model_json_schema(),
        },
    }
    return [schema_body, base_body]


def _cv_extraction_prompt(raw_text_quality: str) -> str:
    return (
        "Extract this student CV/resume into strict JSON matching this shape: "
        '{"document_type":"cv","summary":"","raw_markdown":"","skills":[{"name":"","evidence":"","proficiency":"unknown"}],'
        '"education":[{"institution":"","degree":"","major":"","start_year":null,"end_year":null}],'
        '"experiences":[{"company":"","title":"","summary":"","start_date":null,"end_date":null}],'
        '"projects":[{"name":"","description":"","technologies":[]}],'
        f'"languages":[],"certifications":[],"raw_text_quality":"{raw_text_quality}","confidence":0.0}}. '
        "Set raw_markdown to a clean one-column Markdown CV. Use headings and bullet lists only; "
        "do not create tables, multi-column layouts, HTML, code fences, or decorative separators. "
        "Return only facts visible in the document. "
        "Do not invent dates, companies, degrees, projects, or skills. "
        "Use empty arrays or empty strings when a field is absent."
    )


def cv_extraction_to_text(extraction: CVExtraction) -> str:
    if extraction.raw_markdown.strip():
        return extraction.raw_markdown.strip()

    chunks: list[str] = []
    if extraction.summary:
        chunks.append(f"## Summary\n{extraction.summary}")
    if extraction.skills:
        skill_lines = [f"- {skill.name}" for skill in extraction.skills]
        chunks.append("## Skills\n" + "\n".join(skill_lines))
        evidence = [f"- {skill.evidence}" for skill in extraction.skills if skill.evidence]
        if evidence:
            chunks.append("## Skill Evidence\n" + "\n".join(evidence))
    education = []
    for item in extraction.education:
        education.append(
            "- "
            + " | ".join(
                str(value) for value in [
                    item.institution,
                    item.degree,
                    item.major,
                    item.start_year,
                    item.end_year,
                ] if value
            )
        )
    if education:
        chunks.append("## Education\n" + "\n".join(education))
    experiences = []
    for item in extraction.experiences:
        dates = " - ".join(value for value in [item.start_date or "", item.end_date or ""] if value)
        heading = " | ".join(value for value in [item.title, item.company, dates] if value)
        details = f": {item.summary}" if item.summary else ""
        experiences.append(f"- {heading}{details}")
    if experiences:
        chunks.append("## Experience\n" + "\n".join(experiences))
    projects = []
    for item in extraction.projects:
        tech = ", ".join(item.technologies)
        details = " | ".join(value for value in [item.description, tech] if value)
        projects.append(
            f"- {item.name}: {details}" if item.name and details else f"- {item.name or details}"
        )
    if projects:
        chunks.append("## Projects\n" + "\n".join(projects))
    if extraction.certifications:
        chunks.append("## Certifications\n" + "\n".join(f"- {item}" for item in extraction.certifications))
    if extraction.languages:
        chunks.append("## Languages\n" + "\n".join(f"- {item}" for item in extraction.languages))
    return "\n\n".join(chunk for chunk in chunks if chunk.strip())


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
                raise GeminiCVExtractionError(
                    f"Gemini {model} HTTP {status_code}: {exc.response.text[:500]}"
                ) from exc
            except httpx.HTTPError as exc:
                if attempt < settings.llm_max_retries:
                    continue
                raise GeminiCVExtractionError(f"Gemini {model} request failed: {exc}") from exc

    raise GeminiCVExtractionError(f"Gemini {model} request failed")


def _parse_extraction(data: dict[str, Any]) -> CVExtraction:
    try:
        parts = data["candidates"][0]["content"].get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiCVExtractionError("Unexpected Gemini response shape") from exc
    try:
        return CVExtraction.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise GeminiCVExtractionError("Gemini returned invalid CV JSON") from exc
