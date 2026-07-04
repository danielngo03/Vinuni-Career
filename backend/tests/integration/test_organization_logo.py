"""Organization logo media pipeline tests.

Covers the upload/serve/remove pipeline and the ``public_logo_url`` resolution
that lights up ``logo_url`` across the directory, company detail, spotlight, and
embedded job ``company`` blocks. Emphasis on RBAC + tenant isolation (cross-org
hidden as 404), magic-byte validation (non-image/oversize rejected with a
user-safe error), and public-visibility leakage (suspended/pending never serve).
"""

from __future__ import annotations

import uuid

import pytest
from app.main import app
from app.modules.documents.infrastructure import storage
from app.modules.organization.api import public_presenters
from app.modules.organization.application import logo_service
from app.modules.organization.application.errors import VersionConflictError
from app.modules.organization.domain.models import Organization
from app.shared.exceptions import (
    PermissionDeniedError,
    ResourceNotFoundError,
    ValidationFailedError,
)
from app.shared.models import AuditLog
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.org_utils import add_member, make_org_with_admin

# Smallest byte payloads that pass / fail the magic-byte sniff.
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 64
NOT_AN_IMAGE = b"this is plainly not an image, just ASCII text content"


class _MemoryStorage:
    """In-memory ``StorageBackend`` so tests never touch the filesystem."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def save(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def load(self, key: str) -> bytes:
        try:
            return self._data[key]
        except KeyError as exc:
            raise storage.StorageError("object not found") from exc

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


@pytest.fixture(autouse=True)
def _memory_storage():
    backend = _MemoryStorage()
    storage.set_storage(backend)
    yield backend
    storage.set_storage(None)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


async def _audit_count(db_session, action: str) -> int:
    return (
        await db_session.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _reload(db_session, org_id: uuid.UUID) -> Organization:
    return (
        await db_session.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one()


async def _set_status(db_session, org, status: str) -> None:
    org.status = status
    db_session.add(org)
    await db_session.commit()


# --------------------------------------------------------------------------- #
# Upload happy path + public serve                                            #
# --------------------------------------------------------------------------- #


async def test_upload_sets_logo_and_serve_returns_bytes(db_session, _memory_storage):
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme Co")
    before = await _audit_count(db_session, "organization.logo_updated")

    result = await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    # Detail projection exposes the safe URL, never the raw storage key.
    assert "logo_path" not in result
    assert result["logo_url"].endswith(f"/companies/{org.slug}/logo?v={result['version']}")

    refreshed = await _reload(db_session, org.id)
    assert refreshed.logo_path and refreshed.logo_path.startswith(f"org-logos/{org.id}/")
    assert refreshed.version == 2  # bumped from the create's version 1

    served = await logo_service.serve_logo(db_session, slug=org.slug)
    assert served.content == PNG_BYTES
    assert served.media_type == "image/png"

    assert await _audit_count(db_session, "organization.logo_updated") == before + 1


@pytest.mark.parametrize(
    ("data", "content_type", "media_type"),
    [
        (JPEG_BYTES, "image/jpeg", "image/jpeg"),
        (WEBP_BYTES, "image/webp", "image/webp"),
    ],
)
async def test_upload_accepts_jpeg_and_webp(db_session, data, content_type, media_type):
    _u, org, admin = await make_org_with_admin(db_session)
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo",
        data=data, content_type=content_type, expected_version=None, ctx=CTX,
    )
    served = await logo_service.serve_logo(db_session, slug=org.slug)
    assert served.media_type == media_type


async def test_replacing_logo_deletes_old_object(db_session, _memory_storage):
    _u, org, admin = await make_org_with_admin(db_session)
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="a.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    first_key = (await _reload(db_session, org.id)).logo_path
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="b.webp",
        data=WEBP_BYTES, content_type="image/webp", expected_version=None, ctx=CTX,
    )
    second_key = (await _reload(db_session, org.id)).logo_path
    assert first_key != second_key
    assert not _memory_storage.exists(first_key)  # superseded object cleaned up
    assert _memory_storage.exists(second_key)


# --------------------------------------------------------------------------- #
# Validation: non-image / oversize / empty                                    #
# --------------------------------------------------------------------------- #


async def test_non_image_rejected_user_safe(db_session):
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(ValidationFailedError) as exc:
        await logo_service.upload_logo(
            db_session, principal=admin, org_id=org.id, filename="cv.png",
            data=NOT_AN_IMAGE, content_type="image/png", expected_version=None, ctx=CTX,
        )
    assert exc.value.details["reason"] == "unsupported_image_type"
    # Nothing persisted on rejection.
    assert (await _reload(db_session, org.id)).logo_path is None


async def test_declared_type_not_in_allowlist_rejected(db_session):
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(ValidationFailedError):
        await logo_service.upload_logo(
            db_session, principal=admin, org_id=org.id, filename="x.gif",
            data=PNG_BYTES, content_type="image/gif", expected_version=None, ctx=CTX,
        )


async def test_oversize_rejected(db_session, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.get_settings(), "org_logo_max_mb", 0, raising=False)
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(ValidationFailedError) as exc:
        await logo_service.upload_logo(
            db_session, principal=admin, org_id=org.id, filename="logo.png",
            data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
        )
    assert exc.value.details["reason"] == "file_too_large"


async def test_empty_file_rejected(db_session):
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(ValidationFailedError) as exc:
        await logo_service.upload_logo(
            db_session, principal=admin, org_id=org.id, filename="logo.png",
            data=b"", content_type="image/png", expected_version=None, ctx=CTX,
        )
    assert exc.value.details["reason"] == "empty_file"


# --------------------------------------------------------------------------- #
# RBAC + tenant isolation                                                     #
# --------------------------------------------------------------------------- #


async def test_member_without_update_permission_denied_403(db_session):
    _u, org, _admin = await make_org_with_admin(db_session)
    _mu, _m, member = await add_member(
        db_session, org=org, permissions=[("members", "read")]
    )
    with pytest.raises(PermissionDeniedError):
        await logo_service.upload_logo(
            db_session, principal=member, org_id=org.id, filename="logo.png",
            data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
        )


async def test_cross_org_upload_is_404(db_session):
    _ua, _org_a, admin_a = await make_org_with_admin(db_session, display_name="Org A")
    _ub, org_b, _admin_b = await make_org_with_admin(db_session, display_name="Org B")
    # Admin A targets Org B's id -> hidden as 404, never 403 (no enumeration).
    with pytest.raises(ResourceNotFoundError):
        await logo_service.upload_logo(
            db_session, principal=admin_a, org_id=org_b.id, filename="logo.png",
            data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
        )
    assert (await _reload(db_session, org_b.id)).logo_path is None


async def test_upload_version_conflict(db_session):
    _u, org, admin = await make_org_with_admin(db_session)
    with pytest.raises(VersionConflictError):
        await logo_service.upload_logo(
            db_session, principal=admin, org_id=org.id, filename="logo.png",
            data=PNG_BYTES, content_type="image/png", expected_version=999, ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Removal                                                                     #
# --------------------------------------------------------------------------- #


async def test_remove_logo_clears_and_audits(db_session, _memory_storage):
    _u, org, admin = await make_org_with_admin(db_session)
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    key = (await _reload(db_session, org.id)).logo_path
    before = await _audit_count(db_session, "organization.logo_removed")

    result = await logo_service.remove_logo(
        db_session, principal=admin, org_id=org.id, expected_version=None, ctx=CTX,
    )
    assert result["logo_url"] is None
    assert (await _reload(db_session, org.id)).logo_path is None
    assert not _memory_storage.exists(key)
    assert await _audit_count(db_session, "organization.logo_removed") == before + 1
    # Public serve now 404s.
    with pytest.raises(ResourceNotFoundError):
        await logo_service.serve_logo(db_session, slug=org.slug)


# --------------------------------------------------------------------------- #
# public_logo_url resolution + public-visibility leakage                      #
# --------------------------------------------------------------------------- #


async def test_public_logo_url_none_before_url_after(db_session):
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme Co")
    org = await _reload(db_session, org.id)
    assert public_presenters.public_logo_url(org) is None

    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    org = await _reload(db_session, org.id)
    url = public_presenters.public_logo_url(org)
    assert url is not None and f"/companies/{org.slug}/logo" in url
    assert org.logo_path not in url  # raw storage key never leaks into the URL


async def test_serve_404_for_suspended_and_pending(db_session):
    _u, org, admin = await make_org_with_admin(db_session)
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    org = await _reload(db_session, org.id)
    await _set_status(db_session, org, "suspended")
    with pytest.raises(ResourceNotFoundError):
        await logo_service.serve_logo(db_session, slug=org.slug)

    await _set_status(db_session, await _reload(db_session, org.id), "pending")
    with pytest.raises(ResourceNotFoundError):
        await logo_service.serve_logo(db_session, slug=org.slug)


async def test_serve_404_for_university_and_missing(db_session):
    _u, uni, uni_admin = await make_org_with_admin(
        db_session, org_type="university", display_name="VinUni"
    )
    await logo_service.upload_logo(
        db_session, principal=uni_admin, org_id=uni.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )
    # University orgs are never publicly listable -> never serve a logo.
    with pytest.raises(ResourceNotFoundError):
        await logo_service.serve_logo(db_session, slug=uni.slug)
    with pytest.raises(ResourceNotFoundError):
        await logo_service.serve_logo(db_session, slug="no-such-company")


# --------------------------------------------------------------------------- #
# HTTP contract for the public serve route                                    #
# --------------------------------------------------------------------------- #


async def test_http_public_logo_serve_contract(client, db_session):
    _u, org, admin = await make_org_with_admin(db_session, display_name="Acme Co")
    await logo_service.upload_logo(
        db_session, principal=admin, org_id=org.id, filename="logo.png",
        data=PNG_BYTES, content_type="image/png", expected_version=None, ctx=CTX,
    )

    resp = await client.get(f"/companies/{org.slug}/logo")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/png")
    assert "max-age" in resp.headers.get("cache-control", "")
    assert resp.content == PNG_BYTES

    missing = await client.get("/companies/no-such-company/logo")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
