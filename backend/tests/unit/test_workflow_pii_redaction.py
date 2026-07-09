"""Nested PII redaction tests for the workflow engine.

Workflow node logs and dry-run sample events must never persist raw PII. The
redactor must mask identifier-looking keys wherever they appear — not only at
the top level — so a candidate object nested under the trigger payload, or PII
inside a list, is masked too. Non-PII fields (ids, scores, statuses) must pass
through since conditions need them.
"""

from __future__ import annotations

from app.modules.workflow.application.execution_service import (
    _redact,
    _summarize,
    redact_sample_event,
)

_REDACTED = "[redacted]"


def test_top_level_pii_is_masked() -> None:
    out = _redact({"email": "a@b.com", "phone": "0900", "status": "active"})
    assert out["email"] == _REDACTED
    assert out["phone"] == _REDACTED
    assert out["status"] == "active"


def test_nested_pii_under_candidate_object_is_masked() -> None:
    out = _redact(
        {
            "candidate": {
                "full_name": "Nguyen Van A",
                "email": "a@b.com",
                "fit_score": 82,
            },
            "job_id": "job-123",
        }
    )
    assert out["candidate"]["full_name"] == _REDACTED
    assert out["candidate"]["email"] == _REDACTED
    # Non-PII inner + outer fields survive for realistic condition evaluation.
    assert out["candidate"]["fit_score"] == 82
    assert out["job_id"] == "job-123"


def test_pii_inside_list_of_objects_is_masked() -> None:
    out = _redact(
        {
            "applicants": [
                {"applicant_name": "A", "score": 1},
                {"applicant_name": "B", "cover_letter": "long text"},
            ]
        }
    )
    assert out["applicants"][0]["applicant_name"] == _REDACTED
    assert out["applicants"][0]["score"] == 1
    assert out["applicants"][1]["applicant_name"] == _REDACTED
    assert out["applicants"][1]["cover_letter"] == _REDACTED


def test_substring_keys_are_caught() -> None:
    # Keys like candidate_email / student_phone_number / applicant_passport_number
    # are matched by substring, not only exact name.
    out = _redact(
        {
            "candidate_email": "a@b.com",
            "student_phone_number": "0900",
            "applicant_passport_number": "X123",
            "company_name_display": "OK to keep",
        }
    )
    assert out["candidate_email"] == _REDACTED
    assert out["student_phone_number"] == _REDACTED
    assert out["applicant_passport_number"] == _REDACTED


def test_recursion_is_depth_bounded() -> None:
    # A deeply nested payload must be trimmed, never blow the stack.
    node: dict = {"leaf": "x"}
    for _ in range(30):
        node = {"child": node}
    out = _redact(node)
    # Walk down until we hit the trim sentinel — it must appear.
    seen_trim = False
    cur: object = out
    for _ in range(40):
        if cur == "[trimmed]":
            seen_trim = True
            break
        if isinstance(cur, dict) and "child" in cur:
            cur = cur["child"]
        else:
            break
    assert seen_trim


def test_redact_sample_event_always_returns_dict() -> None:
    assert redact_sample_event({"email": "a@b.com"}) == {"email": _REDACTED}


def test_summarize_masks_trigger_payload() -> None:
    out = _summarize({"trigger": {"candidate": {"email": "a@b.com"}}, "n": 1})
    assert out["trigger"]["candidate"]["email"] == _REDACTED
    assert out["n"] == 1
