"""CV Studio visual canvas + profile-photo tests.

Covers (``docs/CV_STUDIO_SPEC.md`` "Visual Canvas Editor Contract"):

- canvas block CRUD/ordering: valid blocks persist, versioned + audited;
- invalid block payloads (bad type, duplicate id, unknown section_id, bad order)
  are rejected;
- canvas update never clobbers a previously-set photo binding (partial merge);
- optimistic-concurrency (``expected_version``) conflict;
- photo replace/crop happy path + invalid crop rect + invalid file type/size +
  RBAC (owner-only) + remove;
- restoring a prior version restores canvas layout too.
"""

from __future__ import annotations

import uuid

import pytest
from app.modules.documents.application import (
    cv_canvas_service,
    cv_photo_service,
    cv_section_service,
    cv_service,
)
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCropRectError,
    InvalidCvFieldError,
    InvalidPhotoFileError,
)
from app.modules.documents.domain.models import CvSection, CvVersion
from app.modules.documents.infrastructure import storage
from app.shared.exceptions import ResourceNotFoundError
from app.shared.models import AuditLog
from sqlalchemy import func, select

from tests.auth_utils import CTX
from tests.documents_utils import InMemoryStorage, make_student

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _isolated_storage():
    storage.set_storage(InMemoryStorage())
    yield
    storage.set_storage(None)


async def _audit_count(db, action: str) -> int:
    return (
        await db.execute(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == action)
        )
    ).scalar_one()


async def _make_cv(db, student, *, title="My CV") -> dict:
    return await cv_service.create_cv(
        db,
        principal=student,
        payload={"title": title, "creation_mode": "blank_template"},
        ctx=CTX,
    )


async def _section_id(db, cv_id, section_type) -> uuid.UUID:
    sections = (
        (await db.execute(select(CvSection).where(CvSection.cv_id == uuid.UUID(cv_id))))
        .scalars()
        .all()
    )
    return next(s for s in sections if s.section_type == section_type).id


# --------------------------------------------------------------------------- #
# Canvas block CRUD / ordering                                                #
# --------------------------------------------------------------------------- #


async def test_update_canvas_persists_blocks_versioned_and_audited(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    summary_id = await _section_id(db_session, cv["id"], "summary")
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    versions_before = len(before["versions"])

    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "blocks": [
                {
                    "id": "b1",
                    "type": "heading",
                    "section_id": str(summary_id),
                    "order": 0,
                    "visible": True,
                },
                {
                    "id": "b2",
                    "type": "text",
                    "section_id": str(summary_id),
                    "order": 1,
                    "visible": True,
                    "style": {"font_size": 12},
                },
            ],
        },
        ctx=CTX,
    )
    assert data["canvas"]["blocks"][0]["id"] == "b1"
    assert data["canvas"]["blocks"][1]["style"] == {"font_size": 12}
    assert data["version"] == before["version"] + 1
    assert len(data["versions"]) == versions_before + 1
    assert await _audit_count(db_session, "cv.canvas.updated") == 1


async def test_update_canvas_reorders_blocks(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]},
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 5}]},
        ctx=CTX,
    )
    assert data["canvas"]["blocks"][0]["order"] == 5


async def test_update_canvas_rejects_unknown_section_id(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={
                "blocks": [
                    {"id": "b1", "type": "text", "section_id": str(uuid.uuid4()), "order": 0}
                ]
            },
            ctx=CTX,
        )


async def test_update_canvas_rejects_invalid_block_type(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": [{"id": "b1", "type": "not_a_type", "order": 0}]},
            ctx=CTX,
        )


async def test_update_canvas_rejects_duplicate_block_ids(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={
                "blocks": [
                    {"id": "dup", "type": "text", "order": 0},
                    {"id": "dup", "type": "text", "order": 1},
                ]
            },
            ctx=CTX,
        )


async def test_update_canvas_version_conflict(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(CvVersionConflictError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": [], "expected_version": 999},
            ctx=CTX,
        )


async def test_update_canvas_never_clobbers_photo(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="p.png",
        crop=None,
        shape="circle",
        expected_version=None,
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]},
        ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"


async def test_restore_version_restores_canvas(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    v1 = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]},
        ctx=CTX,
    )
    v1_id = v1["current_version_id"]
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b2", "type": "text", "order": 0}]},
        ctx=CTX,
    )
    restored = await cv_section_service.restore_version(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        version_id=uuid.UUID(v1_id),
        payload=None,
        ctx=CTX,
    )
    assert restored["canvas"]["blocks"][0]["id"] == "b1"


async def test_canvas_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=other,
            cv_id=uuid.UUID(cv["id"]),
            payload={"blocks": []},
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Theme overrides (student restyle rail — partial theme layered on template)  #
# --------------------------------------------------------------------------- #


async def _latest_snapshot(db, cv_id: str) -> dict:
    row = (
        await db.execute(
            select(CvVersion)
            .where(CvVersion.cv_id == uuid.UUID(cv_id))
            .order_by(CvVersion.version_number.desc())
            .limit(1)
        )
    ).scalar_one()
    return row.snapshot_json


async def test_update_canvas_persists_theme_override_and_snapshot(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "theme": {
                "palette": {"accent": "#0F766E", "primary": "#123"},
                "typography": {"bodyFont": "serif", "headingCase": "upper", "scale": "compact"},
                "sectionStyle": {"itemGap": "tight"},
            }
        },
        ctx=CTX,
    )
    theme = data["canvas"]["theme"]
    assert theme["palette"] == {"accent": "#0F766E", "primary": "#123"}
    assert theme["typography"] == {
        "bodyFont": "serif",
        "headingCase": "upper",
        "scale": "compact",
    }
    assert theme["sectionStyle"] == {"itemGap": "tight"}
    # Theme is a canvas write: versioned + audited via the same canvas action.
    assert await _audit_count(db_session, "cv.canvas.updated") == 1
    # And it flows into the next immutable version snapshot (under canvas).
    snapshot = await _latest_snapshot(db_session, cv["id"])
    assert snapshot["canvas"]["theme"] == theme


async def test_update_canvas_theme_strips_unknown_keys(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "theme": {
                "palette": {"accent": "#0F766E", "bogusSlot": "#000000"},
                "typography": {"bodyFont": "serif", "bogus": "x"},
                "sectionStyle": {"itemGap": "tight", "bogus": "x"},
                "bogusTopLevel": {"a": 1},
            }
        },
        ctx=CTX,
    )
    theme = data["canvas"]["theme"]
    assert theme["palette"] == {"accent": "#0F766E"}
    assert theme["typography"] == {"bodyFont": "serif"}
    assert theme["sectionStyle"] == {"itemGap": "tight"}
    assert "bogusTopLevel" not in theme


async def test_update_canvas_empty_theme_resets_to_template_default(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"theme": {"palette": {"accent": "#0F766E"}}},
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"theme": {}},
        ctx=CTX,
    )
    assert "theme" not in data["canvas"]


async def test_update_canvas_rejects_invalid_hex_palette(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"theme": {"palette": {"accent": "teal"}}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.theme.palette"


async def test_update_canvas_rejects_invalid_font_token(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"theme": {"typography": {"bodyFont": "comic-sans"}}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.theme.typography"


async def test_update_canvas_rejects_invalid_scale_token(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"theme": {"typography": {"scale": "huge"}}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.theme.typography"


async def test_update_canvas_rejects_invalid_item_gap(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"theme": {"sectionStyle": {"itemGap": "roomy"}}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.theme.sectionStyle"


async def test_update_canvas_theme_does_not_wipe_blocks_or_photo(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    # Seed a photo + blocks first, then a theme-only update must preserve both.
    await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="p.png",
        crop=None,
        shape="circle",
        expected_version=None,
        ctx=CTX,
    )
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"blocks": [{"id": "b1", "type": "text", "order": 0}]},
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"theme": {"palette": {"accent": "#0F766E"}}},
        ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"
    assert data["canvas"]["blocks"][0]["id"] == "b1"
    assert data["canvas"]["theme"]["palette"] == {"accent": "#0F766E"}


async def test_theme_override_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await cv_canvas_service.update_canvas(
            db_session,
            principal=other,
            cv_id=uuid.UUID(cv["id"]),
            payload={"theme": {"palette": {"accent": "#0F766E"}}},
            ctx=CTX,
        )


# --------------------------------------------------------------------------- #
# Per-element style overrides (contextual text toolbar — design spec §"Data     #
# contracts" 1). ``canvas.elementStyles = {editPath: ElementStyle}``.           #
# --------------------------------------------------------------------------- #


async def test_update_canvas_persists_element_styles_and_snapshot(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)

    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "elementStyles": {
                "header.name": {
                    "font": "serif",
                    "size": "2xl",
                    "weight": "bold",
                    "italic": True,
                    "align": "center",
                    "color": "#0F766E",
                },
                "summary.text": {"size": "sm", "align": "left"},
            }
        },
        ctx=CTX,
    )
    styles = data["canvas"]["elementStyles"]
    assert styles["header.name"] == {
        "font": "serif",
        "size": "2xl",
        "weight": "bold",
        "italic": True,
        "align": "center",
        "color": "#0F766E",
    }
    assert styles["summary.text"] == {"size": "sm", "align": "left"}
    # Element styles are a canvas write: versioned + audited via the canvas action.
    assert await _audit_count(db_session, "cv.canvas.updated") == 1
    # And it flows into the next immutable version snapshot (under canvas).
    snapshot = await _latest_snapshot(db_session, cv["id"])
    assert snapshot["canvas"]["elementStyles"] == styles
    # And the CV detail response carries it back verbatim.
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    assert detail["canvas"]["elementStyles"] == styles


async def test_update_canvas_element_styles_strips_unknown_subkeys(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "elementStyles": {
                "header.name": {"size": "lg", "bogus": "x", "fontFamily": "Arial"},
            }
        },
        ctx=CTX,
    )
    assert data["canvas"]["elementStyles"]["header.name"] == {"size": "lg"}


async def test_update_canvas_element_styles_drops_empty_path_entries(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "elementStyles": {
                "header.name": {"size": "lg"},
                # Only unknown sub-keys -> cleans to {} -> whole entry dropped.
                "summary.text": {"bogus": "x"},
                "skills.0": {},
            }
        },
        ctx=CTX,
    )
    styles = data["canvas"]["elementStyles"]
    assert styles == {"header.name": {"size": "lg"}}
    assert "summary.text" not in styles
    assert "skills.0" not in styles


async def test_update_canvas_empty_element_styles_resets(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"elementStyles": {"header.name": {"size": "lg"}}},
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"elementStyles": {}},
        ctx=CTX,
    )
    assert "elementStyles" not in data["canvas"]


async def test_update_canvas_element_styles_snake_case_alias(db_session) -> None:
    """The router may hand the snake_case key; both mean the same map."""
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"element_styles": {"header.name": {"align": "right"}}},
        ctx=CTX,
    )
    assert data["canvas"]["elementStyles"]["header.name"] == {"align": "right"}


@pytest.mark.parametrize(
    ("style", "field"),
    [
        ({"font": "comic-sans"}, "canvas.elementStyles.font"),
        ({"size": "huge"}, "canvas.elementStyles.size"),
        ({"weight": "black"}, "canvas.elementStyles.weight"),
        ({"align": "justify"}, "canvas.elementStyles.align"),
        ({"color": "teal"}, "canvas.elementStyles.color"),
        ({"italic": "yes"}, "canvas.elementStyles.italic"),
    ],
)
async def test_update_canvas_element_styles_rejects_bad_value(db_session, style, field) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"elementStyles": {"header.name": style}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == field


async def test_update_canvas_element_styles_rejects_non_dict(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"elementStyles": ["not", "a", "dict"]},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.elementStyles"


async def test_update_canvas_element_styles_rejects_empty_path_key(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"elementStyles": {"   ": {"size": "lg"}}},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.elementStyles"


async def test_update_canvas_element_styles_caps_path_count(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    too_many = {f"p.{i}": {"size": "lg"} for i in range(501)}
    with pytest.raises(InvalidCvFieldError) as exc:
        await cv_canvas_service.update_canvas(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            payload={"elementStyles": too_many},
            ctx=CTX,
        )
    assert exc.value.details["field"] == "canvas.elementStyles"


async def test_element_styles_do_not_wipe_theme_or_blocks_or_photo(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="p.png",
        crop=None,
        shape="circle",
        expected_version=None,
        ctx=CTX,
    )
    await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={
            "blocks": [{"id": "b1", "type": "text", "order": 0}],
            "theme": {"palette": {"accent": "#0F766E"}},
        },
        ctx=CTX,
    )
    data = await cv_canvas_service.update_canvas(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        payload={"elementStyles": {"header.name": {"size": "lg"}}},
        ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"
    assert data["canvas"]["blocks"][0]["id"] == "b1"
    assert data["canvas"]["theme"]["palette"] == {"accent": "#0F766E"}
    assert data["canvas"]["elementStyles"]["header.name"] == {"size": "lg"}


# --------------------------------------------------------------------------- #
# Header (name/contact) editing round-trips through the section PATCH path     #
# (the P2 frontend header-edit surface writes contact content this way).       #
# --------------------------------------------------------------------------- #


async def test_header_section_contact_content_round_trips(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    header_id = await _section_id(db_session, cv["id"], "header")
    contact = {
        "name": "Nguyen Van A",
        "headline": "Software Engineer",
        "email": "a@example.com",
        "phone": "+84 90 000 0000",
        "location": "Hanoi, Vietnam",
        "links": [{"label": "GitHub", "url": "https://github.com/a"}],
    }
    await cv_section_service.upsert_section(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        section_id=header_id,
        payload={"content": contact},
        ctx=CTX,
    )
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    header = next(s for s in detail["sections"] if s["section_type"] == "header")
    assert header["content"] == contact


async def test_header_typed_link_round_trips(db_session) -> None:
    """A header link with a ``type`` (design spec §"Data contracts" 2) survives the
    section upsert + CV detail round-trip: nothing strips the extra key."""
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    header_id = await _section_id(db_session, cv["id"], "header")
    contact = {
        "name": "Nguyen Van A",
        "links": [
            {"label": "GitHub", "url": "https://github.com/a", "type": "github"},
            {"label": "LinkedIn", "url": "https://linkedin.com/in/a", "type": "linkedin"},
            {"label": "Site", "url": "https://a.dev"},  # no type -> passed through as-is
        ],
    }
    await cv_section_service.upsert_section(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        section_id=header_id,
        payload={"content": contact},
        ctx=CTX,
    )
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    header = next(s for s in detail["sections"] if s["section_type"] == "header")
    links = header["content"]["links"]
    assert links[0] == {"label": "GitHub", "url": "https://github.com/a", "type": "github"}
    assert links[1]["type"] == "linkedin"
    assert "type" not in links[2]


# --------------------------------------------------------------------------- #
# Photo replace/crop/remove                                                   #
# --------------------------------------------------------------------------- #


async def test_photo_update_happy_path(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    before = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))

    data = await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="me.png",
        crop={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        shape="circle",
        expected_version=None,
        ctx=CTX,
    )
    assert data["canvas"]["photo"]["shape"] == "circle"
    assert data["canvas"]["photo"]["crop"]["width"] == 0.8
    assert data["canvas"]["photo"]["document_id"]
    assert data["version"] == before["version"] + 1
    assert await _audit_count(db_session, "cv.photo.updated") == 1
    # storage_path / storage_key never leak.
    import json

    assert "storage_path" not in json.dumps(data)
    assert "storage_key" not in json.dumps(data)


async def test_cv_detail_resolves_canvas_photo_signed_url(db_session) -> None:
    """The CV detail must expose a signed, *displayable* ``canvas.photo.url``.

    The canvas persists only the photo ``document_id`` (never a storage key); the
    renderer/preview/PDF need a real URL, so ``_detail_response`` mints a signed
    ``/api/v1/cv-files/{token}`` link. Verify it is present, round-trips back to
    the stored image bytes via the download service, and leaks no storage key.
    """
    from app.modules.documents.application import download_service

    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="me.png",
        crop={"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8},
        shape="circle",
        expected_version=None,
        ctx=CTX,
    )
    detail = await cv_service.get_cv(db_session, principal=student, cv_id=uuid.UUID(cv["id"]))
    photo = detail["canvas"]["photo"]
    assert photo["document_id"]
    assert isinstance(photo.get("url"), str) and photo["url"]
    assert "/api/v1/cv-files/" in photo["url"]

    # The signed token resolves back to the exact stored image (owner-scoped).
    token = photo["url"].rsplit("/", 1)[-1]
    result = await download_service.resolve_download(db_session, token=token, ctx=CTX)
    assert result.content == _PNG_MAGIC
    assert result.media_type == "image/png"

    # Resolving a URL must not leak the underlying storage key/path.
    import json

    assert "storage_path" not in json.dumps(detail)
    assert "storage_key" not in json.dumps(detail)


async def test_photo_replace_overwrites_binding(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    first = await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="a.png",
        crop=None,
        shape="square",
        expected_version=None,
        ctx=CTX,
    )
    second = await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="b.png",
        crop=None,
        shape="circle",
        expected_version=first["version"],
        ctx=CTX,
    )
    assert second["canvas"]["photo"]["shape"] == "circle"
    assert second["canvas"]["photo"]["document_id"] != first["canvas"]["photo"]["document_id"]


async def test_photo_remove(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    await cv_photo_service.update_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        data=_PNG_MAGIC,
        content_type="image/png",
        filename="a.png",
        crop=None,
        shape="square",
        expected_version=None,
        ctx=CTX,
    )
    removed = await cv_photo_service.remove_photo(
        db_session,
        principal=student,
        cv_id=uuid.UUID(cv["id"]),
        expected_version=None,
        ctx=CTX,
    )
    assert "photo" not in removed["canvas"]
    assert await _audit_count(db_session, "cv.photo.removed") == 1


@pytest.mark.parametrize(
    "crop",
    [
        {"x": -0.1, "y": 0, "width": 1, "height": 1},
        {"x": 0, "y": 0, "width": 0, "height": 1},
        {"x": 0.5, "y": 0, "width": 0.8, "height": 1},
        {"x": 0, "y": 0, "width": "nope", "height": 1},
    ],
)
async def test_photo_invalid_crop_rect_rejected(db_session, crop) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidCropRectError):
        await cv_photo_service.update_photo(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC,
            content_type="image/png",
            filename="a.png",
            crop=crop,
            shape="square",
            expected_version=None,
            ctx=CTX,
        )


async def test_photo_invalid_file_type_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            data=b"not an image",
            content_type="application/pdf",
            filename="a.pdf",
            crop=None,
            shape="square",
            expected_version=None,
            ctx=CTX,
        )


async def test_photo_empty_file_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            data=b"",
            content_type="image/png",
            filename="a.png",
            crop=None,
            shape="square",
            expected_version=None,
            ctx=CTX,
        )


async def test_photo_oversized_file_rejected(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(InvalidPhotoFileError):
        await cv_photo_service.update_photo(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            data=b"0" * (9 * 1024 * 1024),
            content_type="image/png",
            filename="a.png",
            crop=None,
            shape="square",
            expected_version=None,
            ctx=CTX,
        )


async def test_photo_version_conflict(db_session) -> None:
    _u, student = await make_student(db_session)
    cv = await _make_cv(db_session, student)
    with pytest.raises(CvVersionConflictError):
        await cv_photo_service.update_photo(
            db_session,
            principal=student,
            cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC,
            content_type="image/png",
            filename="a.png",
            crop=None,
            shape="square",
            expected_version=999,
            ctx=CTX,
        )


async def test_photo_cross_owner_404(db_session) -> None:
    _u, student = await make_student(db_session)
    _u2, other = await make_student(db_session, prefix="other")
    cv = await _make_cv(db_session, student)
    with pytest.raises(ResourceNotFoundError):
        await cv_photo_service.update_photo(
            db_session,
            principal=other,
            cv_id=uuid.UUID(cv["id"]),
            data=_PNG_MAGIC,
            content_type="image/png",
            filename="a.png",
            crop=None,
            shape="square",
            expected_version=None,
            ctx=CTX,
        )
