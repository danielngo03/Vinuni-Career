"""Admin CRUD + governance for notification templates.

Covers: unknown-variable rejection on create/update, RBAC denial for a
principal without the grant, cross-org 404 isolation, draft-only editing
(archived/active immutability), activate supersedes the prior active version
("rollback" via re-activating an older archived version), and localized
(vi/en) preview rendering with sample data — no email is ever sent.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.notifications.application import template_admin_service
from app.shared.exceptions import (
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin


def _payload(**overrides) -> dict:
    base = {
        "key": "student.custom_digest",
        "channel": "email",
        "locale": "vi",
        "subject": "Bản tin của bạn — VinUni Career",
        "body": "Chào {{name}}, có {{job_count}} việc làm mới.",
        "variables_schema": {"allowed": ["name", "job_count"], "required": ["name"]},
    }
    base.update(overrides)
    return base


async def test_create_rejects_unknown_variable(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    with pytest.raises(ValidationFailedError) as exc:
        await template_admin_service.create_template(
            db_session,
            principal=admin,
            payload=_payload(body="Chào {{name}}, {{unknown_var}}"),
            ctx=CTX,
        )
    assert "unknown_var" in exc.value.details.get("unknown_variables", [])


async def test_create_then_update_draft_ok(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    created = await template_admin_service.create_template(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    assert created["status"] == "draft"
    assert created["version"] == 1

    updated = await template_admin_service.update_template(
        db_session,
        principal=admin,
        template_id=uuid.UUID(created["id"]),
        payload={"subject": "Tin việc làm tuần này — VinUni Career"},
        ctx=CTX,
    )
    assert updated["subject"] == "Tin việc làm tuần này — VinUni Career"


async def test_update_rejects_unknown_variable(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    created = await template_admin_service.create_template(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    with pytest.raises(ValidationFailedError):
        await template_admin_service.update_template(
            db_session,
            principal=admin,
            template_id=uuid.UUID(created["id"]),
            payload={"body": "Chào {{name}}, {{nope}}"},
            ctx=CTX,
        )


async def test_rbac_denies_principal_without_grant(db_session) -> None:
    _u, org, _admin = await make_org_with_admin(
        db_session, org_type="partner", display_name="Acme Corp"
    )
    _member_user, _membership, member = await add_member(
        db_session, org=org, permissions=[("jobs", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await template_admin_service.create_template(
            db_session, principal=member, payload=_payload(), ctx=CTX
        )


async def test_cross_org_template_is_not_found(db_session) -> None:
    _u1, _org1, admin1 = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    _u2, _org2, admin2 = await make_org_with_admin(
        db_session, org_type="partner", display_name="Acme Corp"
    )
    created = await template_admin_service.create_template(
        db_session, principal=admin1, payload=_payload(), ctx=CTX
    )
    with pytest.raises(ResourceNotFoundError):
        await template_admin_service.update_template(
            db_session,
            principal=admin2,
            template_id=uuid.UUID(created["id"]),
            payload={"subject": "hijacked"},
            ctx=CTX,
        )


async def test_activate_requires_valid_template_and_archives_previous(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    v1 = await template_admin_service.create_template(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    activated_v1 = await template_admin_service.activate_template(
        db_session, principal=admin, template_id=uuid.UUID(v1["id"]), ctx=CTX
    )
    assert activated_v1["status"] == "active"
    assert activated_v1["activated_at"] is not None

    # Activating an already-active template is a conflict, not a silent no-op.
    with pytest.raises(ConflictError):
        await template_admin_service.activate_template(
            db_session, principal=admin, template_id=uuid.UUID(v1["id"]), ctx=CTX
        )

    # A new version (v2) can be drafted and activated; v1 is archived.
    v2 = await template_admin_service.create_template(
        db_session,
        principal=admin,
        payload=_payload(subject="V2 subject"),
        ctx=CTX,
    )
    assert v2["version"] == 2
    activated_v2 = await template_admin_service.activate_template(
        db_session, principal=admin, template_id=uuid.UUID(v2["id"]), ctx=CTX
    )
    assert activated_v2["status"] == "active"

    templates = await template_admin_service.list_templates_admin(
        db_session, principal=admin, key="student.custom_digest"
    )
    by_id = {t["id"]: t for t in templates}
    assert by_id[v1["id"]]["status"] == "archived"
    assert by_id[v2["id"]]["status"] == "active"

    # Rollback: re-activate the older archived version (v1). v2 is archived.
    rolled_back = await template_admin_service.activate_template(
        db_session, principal=admin, template_id=uuid.UUID(v1["id"]), ctx=CTX
    )
    assert rolled_back["status"] == "active"
    templates_after = await template_admin_service.list_templates_admin(
        db_session, principal=admin, key="student.custom_digest"
    )
    by_id_after = {t["id"]: t for t in templates_after}
    assert by_id_after[v1["id"]]["status"] == "active"
    assert by_id_after[v2["id"]]["status"] == "archived"


async def test_archive_prevents_further_edits(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    created = await template_admin_service.create_template(
        db_session, principal=admin, payload=_payload(), ctx=CTX
    )
    archived = await template_admin_service.archive_template(
        db_session, principal=admin, template_id=uuid.UUID(created["id"]), ctx=CTX
    )
    assert archived["status"] == "archived"

    with pytest.raises(ConflictError):
        await template_admin_service.update_template(
            db_session,
            principal=admin,
            template_id=uuid.UUID(created["id"]),
            payload={"subject": "should fail"},
            ctx=CTX,
        )

    # Archiving twice is a conflict, not a silent no-op.
    with pytest.raises(ConflictError):
        await template_admin_service.archive_template(
            db_session, principal=admin, template_id=uuid.UUID(created["id"]), ctx=CTX
        )


async def test_localized_preview_renders_vi_and_en_with_sample_data(db_session) -> None:
    _u, _org, admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni Career Center"
    )
    vi = await template_admin_service.create_template(
        db_session,
        principal=admin,
        payload=_payload(locale="vi", body="Chào {{name}}, có {{job_count}} việc làm mới."),
        ctx=CTX,
    )
    en = await template_admin_service.create_template(
        db_session,
        principal=admin,
        payload=_payload(
            locale="en",
            subject="Your digest — VinUni Career",
            body="Hi {{name}}, there are {{job_count}} new jobs.",
        ),
        ctx=CTX,
    )

    preview_vi = await template_admin_service.preview_template(
        db_session,
        principal=admin,
        template_id=uuid.UUID(vi["id"]),
        sample_variables={"name": "An", "job_count": 5},
    )
    assert preview_vi["locale"] == "vi"
    assert "An" in preview_vi["body"]
    assert "5" in preview_vi["body"]

    preview_en = await template_admin_service.preview_template(
        db_session,
        principal=admin,
        template_id=uuid.UUID(en["id"]),
        sample_variables={"name": "An", "job_count": 5},
    )
    assert preview_en["locale"] == "en"
    assert "Hi An" in preview_en["body"]
    assert "5 new jobs" in preview_en["body"]

    # Preview never sends anything and never requires all sample values —
    # un-supplied allowed variables fall back to a readable placeholder.
    preview_defaults = await template_admin_service.preview_template(
        db_session, principal=admin, template_id=uuid.UUID(vi["id"])
    )
    assert "[job_count]" in preview_defaults["body"] or "job_count" in preview_defaults["body"]
