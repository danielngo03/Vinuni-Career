"""Analytics event contract (B-548): the properties allowlist gate is pure."""

from __future__ import annotations

from app.modules.analytics.domain import taxonomy


def test_sanitize_properties_keeps_safe_scalars() -> None:
    clean = taxonomy.sanitize_properties({"job_id": "abc-123", "count": 3, "featured": True})
    assert clean == {"job_id": "abc-123", "count": 3, "featured": True}


def test_sanitize_properties_drops_forbidden_keys() -> None:
    clean = taxonomy.sanitize_properties(
        {"email": "student@example.com", "name": "Jane Doe", "job_id": "abc"}
    )
    assert clean == {"job_id": "abc"}


def test_sanitize_properties_drops_email_shaped_strings() -> None:
    clean = taxonomy.sanitize_properties({"contact": "someone@vinuni.edu.vn"})
    assert clean == {}


def test_sanitize_properties_drops_long_free_text() -> None:
    clean = taxonomy.sanitize_properties({"note": "x" * 200})
    assert clean == {}


def test_sanitize_properties_caps_dict_size() -> None:
    raw = {f"key_{i}": i for i in range(30)}
    clean = taxonomy.sanitize_properties(raw)
    assert len(clean) <= 20


def test_sanitize_properties_non_dict_input_is_empty() -> None:
    assert taxonomy.sanitize_properties(None) == {}
    assert taxonomy.sanitize_properties("not-a-dict") == {}  # type: ignore[arg-type]
