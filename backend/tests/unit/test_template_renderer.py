"""Template renderer: required-variable validation and rendering."""

from __future__ import annotations

import pytest
from app.modules.notifications.application.template_renderer import (
    render,
    validate_template,
)
from app.shared.exceptions import ValidationFailedError

SCHEMA = {
    "allowed": ["name", "job_title", "company_name", "action_url"],
    "required": ["name", "job_title"],
}


def test_render_happy_path() -> None:
    out = render(
        body="Chào {{name}}, vị trí {{job_title}} tại {{company_name}}.",
        subject="Cập nhật đơn ứng tuyển",
        title=None,
        variables={
            "name": "An",
            "job_title": "Backend Intern",
            "company_name": "VinBigdata",
        },
        variables_schema=SCHEMA,
    )
    assert out.body == "Chào An, vị trí Backend Intern tại VinBigdata."


def test_missing_required_variable_blocks_dispatch() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        render(
            body="Chào {{name}}, vị trí {{job_title}}.",
            subject=None,
            title=None,
            variables={"name": "An"},
            variables_schema=SCHEMA,
        )
    assert "job_title" in exc.value.details["missing_variables"]


def test_unknown_variable_blocks_render() -> None:
    with pytest.raises(ValidationFailedError) as exc:
        render(
            body="Chào {{name}} {{secret_field}}.",
            subject=None,
            title=None,
            variables={"name": "An", "job_title": "x"},
            variables_schema=SCHEMA,
        )
    assert "secret_field" in exc.value.details["unknown_variables"]


def test_validate_template_rejects_unknown_variable() -> None:
    with pytest.raises(ValidationFailedError):
        validate_template(
            body="Hello {{rogue}}",
            subject=None,
            title=None,
            variables_schema=SCHEMA,
        )


def test_action_url_must_be_internal_or_allowlisted() -> None:
    with pytest.raises(ValidationFailedError):
        render(
            body="Xem chi tiết: {{action_url}}",
            subject=None,
            title=None,
            variables={
                "name": "An",
                "job_title": "x",
                "action_url": "https://evil.example.com/phish",
            },
            variables_schema=SCHEMA,
        )
    # Internal relative URL is accepted.
    out = render(
        body="Xem chi tiết: {{action_url}}",
        subject=None,
        title=None,
        variables={"name": "An", "job_title": "x", "action_url": "/student/applications/1"},
        variables_schema=SCHEMA,
    )
    assert "/student/applications/1" in out.body
