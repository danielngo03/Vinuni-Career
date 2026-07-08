"""Template renderer with required-variable validation.

Rules (``docs/NOTIFICATIONS_COMMUNICATIONS_SPEC.md`` §4):

- Unknown variables (used in body but not declared) block activation/render.
- Missing required variables block dispatch.
- ``action_url`` must be internal or on an approved allowlist.

Variable syntax is ``{{name}}``. ``variables_schema`` declares ``allowed`` and
``required`` variable names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.shared.exceptions import ValidationFailedError

_VAR_RE = re.compile(r"{{\s*(\w+)\s*}}")


@dataclass(slots=True)
class RenderedTemplate:
    subject: str | None
    title: str | None
    body: str


def extract_variables(*texts: str | None) -> set[str]:
    """Return the set of ``{{var}}`` names referenced across the given texts."""

    found: set[str] = set()
    for text in texts:
        if text:
            found.update(_VAR_RE.findall(text))
    return found


def _allowed_required(schema: dict) -> tuple[set[str], set[str]]:
    allowed = set(schema.get("allowed", []))
    required = set(schema.get("required", []))
    # Required variables are implicitly allowed.
    allowed |= required
    return allowed, required


def validate_template(
    *,
    body: str,
    subject: str | None,
    title: str | None,
    variables_schema: dict,
) -> None:
    """Validate a template definition before activation.

    Raises :class:`ValidationFailedError` if the template references variables not
    declared in ``allowed``/``required``.
    """

    allowed, _required = _allowed_required(variables_schema)
    used = extract_variables(body, subject, title)
    unknown = used - allowed
    if unknown:
        raise ValidationFailedError(
            "Mẫu sử dụng biến chưa được khai báo.",
            details={"unknown_variables": sorted(unknown)},
        )


def _is_safe_action_url(value: str, allowlist: set[str]) -> bool:
    if value.startswith("/"):  # internal relative path
        return True
    return any(value.startswith(prefix) for prefix in allowlist)


def render(
    *,
    body: str,
    subject: str | None,
    title: str | None,
    variables: dict[str, object],
    variables_schema: dict,
    action_url_allowlist: set[str] | None = None,
) -> RenderedTemplate:
    """Render a template, validating required + unknown variables and ``action_url``."""

    allowed, required = _allowed_required(variables_schema)
    used = extract_variables(body, subject, title)

    unknown = used - allowed
    if unknown:
        raise ValidationFailedError(
            "Mẫu sử dụng biến chưa được khai báo.",
            details={"unknown_variables": sorted(unknown)},
        )

    missing = required - set(variables.keys())
    if missing:
        raise ValidationFailedError(
            "Thiếu biến bắt buộc để gửi thông báo.",
            details={"missing_variables": sorted(missing)},
        )

    # action_url safety check.
    if "action_url" in variables:
        allowlist = action_url_allowlist or set()
        if not _is_safe_action_url(str(variables["action_url"]), allowlist):
            raise ValidationFailedError(
                "Liên kết hành động không hợp lệ.",
                details={"field": "action_url"},
            )

    def _sub(text: str | None) -> str | None:
        if text is None:
            return None
        return _VAR_RE.sub(lambda m: str(variables.get(m.group(1), "")), text)

    return RenderedTemplate(
        subject=_sub(subject),
        title=_sub(title),
        body=_sub(body) or "",
    )
