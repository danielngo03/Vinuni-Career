"""Account emails must not rely on a display name existing.

Registration is email/password only (``CLAUDE.md``): a freshly-registered user
has no name until onboarding / profile / CV confirmation. So the account-email
templates that greet by name must not declare ``name`` as a *required* render
variable, and rendering them without a name must not fail dispatch nor emit an
empty ``Hi ,`` / ``Chào ,`` greeting.
"""

from __future__ import annotations

import pytest
from app.modules.notifications.application.template_renderer import render
from app.modules.notifications.application.template_seed_data import DEFAULT_TEMPLATES

# Account emails that can be sent to a user who may not have a name yet.
_NAME_OPTIONAL_KEYS = [
    "account.password_changed",
    "account.student_email_verification",
    "account.email_verification",
    "account.password_reset",
]


def _spec(key: str) -> dict:
    for spec in DEFAULT_TEMPLATES:
        if spec["key"] == key:
            return spec
    raise AssertionError(f"template {key} not found")


@pytest.mark.parametrize("key", _NAME_OPTIONAL_KEYS)
def test_name_is_never_a_required_variable(key: str) -> None:
    required = set(_spec(key)["variables_schema"].get("required", []))
    assert "name" not in required, f"{key} must not require a display name"


@pytest.mark.parametrize("key", ["account.password_changed", "account.student_email_verification"])
@pytest.mark.parametrize("locale", ["vi", "en"])
def test_renders_without_a_name_variable(key: str, locale: str) -> None:
    """Omitting ``name`` entirely must not raise (no required-variable failure)."""

    spec = _spec(key)
    content = spec["locales"][locale]
    variables: dict[str, object] = {"email": "someone@vinuni.edu.vn", "otp_code": "123456"}
    # Deliberately NO "name" key.
    rendered = render(
        body=content["body"],
        subject=content.get("subject"),
        title=content.get("title"),
        variables=variables,
        variables_schema=spec["variables_schema"],
    )
    assert rendered.body  # rendered without error


@pytest.mark.parametrize("key", ["account.password_changed", "account.student_email_verification"])
@pytest.mark.parametrize("locale", ["vi", "en"])
def test_greeting_uses_email_fallback_when_no_name(key: str, locale: str) -> None:
    """The sender's non-empty greeting fallback (email) renders a real greeting,
    never a dangling ``Hi ,`` / ``Chào ,``."""

    spec = _spec(key)
    content = spec["locales"][locale]
    email = "jane@vinuni.edu.vn"
    rendered = render(
        body=content["body"],
        subject=content.get("subject"),
        title=content.get("title"),
        variables={"email": email, "name": email, "otp_code": "123456", "ttl_minutes": "10"},
        variables_schema=spec["variables_schema"],
    )
    assert email in rendered.body
    # No empty greeting artifacts.
    assert "Chào ,\n" not in rendered.body
    assert "Hi ,\n" not in rendered.body
