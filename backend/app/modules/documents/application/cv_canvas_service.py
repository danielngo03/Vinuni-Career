"""CV Studio visual canvas layout mutations (``docs/CV_STUDIO_SPEC.md`` "Visual
Canvas Editor Contract").

``cv_profiles.canvas_json`` is PRESENTATION/LAYOUT metadata only: block
ordering/position/visibility overrides (keyed by a stable client-generated
``block.id``, optionally bound to an existing ``cv_sections`` row), page
settings, and per-CV student restyle overrides (``theme`` — a PARTIAL theme the
renderer layers on top of the chosen template's theme: recolour/font/density
without forking the template). It never duplicates or overrides CV FACTS — those
stay in ``cv_sections.content_json`` and are mutated only through
``cv_section_service``. The profile-photo binding is a sibling key
(``canvas_json["photo"]``) managed exclusively by ``cv_photo_service`` — a
canvas update here only ever replaces the ``blocks``/``page``/``theme``/
``elementStyles`` keys it was given, so it can never silently drop the photo (or
any key it wasn't handed). ``elementStyles`` is the per-element style override map
for the contextual text toolbar (``{editPath: ElementStyle}``): opaque client
``editPath`` strings mapped to a small fixed style vocabulary the renderer layers
on top of the theme, per text node.

RBAC + ownership mirror every other CV mutation: owner-only (404 on cross-owner
access), versioned (bumps ``cv.version`` + writes a ``cv_versions`` snapshot),
audited, and optimistic-concurrency gated via ``expected_version``.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.application.context import RequestContext
from app.modules.documents.application import _cv_core, _shared
from app.modules.documents.application.errors import (
    CvVersionConflictError,
    InvalidCvFieldError,
)
from app.modules.documents.domain import themes
from app.shared.audit import write_audit
from app.shared.permissions import permission_checker

_RESOURCE = _shared.RESOURCE

# --------------------------------------------------------------------------- #
# Theme-override vocabulary (student restyle rail). A ``canvas_json["theme"]``  #
# is a PARTIAL theme layered on top of the template theme by the renderer, so   #
# only the sub-keys below are accepted; anything else is stripped and any wrong #
# TYPE/value is rejected with a precise ``canvas.theme.*`` field. Palette keys  #
# and font tokens reuse the canonical vocab in ``domain.themes`` so the         #
# override can never introduce a colour slot or font the renderer can't map.    #
# --------------------------------------------------------------------------- #
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_SCALE_TOKENS = frozenset({"compact", "regular"})
_HEADING_CASE_TOKENS = frozenset({"normal", "upper"})
_ITEM_GAP_TOKENS = frozenset({"tight", "regular"})
_TYPOGRAPHY_FONT_KEYS = frozenset({"headingFont", "bodyFont"})

# --------------------------------------------------------------------------- #
# Per-element style overrides (contextual text toolbar — design spec §"Data     #
# contracts" 1). ``canvas_json["elementStyles"] = {editPath: ElementStyle}``    #
# where an ``editPath`` is an OPAQUE client string (the ``data-edit-path``      #
# grammar the renderer emits) validated only for shape — never resolved         #
# server-side. Each ``ElementStyle`` carries only the sub-keys below, each      #
# optional, each from a fixed vocabulary; a wrong TYPE / out-of-vocab value is   #
# rejected with a precise ``canvas.elementStyles.*`` field (mirrors             #
# ``_validate_theme_override``). Unknown sub-keys are STRIPPED; an empty         #
# per-path entry is dropped; the whole map is capped so a foreign client cannot  #
# bloat ``canvas_json``.                                                         #
# --------------------------------------------------------------------------- #
_ELEMENT_SIZE_TOKENS = frozenset({"xs", "sm", "base", "lg", "xl", "2xl"})
_ELEMENT_WEIGHT_TOKENS = frozenset({"normal", "medium", "semibold", "bold"})
_ELEMENT_ALIGN_TOKENS = frozenset({"left", "center", "right"})
_MAX_ELEMENT_STYLE_PATHS = 500
_MAX_EDIT_PATH_LEN = 200

# Block types the visual canvas editor supports. ``section`` is the primary one:
# a block bound to a ``cv_section`` that carries its render order/visibility/style
# (the ``<CvDocument/>`` renderer and PDF both read section-bound blocks). The rest
# are free-form canvas elements. Kept as an allowlist so a malformed/foreign client
# payload can never inject an unknown renderer directive
# (``docs/CV_STUDIO_SPEC.md`` "canvas elements").
_BLOCK_TYPES = frozenset(
    {"section", "text", "list", "heading", "image", "divider", "spacer", "custom"}
)
_MAX_BLOCKS = 300


def _validate_blocks(blocks_in: object, *, valid_section_ids: set[str]) -> list[dict]:
    if not isinstance(blocks_in, list) or len(blocks_in) > _MAX_BLOCKS:
        raise InvalidCvFieldError(field="canvas.blocks")

    seen_ids: set[str] = set()
    out: list[dict] = []
    for raw in blocks_in:
        if not isinstance(raw, dict):
            raise InvalidCvFieldError(field="canvas.blocks")
        block_id = raw.get("id")
        if not isinstance(block_id, str) or not block_id.strip() or block_id in seen_ids:
            raise InvalidCvFieldError(field="canvas.blocks.id")
        seen_ids.add(block_id)

        block_type = raw.get("type")
        if block_type not in _BLOCK_TYPES:
            raise InvalidCvFieldError(field="canvas.blocks.type")

        section_id = raw.get("section_id")
        if section_id is not None and str(section_id) not in valid_section_ids:
            # A block may reference a section that no longer exists (deleted
            # concurrently) or one outside this CV — reject rather than silently
            # orphan the binding.
            raise InvalidCvFieldError(field="canvas.blocks.section_id")

        order = raw.get("order", 0)
        if not isinstance(order, int) or isinstance(order, bool) or order < 0:
            raise InvalidCvFieldError(field="canvas.blocks.order")

        style = raw.get("style")
        out.append(
            {
                "id": block_id,
                "type": block_type,
                "section_id": str(section_id) if section_id else None,
                "order": order,
                "visible": bool(raw.get("visible", True)),
                "style": style if isinstance(style, dict) else {},
            }
        )
    return out


def _validate_theme_override(theme_in: object) -> dict:
    """Validate + clean a student theme override into a minimal partial theme.

    Contract (design spec §4.2 / P2 restyle rail): ``theme`` is a PARTIAL theme
    layered on the template. Only these sub-objects are accepted, each optional
    and each carrying only the keys below; any wrong TYPE or out-of-vocab value
    raises ``InvalidCvFieldError`` with a precise ``canvas.theme.*`` field
    (mirrors ``_validate_blocks``). Unknown top-level/nested keys are STRIPPED
    (forward-compatible + never persists junk). Empty sub-objects are dropped, so
    an all-empty/``{}`` payload returns ``{}`` (the caller resets to the template
    default).
    """

    if not isinstance(theme_in, dict):
        raise InvalidCvFieldError(field="canvas.theme")

    cleaned: dict = {}

    palette_in = theme_in.get("palette")
    if palette_in is not None:
        if not isinstance(palette_in, dict):
            raise InvalidCvFieldError(field="canvas.theme.palette")
        palette: dict = {}
        for key, value in palette_in.items():
            if key not in themes.PALETTE_KEYS:
                continue  # strip unknown colour slot
            if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
                raise InvalidCvFieldError(field="canvas.theme.palette")
            palette[key] = value
        if palette:
            cleaned["palette"] = palette

    typography_in = theme_in.get("typography")
    if typography_in is not None:
        if not isinstance(typography_in, dict):
            raise InvalidCvFieldError(field="canvas.theme.typography")
        typography: dict = {}
        for key, value in typography_in.items():
            if key in _TYPOGRAPHY_FONT_KEYS:
                if value not in themes.FONT_TOKENS:
                    raise InvalidCvFieldError(field="canvas.theme.typography")
                typography[key] = value
            elif key == "scale":
                if value not in _SCALE_TOKENS:
                    raise InvalidCvFieldError(field="canvas.theme.typography")
                typography[key] = value
            elif key == "headingCase":
                if value not in _HEADING_CASE_TOKENS:
                    raise InvalidCvFieldError(field="canvas.theme.typography")
                typography[key] = value
            # else: strip unknown typography key
        if typography:
            cleaned["typography"] = typography

    section_style_in = theme_in.get("sectionStyle")
    if section_style_in is not None:
        if not isinstance(section_style_in, dict):
            raise InvalidCvFieldError(field="canvas.theme.sectionStyle")
        section_style: dict = {}
        item_gap = section_style_in.get("itemGap")
        if item_gap is not None:
            if item_gap not in _ITEM_GAP_TOKENS:
                raise InvalidCvFieldError(field="canvas.theme.sectionStyle")
            section_style["itemGap"] = item_gap
        # else: strip unknown sectionStyle key
        if section_style:
            cleaned["sectionStyle"] = section_style

    return cleaned


def _validate_element_style(style_in: object) -> dict:
    """Validate one ``ElementStyle`` (the value at a single ``editPath``).

    Only the sub-keys below are accepted, each optional and each from a fixed
    vocabulary; a wrong TYPE / out-of-vocab value raises ``InvalidCvFieldError``
    with the precise field ``canvas.elementStyles.<sub-key>``. Unknown sub-keys are
    STRIPPED. Returns the cleaned style (possibly ``{}`` when nothing usable was
    provided — the caller then drops the whole per-path entry).
    """

    if not isinstance(style_in, dict):
        raise InvalidCvFieldError(field="canvas.elementStyles")

    cleaned: dict = {}
    for key, value in style_in.items():
        if key == "font":
            if value not in themes.FONT_TOKENS:
                raise InvalidCvFieldError(field="canvas.elementStyles.font")
            cleaned["font"] = value
        elif key == "size":
            if value not in _ELEMENT_SIZE_TOKENS:
                raise InvalidCvFieldError(field="canvas.elementStyles.size")
            cleaned["size"] = value
        elif key == "weight":
            if value not in _ELEMENT_WEIGHT_TOKENS:
                raise InvalidCvFieldError(field="canvas.elementStyles.weight")
            cleaned["weight"] = value
        elif key == "align":
            if value not in _ELEMENT_ALIGN_TOKENS:
                raise InvalidCvFieldError(field="canvas.elementStyles.align")
            cleaned["align"] = value
        elif key == "italic":
            # A real bool only — reject ints/strings so the renderer never has to
            # coerce a surprising truthy value.
            if not isinstance(value, bool):
                raise InvalidCvFieldError(field="canvas.elementStyles.italic")
            cleaned["italic"] = value
        elif key == "color":
            if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
                raise InvalidCvFieldError(field="canvas.elementStyles.color")
            cleaned["color"] = value
        # else: strip unknown ElementStyle sub-key (forward-compatible)
    return cleaned


def _validate_element_styles(styles_in: object) -> dict:
    """Validate + clean the whole ``elementStyles`` map into ``{editPath: style}``.

    Contract (design spec §"Data contracts" 1): a per-CV map from an OPAQUE
    ``editPath`` string (the renderer's ``data-edit-path`` grammar — validated for
    shape only, NOT resolved server-side) to an ``ElementStyle``. The map must be a
    dict of ≤ ``_MAX_ELEMENT_STYLE_PATHS`` entries; each key must be a non-empty
    string of reasonable length; each value is cleaned by
    ``_validate_element_style``. Per-path entries that clean to ``{}`` are dropped,
    so an all-empty / ``{}`` payload returns ``{}`` (the caller then resets by
    dropping the key).
    """

    if not isinstance(styles_in, dict):
        raise InvalidCvFieldError(field="canvas.elementStyles")
    if len(styles_in) > _MAX_ELEMENT_STYLE_PATHS:
        raise InvalidCvFieldError(field="canvas.elementStyles")

    cleaned: dict = {}
    for edit_path, style in styles_in.items():
        if (
            not isinstance(edit_path, str)
            or not edit_path.strip()
            or len(edit_path) > _MAX_EDIT_PATH_LEN
        ):
            raise InvalidCvFieldError(field="canvas.elementStyles")
        style_clean = _validate_element_style(style)
        if style_clean:
            cleaned[edit_path] = style_clean
    return cleaned


async def update_canvas(
    session: AsyncSession,
    *,
    principal,
    cv_id: uuid.UUID,
    payload: dict,
    ctx: RequestContext,
    locale: str = "vi",
) -> dict:
    permission_checker.require(principal, _RESOURCE, "update")
    assert principal.user_id is not None
    cv = await _cv_core._load_owned_cv(session, principal=principal, cv_id=cv_id, lock=True)

    expected = payload.get("expected_version")
    if expected is not None and expected != cv.version:
        raise CvVersionConflictError(current_version=cv.version)

    canvas = dict(cv.canvas_json or {})

    if "blocks" in payload and payload["blocks"] is not None:
        sections = await _cv_core._load_sections(session, cv_id=cv.id)
        valid_section_ids = {str(s.id) for s in sections}
        canvas["blocks"] = _validate_blocks(
            payload["blocks"], valid_section_ids=valid_section_ids
        )

    if "page" in payload and payload["page"] is not None:
        if not isinstance(payload["page"], dict):
            raise InvalidCvFieldError(field="canvas.page")
        canvas["page"] = payload["page"]

    if "theme" in payload and payload["theme"] is not None:
        # Replace ONLY the theme key (partial-update endpoint): a restyle sets
        # the whole override object at once. An all-empty/``{}`` payload resets
        # the CV to the template default by dropping the key.
        cleaned_theme = _validate_theme_override(payload["theme"])
        if cleaned_theme:
            canvas["theme"] = cleaned_theme
        else:
            canvas.pop("theme", None)

    # Accept both the JSON camelCase key and a snake_case alias so the router can
    # pass either; both mean the same per-element style map.
    element_styles_in = payload.get("elementStyles")
    if element_styles_in is None:
        element_styles_in = payload.get("element_styles")
    if element_styles_in is not None:
        # Replace ONLY the elementStyles key (partial-update endpoint): the toolbar
        # sets the whole per-element style map at once. An all-empty/``{}`` payload
        # resets every element to the theme default by dropping the key.
        cleaned_element_styles = _validate_element_styles(element_styles_in)
        if cleaned_element_styles:
            canvas["elementStyles"] = cleaned_element_styles
        else:
            canvas.pop("elementStyles", None)

    cv.canvas_json = canvas
    cv.version += 1
    cv.last_edited_at = _shared.now()
    await session.flush()

    await _cv_core._snapshot_version(
        session,
        cv=cv,
        change_source="manual",
        change_summary="canvas layout updated",
        created_by=principal.user_id,
    )
    await write_audit(
        session,
        action="cv.canvas.updated",
        resource_type="cv",
        resource_id=cv.id,
        context=_shared.audit_ctx(principal, ctx),
        after={"cv_id": str(cv.id), "block_count": len(canvas.get("blocks", []))},
    )
    await session.commit()
    await session.refresh(cv)
    return await _cv_core._detail_response(session, cv=cv, locale=locale)
