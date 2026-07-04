"""Unit tests for documents primitives: signed tokens, structuring, PDF render."""

from __future__ import annotations

import pytest
from app.ai.extraction.cv_structuring import structure_cv_text
from app.modules.documents.infrastructure import pdf_render, storage


def test_signed_token_round_trip() -> None:
    token = storage.make_signed_token({"kind": "export", "id": "abc", "uid": "u1"})
    payload = storage.verify_signed_token(token)
    assert payload["kind"] == "export" and payload["id"] == "abc"


def test_signed_token_expired() -> None:
    token = storage.make_signed_token({"kind": "export", "id": "abc"}, ttl_seconds=-1)
    with pytest.raises(storage.SignedTokenError):
        storage.verify_signed_token(token)


def test_signed_token_tampered() -> None:
    token = storage.make_signed_token({"kind": "export", "id": "abc"})
    bad = token[:-2] + "zz"
    with pytest.raises(storage.SignedTokenError):
        storage.verify_signed_token(bad)


def test_token_carries_no_storage_path() -> None:
    # The token payload references a resource id, never a storage key/path.
    token = storage.make_signed_token({"kind": "export", "id": "abc", "uid": "u1"})
    payload = storage.verify_signed_token(token)
    assert "storage_key" not in payload and "storage_path" not in payload


def test_structure_cv_text_groups_sections_and_contact() -> None:
    text = (
        "Jane Doe\n"
        "Email: jane@example.com | Phone: +84 900 000 000\n"
        "Education\nVinUni BSc CS 2022-2026\n"
        "Experience\n- Built APIs\n"
        "Skills\nPython, FastAPI\n"
    )
    out = structure_cv_text(text)
    assert out["extracted_data"]["contact"]["email"] == "jane@example.com"
    assert "education" in out["extracted_data"]
    assert any(f["path"].startswith("experience") for f in out["review_fields"])
    assert out["detected_language"] == "en"


def test_render_cv_pdf_outputs_pdf_bytes() -> None:
    snapshot = {
        "title": "My CV",
        "sections": [
            {"title": "Skills", "is_visible": True,
             "content_json": {"items": [{"text": "Python"}]}},
        ],
    }
    out = pdf_render.render_cv_pdf(snapshot, watermark=None)
    assert out[:4] == b"%PDF"
    watermarked = pdf_render.render_cv_pdf(snapshot, watermark="Partner")
    assert watermarked[:4] == b"%PDF"
